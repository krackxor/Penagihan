"""
Core Database Module - Sunter Dashboard Pro (V6.8 Sinergi Snapshot Edition)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi (Anti-Lock) untuk akses massal petugas.
2. Self-Healing Migration: Otomatis menambah kolom Snapshot (Nomet, Nama, Alamat) & GPS.
3. Integrity Guard: Menjamin keamanan relasi antar tabel dengan Foreign Keys aktif.
4. Smart Seeder: Menjamin ketersediaan akun admin pusat saat inisialisasi pertama.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    FUNGSI: Membuka koneksi ke Database SQLite dengan Optimasi Server.
    LOGIKA: 
    - WAL Mode: Memungkinkan Admin upload Excel sambil Petugas lapor di lapangan secara bersamaan.
    - row_factory: Memungkinkan akses data menggunakan nama kolom (contoh: row['nama']).
    - Timeout: Memberikan toleransi 30 detik agar tidak terjadi 'Database Locked'.
    """
    db_path = current_app.config.get('DATABASE')
    
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        
        # --- BLOK OPTIMASI SINERGI KINERJA TINGGI ---
        conn.execute('PRAGMA journal_mode=WAL;')       # Anti-Macet saat banyak user
        conn.execute('PRAGMA synchronous=NORMAL;')     # Kecepatan tulis maksimal
        conn.execute('PRAGMA foreign_keys = ON;')      # Validasi relasi antar tabel
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    FUNGSI: Inisialisasi Otomatis & Auto-Migration (Autopilot).
    LOGIKA: Menjalankan urutan pembuatan tabel, migrasi kolom baru, dan seeder admin.
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Jalankan Skema Dasar (Jika file ada)
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. Pastikan Tabel Inti Tersedia
            check_and_create_tables(cursor)

            # 3. JALANKAN MIGRASI SMART (Penambahan Kolom Snapshot & GPS)
            run_smart_migration(cursor)

            # 4. Buat Akun Admin Default
            seed_default_admin(cursor)

            db.commit()
            print("✅ Sinergi V6.8: Database Autopilot Siap Digunakan.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """
    HELPER: Memastikan tabel-tabel krusial selalu tersedia di database.
    """
    # Tabel History Laporan Kunjungan (Pusat Data Lapangan)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            keterangan TEXT,
            catatan TEXT,
            foto_path TEXT,
            mc REAL DEFAULT 0,
            ardebt REAL DEFAULT 0,
            periode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Upload History (Audit Log Admin)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT, file_type TEXT, periode TEXT,
            row_count INTEGER, status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def run_smart_migration(cursor):
    """
    HELPER: Mekanisme Self-Healing untuk menambah kolom baru tanpa merusak data.
    PENTING: Menambahkan kolom Snapshot (Nomet, Nama, Alamat) dan GPS (Lat, Lng).
    """
    # --- 1. Migrasi Tabel kunjungan_petugas (Fitur Snapshot & GPS) ---
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_cols = [row['name'] for row in cursor.fetchall()]
    
    # Daftar kolom baru untuk V6.8
    new_columns = {
        'nomet': 'TEXT',                # Snapshot No Meter
        'nama_snapshot': 'TEXT',        # Snapshot Nama Pelanggan
        'alamat_snapshot': 'TEXT',      # Snapshot Alamat Pelanggan
        'latitude': 'TEXT',             # Koordinat GPS Lat
        'longitude': 'TEXT',            # Koordinat GPS Lng
        'no_hp': 'TEXT',                # Snapshot HP Pelanggan
        'volume': 'REAL DEFAULT 0'      # Snapshot Pemakaian Air
    }
    
    for col, dtype in new_columns.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")
            print(f"🔧 Migrasi Sinergi: Kolom [{col}] ditambahkan ke kunjungan_petugas")

    # --- 2. Migrasi Tabel master_pelanggan ---
    cursor.execute("PRAGMA table_info(master_pelanggan)")
    existing_mc = [row['name'] for row in cursor.fetchall()]
    
    mc_updates = {
        'alamat': 'TEXT', 
        'nomet': 'TEXT', 
        'kubik': 'REAL DEFAULT 0'
    }
    
    for col, dtype in mc_updates.items():
        if col not in existing_mc:
            cursor.execute(f"ALTER TABLE master_pelanggan ADD COLUMN {col} {dtype}")
            print(f"🔧 Migrasi Sinergi: Kolom [{col}] ditambahkan ke master_pelanggan")

def seed_default_admin(cursor):
    """
    HELPER: Pintu Darurat - Menjamin akun admin pusat selalu ada.
    Default: admin_sunter / admin123
    """
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))
        print(f"👤 Smart Seeder: Akun Admin '{username}' siap.")

def get_db():
    """
    HELPER: Global Flask Database Access.
    """
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
