"""
Core Database Module - Sunter Dashboard Pro (V12.67 Stable)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Infrastructure First: Menjamin rute_petugas & upload_history dibuat paling awal.
2. Robust Transaction: Menggunakan COMMIT setelah pembuatan tabel untuk mengunci skema.
3. Fix last_login: Auto-migration pada tabel users.
4. sequential Execution: Pemisahan tahap Create, Migrate, dan Index secara ketat.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """ [KONEKSI DATABASE UTAMA DENGAN PRAGMA TURBO] """
    db_path = current_app.config.get('DATABASE')
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        conn.execute('PRAGMA journal_mode=WAL;')       # Mode Multi-User Anti-Lock
        conn.execute('PRAGMA synchronous=NORMAL;')     # Kecepatan I/O maksimal
        conn.execute('PRAGMA foreign_keys = ON;')      # Integritas Relasional
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """ [INISIALISASI & MIGRASI OTOMATIS] """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # --- TAHAP 1: PEMBUATAN TABEL (HARUS PALING AWAL) ---
            check_and_create_tables(cursor)
            db.commit() # Kunci agar tabel benar-benar ada di disk sebelum migrasi

            # --- TAHAP 2: MIGRASI KOLOM (SELF-HEALING) ---
            run_smart_migration(cursor)
            db.commit()
            
            # --- TAHAP 3: OPTIMASI (INDEXING) ---
            optimize_performance(cursor)

            # --- TAHAP 4: SEEDING ADMIN ---
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.67: Inisialisasi Sukses & Infrastruktur Siap.")
            
        except Exception as e:
            print(f"❌ Database Init Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """Melahirkan struktur tabel master secara eksplisit untuk mencegah error 'no such table'."""
    
    # 1. Tabel Infrastruktur & Navigasi
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rute_petugas (
            pcez TEXT PRIMARY KEY,
            petugas TEXT,
            no_admin TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT, file_type TEXT, periode TEXT,
            row_count INTEGER DEFAULT 0, status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Tabel Master Pelanggan & Ardebt
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT UNIQUE,
            nama TEXT, alamat TEXT, pcez TEXT, rayon TEXT, 
            nominal REAL, nomet TEXT, periode TEXT, status_lunas INTEGER DEFAULT 0
        )
    """)

    cursor.execute("CREATE TABLE IF NOT EXISTS master_bayar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS collection_harian (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS ardebt (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    
    # 3. Tabel Keamanan & Log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, password TEXT, role TEXT, petugas_id TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, action TEXT, module TEXT, details TEXT, ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def run_smart_migration(cursor):
    """Menambahkan kolom baru ke tabel yang sudah ada (Self-Healing)."""
    
    # Fix users: last_login (Penyebab Akses Ditolak)
    cursor.execute("PRAGMA table_info(users)")
    if 'last_login' not in [row['name'] for row in cursor.fetchall()]:
        cursor.execute("ALTER TABLE users ADD COLUMN last_login TIMESTAMP")

    # Fix kunjungan_petugas: Snapshot & Nominal
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing = [row['name'] for row in cursor.fetchall()]
    cols = {
        'mc': 'REAL DEFAULT 0', 'ardebt': 'REAL DEFAULT 0', 'catatan': 'TEXT',
        'keterangan': 'TEXT', 'foto_path': 'TEXT', 'nama_snapshot': 'TEXT',
        'alamat_snapshot': 'TEXT', 'latitude': 'TEXT', 'longitude': 'TEXT', 'periode': 'TEXT'
    }
    for col, dtype in cols.items():
        if col not in existing:
            cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")

def optimize_performance(cursor):
    """Menjalankan Turbo Indexing untuk akselerasi join data."""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_master_nomen_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_logs_date ON system_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_per ON kunjungan_petugas (periode)",
        "CREATE INDEX IF NOT EXISTS idx_ardebt_nomen ON ardebt (nomen)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
    """Menjamin akses administrator tersedia."""
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("INSERT INTO users (username, password, role, petugas_id) VALUES (?, ?, ?, ?)", 
                       (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))

def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
