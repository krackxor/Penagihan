"""
Core Database Module - Sunter Dashboard Pro (V12.98 Ultra-Sync)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX: Unique Constraint Error pada users (Defensive Seeding).
2. ✅ STABILITY: Peningkatan timeout ke 300 detik & cache turbo untuk Bulk Upload.
3. ✅ CONFLICT RESOLVER: INSERT OR IGNORE pada seeding default admin.
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
            
            # --- TAHAP 1: INFRASTRUKTUR DASAR & TRIGGER ---
            check_and_create_tables(cursor)
            db.commit() 

            # --- TAHAP 2: SELF-HEALING MIGRATIONS (FIX 500 ERROR) ---
            run_smart_migration(cursor)
            db.commit()
            
            # --- TAHAP 3: TURBO INDEXING ---
            optimize_performance(cursor)
            
            # --- TAHAP 4: SECURITY SEEDING ---
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database V12.98: Engine High-Load & History Sync Aktif.")
            
        except Exception as e:
            # Jika error tetap terjadi karena constraint, kita log namun jangan hentikan app
            print(f"⚠️ Database Init Warning/Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """Melahirkan struktur tabel utama & Trigger Otomatis."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rute_petugas (
            pcez TEXT PRIMARY KEY, petugas TEXT, no_admin TEXT, 
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, nama TEXT, 
            alamat TEXT, pcez TEXT, rayon TEXT, nominal REAL, periode TEXT, 
            status_lunas INTEGER DEFAULT 0, no_hp TEXT DEFAULT '-', 
            tgl_lunas TEXT, tipe TEXT DEFAULT 'MC'
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
    cursor.execute("CREATE TABLE IF NOT EXISTS ardebt (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, periode_bill TEXT, jumlah REAL DEFAULT 0, volume REAL DEFAULT 0, periode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, petugas_id TEXT, last_login TIMESTAMP, no_hp TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS system_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT, module TEXT, details TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

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
    """Fungsi Self-Healing: Menjamin kolom Janji Bayar & Snapshot tersedia."""
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_kunjungan = [row['name'] for row in cursor.fetchall()]
    kunjungan_cols = {
        'nomet': 'TEXT', 'no_hp': 'TEXT', 'petugas_name':'TEXT', 
        'keterangan':'TEXT', 'foto_path':'TEXT', 'latitude':'TEXT', 
        'longitude':'TEXT', 'periode':'TEXT', 'nama_snapshot':'TEXT', 
        'alamat_snapshot':'TEXT', 'mc':'REAL', 'ardebt':'REAL', 
        'catatan':'TEXT', 'janji_bayar_dt': 'TEXT'
    }
    for col, dtype in kunjungan_cols.items():
        if col not in existing_kunjungan:
            cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")

    cursor.execute("PRAGMA table_info(master_pelanggan)")
    existing_master = [row['name'] for row in cursor.fetchall()]
    master_cols = {'tarif': 'TEXT', 'kubik': 'REAL DEFAULT 0', 'nomet': 'TEXT', 'no_hp': 'TEXT DEFAULT "-"', 'tgl_lunas': 'TEXT', 'tipe': "TEXT DEFAULT 'MC'"}
    for col, dtype in master_cols.items():
        if col not in existing_master:
            cursor.execute(f"ALTER TABLE master_pelanggan ADD COLUMN {col} {dtype}")

    cursor.execute("PRAGMA table_info(users)")
    if 'no_hp' not in [r['name'] for r in cursor.fetchall()]:
        cursor.execute("ALTER TABLE users ADD COLUMN no_hp TEXT")
    
    for table in ['master_bayar', 'collection_harian']:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row['name'] for row in cursor.fetchall()]
        if 'bulan_rek' not in cols: cursor.execute(f"ALTER TABLE {table} ADD COLUMN bulan_rek TEXT")
        if 'periode' not in cols: cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")

def optimize_performance(cursor):
    """Turbo Indexing untuk Akselerasi Query Lintas Periode."""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_mc_nomen_per ON master_pelanggan (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_mb_nomen_per ON master_bayar (nomen, periode)",
        "CREATE INDEX IF NOT EXISTS idx_kj_nomen_per ON kunjungan_petugas (nomen, periode)"
    ]
    for idx in indices:
        cursor.execute(idx)

def seed_default_admin(cursor):
    """Menjamin akses Admin Utama tanpa menyebabkan UNIQUE constraint error."""
    username = 'admin_sunter'
    # Menggunakan INSERT OR IGNORE sebagai proteksi lapis kedua
    hashed_pw = generate_password_hash('admin123')
    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password, role, petugas_id) 
        VALUES (?, ?, ?, ?)
    """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))

def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
