"""
Core Database Module - Sunter Dashboard Pro (V12.71 Full Sync)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Transaction Column Shield: Menjamin tgl_bayar & kategori tersedia (Fix: Sync Error).
2. Category Logic: Mendukung klasifikasi UNDUE/CURRENT untuk Dashboard N+1.
3. Ardebt Extension: Sinkronisasi kolom periode_bill & volume pada tabel tunggakan.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    db_path = current_app.config.get('DATABASE') or os.path.join(os.getcwd(), 'penagihan.db')
    try:
        conn = sqlite3.connect(db_path, timeout=60)
        conn.row_factory = sqlite3.Row 
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        conn.execute('PRAGMA foreign_keys = ON;')
        return conn
    except sqlite3.Error as e:
        print(f"❌ Connection Error: {e}")
        raise

def init_db(app):
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # --- TAHAP 1: INFRASTRUKTUR & MASTER ---
            check_and_create_tables(cursor)
            db.commit() 

            # --- TAHAP 2: SELF-HEALING MIGRATIONS ---
            run_smart_migration(cursor)
            db.commit()
            
            # --- TAHAP 3: TURBO INDEXING ---
            optimize_performance(cursor)
            
            # --- TAHAP 4: SECURITY SEEDING ---
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.71: Skema Fisik & Logika Upload Sinkron.")
            
        except Exception as e:
            print(f"❌ Database Init Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    # 1. Infrastruktur Dasar
    cursor.execute("CREATE TABLE IF NOT EXISTS rute_petugas (pcez TEXT PRIMARY KEY, petugas TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS upload_history (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT, file_type TEXT, periode TEXT, row_count INTEGER DEFAULT 0, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    # 2. Master Pelanggan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT UNIQUE, nama TEXT, alamat TEXT, pcez TEXT, rayon TEXT, 
            nominal REAL, nomet TEXT, periode TEXT, status_lunas INTEGER DEFAULT 0
        )
    """)

    # 3. Tabel Transaksi (FIXED: Penambahan kolom tgl_bayar, pay_dt, & kategori)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_bayar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nomen TEXT, tgl_bayar TEXT, nominal REAL, periode TEXT, kategori TEXT DEFAULT 'HISTORY'
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_harian (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nomen TEXT, pay_dt TEXT, nominal REAL, periode TEXT, kategori TEXT DEFAULT 'HISTORY'
        )
    """)

    # Ardebt dengan periode_bill (untuk tunggakan berekor)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ardebt (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nomen TEXT, periode_bill TEXT, jumlah REAL, volume REAL, periode TEXT
        )
    """)
    
    # 4. Keamanan & Log
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, petugas_id TEXT, last_login TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS system_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT, module TEXT, details TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS kunjungan_petugas (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

def run_smart_migration(cursor):
    """Fungsi yang menjaga data tetap aman saat ada update fitur baru"""
    # Migrasi Kunjungan (Snapshot)
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing = [row['name'] for row in cursor.fetchall()]
    cols = {'mc':'REAL', 'ardebt':'REAL', 'catatan':'TEXT', 'keterangan':'TEXT', 'foto_path':'TEXT', 'nama_snapshot':'TEXT', 'alamat_snapshot':'TEXT', 'latitude':'TEXT', 'longitude':'TEXT', 'periode':'TEXT', 'petugas_name':'TEXT'}
    for col, dtype in cols.items():
        if col not in existing: cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")

def optimize_performance(cursor):
    """Menambah index pada kategori untuk mempercepat Dashboard Pusat Kendali"""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_master_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_mb_cat ON master_bayar (periode, kategori)",
        "CREATE INDEX IF NOT EXISTS idx_coll_cat ON collection_harian (periode, kategori)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_per ON kunjungan_petugas (periode)"
    ]
    for idx in indices: cursor.execute(idx)

def seed_default_admin(cursor):
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("INSERT INTO users (username, password, role, petugas_id) VALUES (?, ?, ?, ?)", (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))

def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
