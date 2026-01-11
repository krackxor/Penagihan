"""
Core Database Module - Sunter Dashboard Pro (V7.4 Sinergi Final Edition)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi untuk akses massal petugas.
2. Self-Healing Migration V4: Perbaikan otomatis kolom NOMET di master & kunjungan.
3. Performance Indexing: Turbo charging untuk pencarian PCEZ dan NOMET.
4. Audit Trail Guard: Pembersihan otomatis data history untuk mencegah Error 500.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    [FUNGSI: KONEKSI DATABASE UTAMA]
    Membuka jalur komunikasi ke SQLite dengan mode WAL untuk efisiensi tinggi.
    """
    db_path = current_app.config.get('DATABASE')
    
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        
        # --- BLOK OPTIMASI KINERJA TINGGI ---
        conn.execute('PRAGMA journal_mode=WAL;')       # Anti-Lock untuk akses simultan
        conn.execute('PRAGMA synchronous=NORMAL;')     # Kecepatan I/O maksimal
        conn.execute('PRAGMA foreign_keys = ON;')      # Menjamin integritas relasi
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    [FUNGSI: INISIALISASI OTOMATIS]
    Menyiapkan infrastruktur database, migrasi kolom, dan optimasi performa.
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Eksekusi skema dasar SQL
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. Proteksi struktur tabel minimal
            check_and_create_tables(cursor)

            # 3. Jalankan Migrasi Self-Healing (Nomet & History Guard)
            run_smart_migration(cursor)
            
            # 4. Optimasi Turbo Indexing (Nomet & PCEZ Sync)
            optimize_performance(cursor)

            # 5. Seeding Akun Admin Pusat
            seed_default_admin(cursor)

            db.commit()
            print("✅ Sinergi V7.4: Infrastruktur Database & Nomet Sync Telah Aktif.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """ Menjamin tabel-tabel krusial tersedia agar API tidak Error 500. """
    # Tabel Laporan Kunjungan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Riwayat Upload
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT, file_type TEXT, periode TEXT,
            row_count INTEGER DEFAULT 0, status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def run_smart_migration(cursor):
    """
    [HELPER: MEKANISME SELF-HEALING V4]
    Menambah kolom baru secara otomatis dan menjamin NOMET tersedia.
    """
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
            print(f"🔧 Kunjungan: Kolom [{col}] ditambahkan.")

    # --- 2. MIGRASI TABEL MASTER (NOMET GUARD) ---
    # Memastikan kolom nomet tersedia untuk menampung data alfanumerik dari Excel
    cursor.execute("PRAGMA table_info(master_pelanggan)")
    existing_master = [row['name'] for row in cursor.fetchall()]
    if 'nomet' not in existing_master:
        cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN nomet TEXT")
        print("🔧 Master: Kolom [nomet] ditambahkan otomatis.")

    # --- 3. AUDIT TRAIL GUARD ---
    # Memperbaiki data history yang NULL agar halaman riwayat tidak crash
    cursor.execute("UPDATE upload_history SET row_count = 0 WHERE row_count IS NULL")
    cursor.execute("UPDATE upload_history SET status = 'FAILED' WHERE status IS NULL")

def optimize_performance(cursor):
    """
    [HELPER: TURBO LOADING & SYNC]
    Membuat Index pada NOMET dan PCEZ agar deteksi data instan.
    """
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_master_nomen ON master_pelanggan (nomen)",
        "CREATE INDEX IF NOT EXISTS idx_master_nomet ON master_pelanggan (nomet)",
        "CREATE INDEX IF NOT EXISTS idx_master_pcez ON master_pelanggan (pcez)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas (nomen)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_periode ON kunjungan_petugas (periode)",
        "CREATE INDEX IF NOT EXISTS idx_history_date ON upload_history (created_at)"
    ]
    for idx in indices:
        cursor.execute(idx)
    print("🚀 Performa: Indexing Turbo (Nomet & Petugas Sync) Aktif.")

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
        print(f"👤 Seeder: Akun Admin '{username}' siap (Default: admin123).")

def get_db():
    """ Mengambil koneksi database yang aktif. """
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
