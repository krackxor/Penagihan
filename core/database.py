"""
Core Database Module - Sunter Dashboard Pro (V12.61 Intelligence)
Pembaruan: Fix 'no such table' error dengan inisialisasi tabel master eksplisit.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    db_path = current_app.config.get('DATABASE')
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        conn.execute('PRAGMA foreign_keys = ON;')
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # --- URUTAN LOGIKA TETAP (CRITICAL) ---
            # 1. Lahirkan tabel jika belum ada
            check_and_create_tables(cursor)

            # 2. Tambahkan kolom baru jika ada update versi
            run_smart_migration(cursor)
            
            # 3. Optimasi (Hanya jalan setelah tabel dipastikan ada)
            optimize_performance(cursor)

            # 4. Buat user admin default
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.61: Infrastruktur siap dan teroptimasi.")
            
        except Exception as e:
            print(f"❌ Database Init Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """ Menjamin seluruh tabel master tersedia agar Indexing tidak Error. """
    
    # Tabel Master Utama
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT UNIQUE,
            nama TEXT, alamat TEXT, pcez TEXT, rayon TEXT, 
            nominal REAL, nomet TEXT, periode TEXT, status_lunas INTEGER DEFAULT 0
        )
    """)

    # Tabel Transaksi
    cursor.execute("CREATE TABLE IF NOT EXISTS master_bayar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS collection_harian (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS ardebt (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    
    # Tabel User & Rute
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, password TEXT, role TEXT, petugas_id TEXT
        )
    """)
    
    # Tabel Log & Kunjungan
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT, file_type TEXT, periode TEXT,
            row_count INTEGER DEFAULT 0, status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def run_smart_migration(cursor):
    """ [MEKANISME SELF-HEALING: Update Kolom Tanpa Hapus Data] """
    
    # --- Update Kunjungan Petugas ---
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_kunjungan = [row['name'] for row in cursor.fetchall()]
    kunjungan_cols = {
        'mc': 'REAL DEFAULT 0', 'ardebt': 'REAL DEFAULT 0', 'catatan': 'TEXT',
        'keterangan': 'TEXT', 'foto_path': 'TEXT', 'nomet': 'TEXT',
        'nama_snapshot': 'TEXT', 'alamat_snapshot': 'TEXT', 'latitude': 'TEXT',
        'longitude': 'TEXT', 'no_hp': 'TEXT', 'periode': 'TEXT'
    }
    for col, dtype in kunjungan_cols.items():
        if col not in existing_kunjungan:
            cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")

    # --- Update Ardebt & Master (Ensure Columns) ---
    tables_to_check = {
        'ardebt': {'jumlah': 'REAL DEFAULT 0', 'volume': 'REAL DEFAULT 0', 'periode_bill': 'TEXT'},
        'master_pelanggan': {'nomet': 'TEXT', 'pcez': 'TEXT'}
    }
    for table, cols in tables_to_check.items():
        cursor.execute(f"PRAGMA table_info({table})")
        existing = [row['name'] for row in cursor.fetchall()]
        for c_name, c_type in cols.items():
            if c_name not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {c_name} {c_type}")

def optimize_performance(cursor):
    """ [TURBO INDEXING] """
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_logs_date ON system_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_per ON kunjungan_petugas (periode)",
        "CREATE INDEX IF NOT EXISTS idx_master_nomen_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_ardebt_nomen ON ardebt (nomen)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
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
