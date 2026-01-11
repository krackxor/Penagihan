"""
Core Database Module - Sunter Dashboard Pro (V7.2 Sinergi Final Edition)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi (Anti-Lock) untuk akses massal petugas.
2. Self-Healing Migration V3: Perbaikan otomatis kolom di tabel kunjungan & upload_history.
3. Performance Indexing: Penambahan index pada kolom periode untuk mempercepat dashboard.
4. Secure Seeder: Menjamin ketersediaan akun admin dengan hashing yang kuat.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    [FUNGSI: KONEKSI DATABASE UTAMA]
    Kegunaan: Membuka jalur komunikasi ke file database SQLite.
    Logika Cerdas:
    - WAL Mode: Memungkinkan Admin upload Excel & Petugas lapor secara bersamaan tanpa 'Database Locked'.
    - Row Factory: Mengubah hasil query menjadi format dictionary agar bisa dipanggil lewat nama kolom.
    """
    db_path = current_app.config.get('DATABASE')
    
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        
        # --- BLOK OPTIMASI KINERJA TINGGI ---
        conn.execute('PRAGMA journal_mode=WAL;')       # Aktifkan Write-Ahead Logging (Anti-Lock)
        conn.execute('PRAGMA synchronous=NORMAL;')     # Mengurangi beban I/O untuk kecepatan maksimal
        conn.execute('PRAGMA foreign_keys = ON;')      # Menjamin integritas relasi antar tabel
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    [FUNGSI: INISIALISASI OTOMATIS]
    Kegunaan: Mempersiapkan infrastruktur database saat aplikasi dijalankan.
    Alur: Load Config -> Create Tables -> Smart Migration -> Turbo Indexing.
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Eksekusi skema dasar dari file SQL
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. Proteksi struktur tabel utama
            check_and_create_tables(cursor)

            # 3. Jalankan Migrasi Self-Healing (Perbaikan Kolom)
            run_smart_migration(cursor)
            
            # 4. Optimasi Turbo Indexing
            optimize_performance(cursor)

            # 5. Seeding Akun Admin
            seed_default_admin(cursor)

            db.commit()
            print("✅ Sinergi V7.2: Database & Infrastruktur Siap Digunakan.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """
    [HELPER: PENJAGA STRUKTUR TABEL]
    Menjamin tabel-tabel krusial tersedia agar API tidak menghasilkan Error 500.
    """
    # Tabel Kunjungan Lapangan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Riwayat Upload (Audit Trail)
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

def run_smart_migration(cursor):
    """
    [HELPER: MEKANISME SELF-HEALING V3]
    Menambah kolom baru secara otomatis dan memperbaiki nilai NULL pada kolom lama.
    """
    # --- MIGRASI TABEL KUNJUNGAN ---
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

    # --- MIGRASI & CLEANING TABEL HISTORY ---
    # Perbaikan Error 500: Menjamin row_count tidak NULL
    cursor.execute("UPDATE upload_history SET row_count = 0 WHERE row_count IS NULL")
    print("🧹 Database Clean: Nilai NULL pada row_count telah dibersihkan.")

def optimize_performance(cursor):
    """
    [HELPER: TURBO LOADING]
    Membuat Index agar pencarian di puluhan ribu data tetap instan.
    """
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_master_nomen ON master_pelanggan (nomen)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas (nomen)",
        "CREATE INDEX IF NOT EXISTS idx_kunjungan_periode ON kunjungan_petugas (periode)",
        "CREATE INDEX IF NOT EXISTS idx_history_date ON upload_history (created_at)"
    ]
    for idx in indices:
        cursor.execute(idx)
    print("🚀 Performa: Indexing Turbo Aktif.")

def seed_default_admin(cursor):
    """
    [HELPER: PENGAMAN AKSES]
    Membuat akun admin pusat jika belum tersedia.
    """
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
    """Mengambil koneksi database global Flask."""
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
