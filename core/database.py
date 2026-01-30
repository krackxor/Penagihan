"""
Core Database Module - Sunter Dashboard Pro (V12.93 Stability Patch)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Fix OperationalError: Penambahan kolom 'created_at' pada tabel 'users' via Smart Migration.
2. Robust Migration Engine: Menjamin kolom 'tipe' dan 'periode' sinkron di semua 
   tabel transaksi guna menghindari Error 500 pada Dashboard.
3. Ultra-High Write Performance: Mengaktifkan temp_store MEMORY dan turbo cache 
   untuk mendukung Bulk Injection (executemany) puluhan ribu baris.
4. Target Lock Integrity: Default value 'MC' pada master_pelanggan memastikan 
   angka target dashboard tidak bergeser saat upload MB.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """ [KONEKSI DATABASE UTAMA DENGAN PRAGMA TURBO] """
    db_path = current_app.config.get('DATABASE') or os.path.join(os.getcwd(), 'penagihan.db')
    try:
        # Timeout ditingkatkan menjadi 100 detik untuk mencegah 'Database is locked'
        conn = sqlite3.connect(db_path, timeout=100)
        conn.row_factory = sqlite3.Row 
        
        # Optimasi SQLite untuk Akses Simultan (Multi-User & Ultra High Speed)
        conn.execute('PRAGMA journal_mode=WAL;')       # Baca & Tulis bersamaan tanpa antri
        conn.execute('PRAGMA synchronous=NORMAL;')     # Keseimbangan speed & data safety
        conn.execute('PRAGMA temp_store=MEMORY;')      # Tabel sementara diproses di RAM
        conn.execute('PRAGMA cache_size=-64000;')      # Alokasikan RAM 64MB untuk buffer database
        conn.execute('PRAGMA journal_size_limit=67108864;') # Batasi log file WAL agar hemat disk
        conn.execute('PRAGMA foreign_keys = ON;')      # Menjaga integritas relasi antar tabel
        
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
            print("✅ Database V12.93: Engine Ultra-Speed & Schema User Telah Sinkron.")
            
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
            nomen TEXT, nama TEXT, alamat TEXT, pcez TEXT, rayon TEXT, 
            nominal REAL, periode TEXT, status_lunas INTEGER DEFAULT 0,
            no_hp TEXT DEFAULT '-', tgl_lunas TEXT, tipe TEXT DEFAULT 'MC'
        )
    """)

    # 4. Tabel Realisasi & Tunggakan
    cursor.execute("CREATE TABLE IF NOT EXISTS master_bayar (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, tgl_bayar TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY', bulan_rek TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS collection_harian (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, pay_dt TEXT, nominal REAL DEFAULT 0, periode TEXT, kategori TEXT DEFAULT 'HISTORY', bulan_rek TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS ardebt (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode_bill TEXT, jumlah REAL DEFAULT 0, volume REAL DEFAULT 0, periode TEXT)")
    
    # 5. Keamanan & Audit Lapangan
    # Ditambahkan created_at pada struktur dasar untuk mencegah error di masa depan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT UNIQUE, 
            password TEXT, 
            role TEXT, 
            petugas_id TEXT, 
            last_login TIMESTAMP, 
            no_hp TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
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
    
    master_cols = {
        'tarif': 'TEXT', 
        'kubik': 'REAL DEFAULT 0', 
        'nomet': 'TEXT', 
        'no_hp': 'TEXT DEFAULT "-"',
        'tgl_lunas': 'TEXT',
        'tipe': "TEXT DEFAULT 'MC'"
    }
    for col, dtype in master_cols.items():
        if col not in existing_master:
            cursor.execute(f"ALTER TABLE master_pelanggan ADD COLUMN {col} {dtype}")
            print(f"⚙️ Migrasi: Kolom [{col}] ditambahkan ke master_pelanggan")

    # --- MIGRASI USER (FIX created_at) ---
    cursor.execute("PRAGMA table_info(users)")
    existing_users = [row['name'] for row in cursor.fetchall()]
    
    if 'no_hp' not in existing_users:
        cursor.execute("ALTER TABLE users ADD COLUMN no_hp TEXT")
        
    if 'created_at' not in existing_users:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        print("⚙️ Migrasi: Kolom [created_at] ditambahkan ke tabel users")

    # --- MIGRASI SMART TRANS-PERIOD ---
    for table in ['master_bayar', 'collection_harian']:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row['name'] for row in cursor.fetchall()]
        if 'bulan_rek' not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN bulan_rek TEXT")
        if 'kategori' not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN kategori TEXT DEFAULT 'HISTORY'")
        if 'periode' not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")

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
        "CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan (pcez)",
        "CREATE INDEX IF NOT EXISTS idx_mc_tipe ON master_pelanggan (tipe)",
        "CREATE INDEX IF NOT EXISTS idx_mb_nomen_per ON master_bayar (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_mb_brek ON master_bayar (bulan_rek)",
        "CREATE INDEX IF NOT EXISTS idx_mb_kat ON master_bayar (kategori)",
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
