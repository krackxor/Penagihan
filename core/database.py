"""
Core Database Module - Sunter Dashboard Pro (V3.8 Sinergi Edition)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi (Anti-Lock) untuk akses massal petugas.
2. Auto-Migration Engine: Mendeteksi dan menambah kolom baru secara otomatis (Self-Healing).
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
    - Timeout: Memberikan toleransi 30 detik saat database sedang sibuk.
    """
    db_path = current_app.config.get('DATABASE')
    
    # Fallback ke direktori root jika path di config tidak terbaca
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        
        # --- BLOK OPTIMASI SINERGI KINERJA TINGGI ---
        conn.execute('PRAGMA journal_mode=WAL;')       # Write-Ahead Logging (Anti-Database-Locked)
        conn.execute('PRAGMA synchronous=NORMAL;')     # Keseimbangan antara keamanan data dan kecepatan
        conn.execute('PRAGMA foreign_keys = ON;')      # Menjaga relasi antar tabel tetap konsisten
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    FUNGSI: Inisialisasi Otomatis & Auto-Migration (Autopilot).
    LOGIKA:
    1. Membaca skema dasar dari file 'schema.sql'.
    2. Menjalankan 'Self-Healing' untuk membuat tabel yang hilang.
    3. Menambah kolom secara otomatis jika ada pembaruan fitur (Migration).
    4. Menyediakan akun admin default jika database masih baru.
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. EKSEKUSI SKEMA UTAMA (Jika file schema.sql tersedia)
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. AUTO-REPAIR TABEL (Menjamin tabel inti selalu tersedia)
            check_and_create_tables(cursor)

            # 3. SMART COLUMN MIGRATION (Menambah kolom baru tanpa merusak data lama)
            # Logika ini mencegah error 'has no column named' saat ada update fitur.
            run_smart_migration(cursor)

            # 4. ADMIN SEEDER (Pintu Darurat)
            seed_default_admin(cursor)

            db.commit()
            print("✅ Autopilot: Database Sinergi V3.8 siap digunakan.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """
    HELPER: Memastikan tabel-tabel krusial yang sering menyebabkan error 500 dibuat otomatis.
    """
    # Tabel History untuk audit log admin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT, file_type TEXT, periode TEXT,
            row_count INTEGER, status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Collection untuk setoran harian petugas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_harian (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL, notag TEXT,
            bill_period TEXT, bill_reason TEXT,
            nominal REAL DEFAULT 0, pay_dt TEXT,
            freeze_dttm TEXT, vol_collect REAL DEFAULT 0,
            periode TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def run_smart_migration(cursor):
    """
    HELPER: Menambah kolom baru ke tabel yang sudah ada secara dinamis.
    Ini adalah kunci agar aplikasi tidak blank saat Anda menambah fitur baru.
    """
    # --- Migrasi Kolom Master Pelanggan (MC) ---
    cursor.execute("PRAGMA table_info(master_pelanggan)")
    existing_mc = [row['name'] for row in cursor.fetchall()]
    
    mc_updates = {
        'alamat': 'TEXT',            # Gabungan alamat lengkap
        'rayon': 'TEXT',             # Kode rute (34/35)
        'pc': 'TEXT',                # Komponen ZONA_NOVAK
        'ez': 'TEXT',                # Komponen ZONA_NOVAK
        'blok': 'TEXT',              # Komponen ZONA_NOVAK
        'is_high_value': 'INTEGER DEFAULT 0' # Filter penagihan besar
    }
    
    for col, dtype in mc_updates.items():
        if col not in existing_mc:
            cursor.execute(f"ALTER TABLE master_pelanggan ADD COLUMN {col} {dtype}")
            print(f"🔧 Migrasi: Kolom [{col}] ditambahkan ke master_pelanggan")

def seed_default_admin(cursor):
    """
    HELPER: Menjamin sistem memiliki minimal satu akun Admin Pusat.
    Default Login: admin_sunter / admin123
    """
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))
        print(f"👤 Smart Seeder: Akun '{username}' (Pass: admin123) berhasil dibuat.")

def get_db():
    """
    HELPER: Digunakan di dalam rute Flask untuk mengambil koneksi database aktif.
    Menjamin efisiensi memori dengan menggunakan objek 'g' (Global Flask).
    """
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
