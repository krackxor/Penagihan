"""
Core Database Module - Sunter Dashboard Pro (V12.60 Intelligence)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. System Log Architecture: Penambahan tabel 'system_logs' untuk Audit Trail Admin.
2. Snapshot Migration: Update tabel kunjungan_petugas untuk mengunci Alamat & Nama Pelanggan.
3. Dual Nominal Logic: Menjamin kolom 'mc' dan 'ardebt' tersedia untuk pemisahan tugas.
4. Turbo Indexing: Optimasi join antar periode untuk mempercepat loading Kumulatif Rayon.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """ [FUNGSI: KONEKSI DATABASE UTAMA DENGAN PRAGMA TURBO] """
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
    """ [FUNGSI: INISIALISASI & MIGRASI OTOMATIS] """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Pastikan Tabel-Tabel Dasar Tersedia
            check_and_create_tables(cursor)

            # 2. Jalankan Migrasi Self-Healing (Kunjungan & Log)
            run_smart_migration(cursor)
            
            # 3. Optimasi Turbo Indexing (Fast Join)
            optimize_performance(cursor)

            # 4. Seeding Akun Admin
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.60: Audit Trail, Snapshot Alamat & Dual Nominal Aktif.")
            
        except Exception as e:
            print(f"❌ Database Init Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """ Menjamin infrastruktur tabel utama agar sistem tidak crash. """
    # TABEL KUNJUNGAN (DIPERLUAS UNTUK SNAPSHOT)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # [FITUR BARU] TABEL LOG SISTEM (AUDIT TRAIL)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT,
            module TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    """ [HELPER: MEKANISME MIGRASI OTOMATIS TANPA HAPUS DATA] """
    # --- 1. UPDATE TABEL KUNJUNGAN (V12.60 SNAPSHOT) ---
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_kunjungan = [row['name'] for row in cursor.fetchall()]
    kunjungan_cols = {
        'mc': 'REAL DEFAULT 0',        # Tagihan Current
        'ardebt': 'REAL DEFAULT 0',    # Tagihan Tunggakan
        'catatan': 'TEXT',             # Memo Petugas
        'keterangan': 'TEXT',          # Status: JANJI BAYAR, RKS, dsb
        'foto_path': 'TEXT',
        'nomet': 'TEXT',
        'nama_snapshot': 'TEXT',       # Kunci Nama Saat Dikunjungi
        'alamat_snapshot': 'TEXT',     # Kunci Alamat Saat Dikunjungi
        'latitude': 'TEXT',
        'longitude': 'TEXT',
        'no_hp': 'TEXT',
        'periode': 'TEXT'
    }
    for col, dtype in kunjungan_cols.items():
        if col not in existing_kunjungan:
            cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")

    # --- 2. PERIODE GUARD ---
    tables_to_fix = ['master_pelanggan', 'master_bayar', 'collection_harian', 'ardebt']
    for table in tables_to_fix:
        cursor.execute(f"PRAGMA table_info({table})")
        existing_cols = [row['name'] for row in cursor.fetchall()]
        if 'periode' not in existing_cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")

def optimize_performance(cursor):
    """ [TURBO INDEXING: AKSELERASI DASHBOARD] """
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_logs_date ON system_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_per ON kunjungan_petugas (periode)",
        "CREATE INDEX IF NOT EXISTS idx_master_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_ardebt_nomen ON ardebt (nomen)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
    """ Menjamin akses admin tidak terkunci. """
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
