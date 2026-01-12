"""
Core Database Module - Sunter Dashboard Pro (V7.6 Sinergi Final Edition)
Pembaruan:
1. Strict Separation Logic: Penambahan Index pada tabel Ardebt untuk mempercepat filter pemisahan data.
2. Anti-NULL Trigger Guard: Sinkronisasi otomatis status lunas di Master Pelanggan berdasarkan Nomen & Periode.
3. Multi-Table Periode Sync: Menjamin kolom 'periode' tersedia di semua tabel transaksi (MC, MB, Coll, Ardebt).
4. Self-Healing Migration V6: Menjamin kolom NOMET bertipe TEXT untuk data alfanumerik Excel.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """ [FUNGSI: KONEKSI DATABASE UTAMA] """
    db_path = current_app.config.get('DATABASE')
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        conn.execute('PRAGMA journal_mode=WAL;')       # Anti-Lock untuk akses simultan
        conn.execute('PRAGMA synchronous=NORMAL;')     # Kecepatan I/O maksimal
        conn.execute('PRAGMA foreign_keys = ON;')      # Menjamin integritas relasi
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
            
            # 1. Jalankan Skema Dasar
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. Proteksi Tabel Krusial
            check_and_create_tables(cursor)

            # 3. Jalankan Migrasi Self-Healing V6 (Integritas Periode & Nomet)
            run_smart_migration(cursor)
            
            # 4. Optimasi Turbo Indexing (Fast Join & Auto-Hide)
            optimize_performance(cursor)

            # 5. Seeding Akun Admin Pusat
            seed_default_admin(cursor)

            db.commit()
            print("✅ Sinergi V7.6: Infrastruktur Database, Ardebt Filter & Nomet Sync Aktif.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """ Menjamin tabel-tabel krusial tersedia agar sistem tidak crash. """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
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
    """ [HELPER: MEKANISME SELF-HEALING V6] """
    # --- 1. MIGRASI TABEL KUNJUNGAN ---
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_kunjungan = [row['name'] for row in cursor.fetchall()]
    kunjungan_cols = {
        'mc': 'REAL DEFAULT 0', 'ardebt': 'REAL DEFAULT 0', 'catatan': 'TEXT',
        'keterangan': 'TEXT', 'foto_path': 'TEXT', 'nomet': 'TEXT',
        'nama_snapshot': 'TEXT', 'alamat_snapshot': 'TEXT', 'latitude': 'TEXT',
        'longitude': 'TEXT', 'no_hp': 'TEXT', 'volume': 'REAL DEFAULT 0', 'periode': 'TEXT'
    }
    for col, dtype in kunjungan_cols.items():
        if col not in existing_kunjungan:
            cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")

    # --- 2. PERIODE & NOMET GUARD (MASTER & TRANSAKSI) ---
    # Mendukung pemisahan Ardebt dan Current
    tables_to_fix = ['master_pelanggan', 'master_bayar', 'collection_harian', 'ardebt']
    for table in tables_to_fix:
        cursor.execute(f"PRAGMA table_info({table})")
        existing_cols = [row['name'] for row in cursor.fetchall()]
        if 'periode' not in existing_cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")
        if table == 'master_pelanggan' and 'nomet' not in existing_cols:
            cursor.execute(f"ALTER TABLE master_pelanggan ADD COLUMN nomet TEXT")

    # --- 3. AUDIT TRAIL GUARD ---
    cursor.execute("UPDATE upload_history SET row_count = 0 WHERE row_count IS NULL")
    cursor.execute("UPDATE upload_history SET status = 'FAILED' WHERE status IS NULL")

def optimize_performance(cursor):
    """ [HELPER: TURBO LOADING & INDEXING] """
    indices = [
        # Index Utama untuk Join Nomen & Periode
        "CREATE INDEX IF NOT EXISTS idx_master_nomen_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_master_pcez_per ON master_pelanggan (pcez, periode)",
        
        # Index untuk Filter Ardebt (Pemisahan Current)
        "CREATE INDEX IF NOT EXISTS idx_ardebt_nomen ON ardebt (nomen)",
        
        # Index untuk Realisasi (Anti-NULL Logic)
        "CREATE INDEX IF NOT EXISTS idx_mb_nomen_per ON master_bayar (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_coll_nomen_per ON collection_harian (nomen, periode)",
        
        # Index Audit
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_periode ON kunjungan_petugas (periode)",
        "CREATE INDEX IF NOT EXISTS idx_history_date ON upload_history (created_at)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
    """ Menjamin ketersediaan akun admin utama. """
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
