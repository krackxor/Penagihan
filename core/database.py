"""
Core Database Module - Sunter Dashboard Pro (V12.63 Stable)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Solid Initialization: Menjamin tabel master dibuat sebelum indexing (Fix: no such table).
2. User Table Guard: Fix 'no such column: last_login' dengan auto-migration.
3. Snapshot Architecture: Kunci Alamat & Nama Pelanggan pada kunjungan_petugas.
4. sequential Execution: Pemisahan tahap Create, Migrate, dan Index secara ketat.
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
            
            # --- TAHAP 1: PEMBUATAN TABEL (HARUS PALING AWAL) ---
            check_and_create_tables(cursor)
            db.commit() # Kunci agar tabel benar-benar ada di disk

            # --- TAHAP 2: MIGRASI KOLOM (SELF-HEALING) ---
            run_smart_migration(cursor)
            db.commit()
            
            # --- TAHAP 3: OPTIMASI (INDEXING) ---
            optimize_performance(cursor)

            # --- TAHAP 4: SEEDING ---
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.63: Inisialisasi Sukses & Indexing Aktif.")
            
        except Exception as e:
            print(f"❌ Database Init Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """Melahirkan struktur tabel master secara eksplisit untuk mencegah error 'no such table'."""
    
    # 1. Tabel Master (Krusial untuk Indexing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT UNIQUE,
            nama TEXT, alamat TEXT, pcez TEXT, rayon TEXT, 
            nominal REAL, nomet TEXT, periode TEXT, status_lunas INTEGER DEFAULT 0
        )
    """)

    # 2. Tabel Transaksi Dasar
    cursor.execute("CREATE TABLE IF NOT EXISTS master_bayar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS collection_harian (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS ardebt (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode TEXT)")
    
    # 3. Tabel Infrastruktur Lainnya
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
    """Menambahkan kolom baru ke tabel yang sudah ada."""
    
    # Fix users: last_login
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

    # Fix ardebt: columns
    cursor.execute("PRAGMA table_info(ardebt)")
    existing_ardebt = [row['name'] for row in cursor.fetchall()]
    if 'jumlah' not in existing_ardebt:
        cursor.execute("ALTER TABLE ardebt ADD COLUMN jumlah REAL DEFAULT 0")
    if 'periode_bill' not in existing_ardebt:
        cursor.execute("ALTER TABLE ardebt ADD COLUMN periode_bill TEXT")

def optimize_performance(cursor):
    """Menjalankan Turbo Indexing hanya setelah tabel dipastikan ada."""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_master_nomen_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_logs_date ON system_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_per ON kunjungan_petugas (periode)",
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
