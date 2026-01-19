"""
Core Database Module - Sunter Dashboard Pro (V12.62 Intelligence)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. User Table Guard: Fix 'no such column: last_login' dengan auto-migration.
2. System Log Architecture: Penambahan tabel 'system_logs' untuk Audit Trail.
3. Snapshot Migration: Kunci Alamat & Nama Pelanggan pada kunjungan_petugas.
4. Turbo Indexing: Optimasi pencarian data untuk dashboard performa tinggi.
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
        conn.execute('PRAGMA journal_mode=WAL;')       # Anti-Lock Simultaneous Access
        conn.execute('PRAGMA synchronous=NORMAL;')     # I/O Speed Optimization
        conn.execute('PRAGMA foreign_keys = ON;')      # Relational Integrity
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
            
            # 1. Pastikan Struktur Tabel Dasar Tersedia
            check_and_create_tables(cursor)

            # 2. Jalankan Migrasi Self-Healing (Fixing Missing Columns)
            run_smart_migration(cursor)
            
            # 3. Optimasi Turbo Indexing (Fast Join)
            optimize_performance(cursor)

            # 4. Seeding Akun Admin Default
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.62: Fix last_login, Audit Trail, & Snapshot Alamat Aktif.")
            
        except Exception as e:
            print(f"❌ Database Init Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """ Menjamin infrastruktur tabel utama tersedia. """
    # TABEL USERS (DIPERKUAT)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            petugas_id TEXT
        )
    """)

    # TABEL KUNJUNGAN
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # TABEL LOG SISTEM (AUDIT TRAIL)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, action TEXT, module TEXT, details TEXT, 
            ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    """ [HELPER: MEKANISME MIGRASI TANPA HAPUS DATA] """
    
    # --- 1. UPDATE TABEL USERS (Fix: last_login error) ---
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [row['name'] for row in cursor.fetchall()]
    if 'last_login' not in user_cols:
        print("🔧 Migrating: Adding 'last_login' to users table...")
        cursor.execute("ALTER TABLE users ADD COLUMN last_login TIMESTAMP")

    # --- 2. UPDATE TABEL KUNJUNGAN (Snapshot Architecture) ---
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

    # --- 3. PERIODE GUARD ---
    tables_to_fix = ['master_pelanggan', 'master_bayar', 'collection_harian', 'ardebt']
    for table in tables_to_fix:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row['name'] for row in cursor.fetchall()]
        if 'periode' not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")

def optimize_performance(cursor):
    """ [TURBO INDEXING] """
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_logs_date ON system_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_per ON kunjungan_petugas (periode)",
        "CREATE INDEX IF NOT EXISTS idx_master_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_ardebt_nom ON ardebt (nomen)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))

def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
