"""
Core Database Module - Sunter Dashboard Pro (V17.0 Stable Hybrid)
Update: 2026-02-05
---------------------------------------------------------------------------
Basis: V13.2 (Pilihan User) + Patch V16.5 (Support Dashboard Baru)
Fitur:
1. ✅ STABILITAS V13.2: Menggunakan logic koneksi dan pragma yang terbukti sukses.
2. ✅ SUPPORT DASHBOARD V16: Menjamin kolom 'kubik', 'volume', 'nomet' tersedia.
3. ✅ AUTO-FIX: Memperbaiki tabel otomatis jika ada kolom tertinggal.
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
        
        # Settingan V13.2 yang Anda suka (Terbukti Stabil)
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
            
            # 1. Infrastruktur Dasar
            check_and_create_tables(cursor)
            db.commit() 

            # 2. Self-Healing (Digabung dengan kebutuhan V16)
            run_smart_migration(cursor)
            db.commit()
            
            # 3. Turbo Indexing
            optimize_performance(cursor)
            
            # 4. Security
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V17.0: Hybrid Stability & Dashboard Support Ready.")
            
        except Exception as e:
            print(f"⚠️ Database Init Warning: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """Melahirkan struktur tabel utama."""
    
    # Update Struktur Master Pelanggan (Support Nomet & Kubik)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nomen TEXT, 
            nomet TEXT,  -- Penting untuk Dashboard
            nama TEXT, 
            alamat TEXT, pcez TEXT, rayon TEXT, nominal REAL, 
            kubik REAL DEFAULT 0, -- Penting untuk Dashboard
            periode TEXT, 
            status_lunas INTEGER DEFAULT 0, no_hp TEXT DEFAULT '-', 
            tgl_lunas TEXT, tipe TEXT DEFAULT 'MC',
            latitude TEXT, longitude TEXT
        )
    """)
    
    # Update Ardebt (Support Volume)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ardebt (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, 
            periode_bill TEXT, jumlah REAL DEFAULT 0, 
            volume REAL DEFAULT 0, -- Penting untuk Dashboard
            periode TEXT, tipe_bill TEXT DEFAULT 'WATER'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rute_petugas (
            pcez TEXT PRIMARY KEY, petugas TEXT, no_admin TEXT, 
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT NOT NULL, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE TABLE IF NOT EXISTS upload_history (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT, file_type TEXT, periode TEXT, row_count INTEGER DEFAULT 0, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS master_bayar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, tgl_bayar TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY', bulan_rek TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS collection_harian (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, pay_dt TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY', bulan_rek TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, petugas_id TEXT, last_login TIMESTAMP, no_hp TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS system_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT, module TEXT, details TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    # Tabel Analisa Anomali
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

    # Triggers
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
    Fungsi Penyelamat (Hybrid): 
    Menggabungkan V13.2 (GPS Fix) dengan V16.5 (Data Lengkap).
    """
    
    # Daftar Kolom Wajib agar Dashboard V16.5 jalan mulus
    required_columns = [
        # Tabel Kunjungan (Fitur V13.2)
        ('kunjungan_petugas', 'latitude', 'TEXT'),
        ('kunjungan_petugas', 'longitude', 'TEXT'),
        ('kunjungan_petugas', 'akurasi', 'TEXT'),
        ('kunjungan_petugas', 'nomet', 'TEXT'),
        ('kunjungan_petugas', 'periode', 'TEXT'),
        ('kunjungan_petugas', 'foto_path', 'TEXT'),

        # Tabel Master Pelanggan (Fitur Dashboard V16)
        ('master_pelanggan', 'kubik', 'REAL DEFAULT 0'),
        ('master_pelanggan', 'nomet', 'TEXT'),
        ('master_pelanggan', 'latitude', 'TEXT'),
        ('master_pelanggan', 'longitude', 'TEXT'),
        ('master_pelanggan', 'tipe', "TEXT DEFAULT 'MC'"),
        ('master_pelanggan', 'periode', 'TEXT'),

        # Tabel Ardebt
        ('ardebt', 'volume', 'REAL DEFAULT 0'),
        ('ardebt', 'periode', 'TEXT'),
        ('ardebt', 'tipe_bill', "TEXT DEFAULT 'WATER'"),

        # Tabel Transaksi
        ('master_bayar', 'periode', 'TEXT'),
        ('master_bayar', 'bulan_rek', 'TEXT'),
        ('collection_harian', 'periode', 'TEXT'),
        ('collection_harian', 'bulan_rek', 'TEXT')
    ]

    print("⚙️ Verifikasi Struktur Database (Hybrid Check)...")
    
    for table, col, dtype in required_columns:
        try:
            # Coba tambah kolom
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
            print(f"   🔧 Fixed: Menambahkan kolom '{col}' ke tabel '{table}'")
        except sqlite3.OperationalError:
            # Kolom sudah ada? Bagus, lanjut.
            pass
        except Exception as e:
            print(f"   ⚠️ Warning check {table}.{col}: {e}")

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
        try: cursor.execute(idx)
        except: pass

def seed_default_admin(cursor):
    """Menjamin akses Admin Utama."""
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
