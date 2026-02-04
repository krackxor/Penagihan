"""
Core Database Module - Sunter Dashboard Pro (V15.2 Auto-Healing)
Update: 2026-02-05
---------------------------------------------------------------------------
Fitur Utama:
1. ✅ AUTO-HEALING: Otomatis mendeteksi dan menambah kolom yang hilang (kubik, volume, dll).
2. ✅ ANOMALY TABLES: Otomatis membuat tabel untuk analisa Ekstrem & Drop.
3. ✅ PERFORMANCE: Tuning SQLite PRAGMA untuk kecepatan dashboard.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """ [KONEKSI DATABASE UTAMA DENGAN PRAGMA ULTRA-TURBO] """
    db_path = current_app.config.get('DATABASE') or os.path.join(os.getcwd(), 'penagihan.db')
    try:
        conn = sqlite3.connect(db_path, timeout=300)
        conn.row_factory = sqlite3.Row 
        
        # Tuning Performa
        conn.execute('PRAGMA journal_mode=WAL;')        
        conn.execute('PRAGMA synchronous=NORMAL;')      
        conn.execute('PRAGMA temp_store=MEMORY;')       
        conn.execute('PRAGMA cache_size=-128000;')      
        conn.execute('PRAGMA busy_timeout=300000;')     
        conn.execute('PRAGMA journal_size_limit=67108864;') 
        conn.execute('PRAGMA foreign_keys = ON;')       
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Connection Error: {e}")
        raise

def init_db(app):
    """ [INISIALISASI & MIGRASI OTOMATIS] """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Pastikan Tabel Utama Ada
            check_and_create_tables(cursor)
            db.commit() 

            # 2. JALANKAN PERBAIKAN STRUKTUR (MIGRASI)
            # Ini yang memperbaiki error "no such column: kubik/volume"
            run_smart_migration(cursor)
            db.commit()
            
            # 3. Buat Index agar Cepat
            optimize_performance(cursor)
            
            # 4. Buat Admin Default
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database System Ready (Structure Verified).")
            
        except Exception as e:
            print(f"⚠️ Database Init Warning: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """Membuat tabel jika belum ada."""
    
    # Tabel Master Pelanggan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, nama TEXT, 
            alamat TEXT, pcez TEXT, rayon TEXT, nominal REAL, kubik REAL DEFAULT 0,
            periode TEXT, status_lunas INTEGER DEFAULT 0, no_hp TEXT DEFAULT '-', 
            tgl_lunas TEXT, tipe TEXT DEFAULT 'MC',
            latitude TEXT, longitude TEXT
        )
    """)
    
    # Tabel Ardebt (Tunggakan)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ardebt (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, 
            periode_bill TEXT, jumlah REAL DEFAULT 0, volume REAL DEFAULT 0, 
            periode TEXT, tipe_bill TEXT DEFAULT 'WATER'
        )
    """)

    # Tabel Rute
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rute_petugas (
            pcez TEXT PRIMARY KEY, petugas TEXT, no_admin TEXT, 
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Kunjungan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT NOT NULL, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Transaksi & Log
    cursor.execute("CREATE TABLE IF NOT EXISTS upload_history (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT, file_type TEXT, periode TEXT, row_count INTEGER DEFAULT 0, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS master_bayar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, tgl_bayar TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY', bulan_rek TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS collection_harian (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, pay_dt TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY', bulan_rek TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, petugas_id TEXT, last_login TIMESTAMP, no_hp TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS system_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT, module TEXT, details TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    # Tabel Analisa Anomali (Dashboard V15)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analisa_ekstrem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT, periode TEXT, penyebab TEXT, tindakan TEXT, auditor TEXT, updated_at DATETIME
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analisa_drop (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT, periode TEXT, penyebab TEXT, tindakan TEXT, auditor TEXT, updated_at DATETIME
        )
    """)

    # Triggers Otomatis Lunas
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_mb
        AFTER INSERT ON master_bayar BEGIN
            UPDATE master_pelanggan SET status_lunas = 1, tgl_lunas = NEW.tgl_bayar
            WHERE nomen = NEW.nomen AND status_lunas = 0;
        END;
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_coll
        AFTER INSERT ON collection_harian BEGIN
            UPDATE master_pelanggan SET status_lunas = 1, tgl_lunas = NEW.pay_dt
            WHERE nomen = NEW.nomen AND status_lunas = 0;
        END;
    """)

def run_smart_migration(cursor):
    """
    Fungsi Penyelamat: Mengecek kolom satu per satu.
    Jika kolom belum ada di database lama, akan ditambahkan paksa.
    """
    
    # Daftar Kolom Wajib untuk Dashboard V15
    # Format: (Nama Tabel, Nama Kolom, Tipe Data)
    required_columns = [
        # Tabel Master Pelanggan
        ('master_pelanggan', 'kubik', 'REAL DEFAULT 0'),
        ('master_pelanggan', 'latitude', 'TEXT'),
        ('master_pelanggan', 'longitude', 'TEXT'),
        ('master_pelanggan', 'tipe', "TEXT DEFAULT 'MC'"),
        
        # Tabel Ardebt
        ('ardebt', 'volume', 'REAL DEFAULT 0'),
        ('ardebt', 'tipe_bill', "TEXT DEFAULT 'WATER'"),
        
        # Tabel Kunjungan (GPS)
        ('kunjungan_petugas', 'latitude', 'TEXT'),
        ('kunjungan_petugas', 'longitude', 'TEXT'),
        ('kunjungan_petugas', 'akurasi', 'TEXT'),
        ('kunjungan_petugas', 'foto_path', 'TEXT'),
        
        # Tabel Transaksi
        ('master_bayar', 'bulan_rek', 'TEXT'),
        ('collection_harian', 'bulan_rek', 'TEXT')
    ]

    print("⚙️ Checking Database Schema Integrity...")
    
    for table, col, dtype in required_columns:
        try:
            # Coba tambahkan kolom. Jika sudah ada, SQLite akan error -> masuk ke except -> Lanjut.
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
            print(f"   🔧 Fixed: Added column '{col}' to table '{table}'")
        except sqlite3.OperationalError:
            # Error ini berarti kolom sudah ada, jadi aman. Abaikan.
            pass
        except Exception as e:
            print(f"   ⚠️ Warning: Failed to check {table}.{col}: {e}")

def optimize_performance(cursor):
    """Turbo Indexing."""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_mc_nomen_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_mb_nomen_per ON master_bayar (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_kj_nomen_per ON kunjungan_petugas (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_ardebt_nomen ON ardebt (nomen)",
        "CREATE INDEX IF NOT EXISTS idx_mc_coords ON master_pelanggan (latitude, longitude)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
    """Admin Default."""
    username = 'admin_sunter'
    hashed_pw = generate_password_hash('admin123')
    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password, role, petugas_id) 
        VALUES (?, ?, ?, ?)
    """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))

def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
