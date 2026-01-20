"""
Core Database Module - Sunter Dashboard Pro (V12.78 Ultimate Sync)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Smart Undue Shield: Migrasi otomatis kolom 'bulan_rek' (Fix: Sync Error).
2. Table Integrity: Menjamin tabel 'upload_history' & 'kunjungan_petugas' sinkron.
3. Self-Healing Master: Auto-migrasi kolom 'tarif' & 'kubik' (Fix: Ardebt Error).
4. Robust Multi-User: Busy Timeout 60s & WAL Mode aktif (Fix: Database is locked).
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """ [KONEKSI DATABASE UTAMA DENGAN PRAGMA TURBO] """
    db_path = current_app.config.get('DATABASE') or os.path.join(os.getcwd(), 'penagihan.db')
    try:
        # Timeout ditingkatkan untuk mencegah 'Database is locked' saat upload besar
        conn = sqlite3.connect(db_path, timeout=60)
        conn.row_factory = sqlite3.Row 
        
        # Optimasi SQLite untuk Akses Simultan (Multi-User)
        conn.execute('PRAGMA journal_mode=WAL;')       # Baca/Tulis bersamaan
        conn.execute('PRAGMA synchronous=NORMAL;')     # Performa tulis cepat
        conn.execute('PRAGMA foreign_keys = ON;')      # Integritas relasi
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
            
            # --- TAHAP 1: INFRASTRUKTUR DASAR ---
            check_and_create_tables(cursor)
            db.commit() 

            # --- TAHAP 2: SELF-HEALING MIGRATIONS (Penyembuhan Mandiri) ---
            run_smart_migration(cursor)
            db.commit()
            
            # --- TAHAP 3: TURBO INDEXING (Akselerasi Pencarian) ---
            optimize_performance(cursor)
            
            # --- TAHAP 4: SECURITY SEEDING ---
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.78: Kolom bulan_rek & Skema Audit Telah Sinkron.")
            
        except Exception as e:
            print(f"❌ Database Init Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """Melahirkan struktur tabel utama jika belum ada."""
    
    # 1. Infrastruktur Rute & Admin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rute_petugas (
            pcez TEXT PRIMARY KEY, 
            petugas TEXT, 
            no_admin TEXT, 
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Riwayat Aktivitas Upload
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            file_name TEXT, 
            file_type TEXT, 
            periode TEXT, 
            row_count INTEGER DEFAULT 0, 
            status TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 3. Master Pelanggan (Data Target)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT UNIQUE, nama TEXT, alamat TEXT, pcez TEXT, rayon TEXT, 
            nominal REAL, periode TEXT, status_lunas INTEGER DEFAULT 0
        )
    """)

    # 4. Tabel Realisasi & Tunggakan
    cursor.execute("CREATE TABLE IF NOT EXISTS master_bayar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, tgl_bayar TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY')")
    cursor.execute("CREATE TABLE IF NOT EXISTS collection_harian (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, pay_dt TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY')")
    cursor.execute("CREATE TABLE IF NOT EXISTS ardebt (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode_bill TEXT, jumlah REAL DEFAULT 0, volume REAL DEFAULT 0, periode TEXT)")
    
    # 5. Keamanan & Audit Lapangan
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, petugas_id TEXT, last_login TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS system_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT, module TEXT, details TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    # Tabel Kunjungan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nomen TEXT NOT NULL, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def run_smart_migration(cursor):
    """Menambah kolom secara otomatis tanpa merusak data lama."""
    
    # --- MIGRASI MASTER PELANGGAN ---
    cursor.execute("PRAGMA table_info(master_pelanggan)")
    existing_master = [row['name'] for row in cursor.fetchall()]
    for col, dtype in {'tarif': 'TEXT', 'kubik': 'REAL DEFAULT 0', 'nomet': 'TEXT'}.items():
        if col not in existing_master:
            cursor.execute(f"ALTER TABLE master_pelanggan ADD COLUMN {col} {dtype}")

    # --- MIGRASI SMART UNDUE (Fix: table master_bayar has no column named bulan_rek) ---
    for table in ['master_bayar', 'collection_harian']:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row['name'] for row in cursor.fetchall()]
        if 'bulan_rek' not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN bulan_rek TEXT")
            print(f"⚙️ Migrasi: Kolom [bulan_rek] ditambahkan ke {table}")
        if 'kategori' not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN kategori TEXT DEFAULT 'HISTORY'")

    # --- MIGRASI KUNJUNGAN PETUGAS ---
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_kunjungan = [row['name'] for row in cursor.fetchall()]
    kunjungan_cols = {
        'petugas_name':'TEXT', 'keterangan':'TEXT', 'foto_path':'TEXT', 
        'latitude':'TEXT', 'longitude':'TEXT', 'periode':'TEXT',
        'nama_snapshot':'TEXT', 'alamat_snapshot':'TEXT',
        'mc':'REAL', 'ardebt':'REAL', 'catatan':'TEXT'
    }
    for col, dtype in kunjungan_cols.items():
        if col not in existing_kunjungan:
            cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")

def optimize_performance(cursor):
    """Turbo Indexing: Akselerasi join data dan filter harian."""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_mc_nomen_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_mb_nomen_per ON master_bayar (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_mb_brek ON master_bayar (bulan_rek)",
        "CREATE INDEX IF NOT EXISTS idx_ch_nomen_per ON collection_harian (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_kj_nomen_per ON kunjungan_petugas (nomen, periode)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
    """Menjamin akses Admin Utama."""
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
