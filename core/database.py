"""
Core Database Module - Sunter Dashboard Pro
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi agar aplikasi tidak 'Database Locked' saat banyak petugas lapor.
2. Auto-Migrasi Cerdas: Mendeteksi dan menambah kolom baru otomatis tanpa merusak data lama.
3. Integrity Guard: Menjamin keamanan relasi antar tabel (Foreign Keys).
"""

import sqlite3
import os
from flask import current_app
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    MEMBUAT KONEKSI DATABASE (SMART CONFIG):
    Menggunakan WAL (Write-Ahead Logging) Mode untuk memungkinkan 
    proses baca (dashboard admin) dan tulis (laporan petugas) berjalan beriringan.
    """
    db_path = current_app.config.get('DATABASE')
    
    # Fallback autopilot jika path tidak ditemukan di config
    if not db_path:
        db_path = os.path.join(current_app.root_path, 'penagihan.db')
    
    try:
        # Timeout 30 detik untuk menunggu jika database sedang sibuk
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row # Memungkinkan akses data menggunakan nama kolom
        
        # --- BLOK OPTIMASI SINERGI ---
        conn.execute('PRAGMA journal_mode=WAL;')      # Mode tulis-cepat
        conn.execute('PRAGMA synchronous=NORMAL;')    # Keseimbangan keamanan & kecepatan
        conn.execute('PRAGMA foreign_keys = ON;')     # Menjaga integritas relasi data
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    INISIALISASI & AUTO-MIGRASI (AUTOPILOT):
    Mendeteksi struktur tabel saat aplikasi dinyalakan dan memperbaruinya otomatis.
    Sinergi: Memungkinkan penambahan fitur baru tanpa perlu install ulang database.
    """
    with app.app_context():
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Jalankan Skema Dasar dari file SQL (jika ada)
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. LOGIKA AUTO-MIGRASI (SMART FIXER)
            # Memeriksa kolom satu-per-satu untuk menjamin kompatibilitas versi terbaru.
            
            # --- Migrasi Tabel master_pelanggan ---
            cursor.execute("PRAGMA table_info(master_pelanggan)")
            cols = [row['name'] for row in cursor.fetchall()]
            check_and_add_columns(cursor, "master_pelanggan", cols, {
                'rayon': 'TEXT',
                'nomet': 'TEXT',
                'periode': 'TEXT',
                'volume': 'REAL DEFAULT 0'
            })

            # --- Migrasi Tabel rute_petugas ---
            cursor.execute("PRAGMA table_info(rute_petugas)")
            cols = [row['name'] for row in cursor.fetchall()]
            if 'no_admin' not in cols:
                cursor.execute("ALTER TABLE rute_petugas ADD COLUMN no_admin TEXT DEFAULT '628123456789'")

            # --- Migrasi Tabel kunjungan_petugas (Geo-Tagging & Snapshot) ---
            cursor.execute("PRAGMA table_info(kunjungan_petugas)")
            cols = [row['name'] for row in cursor.fetchall()]
            migrasi_kunjungan = {
                'mc': 'REAL DEFAULT 0',
                'ardebt': 'REAL DEFAULT 0',
                'no_hp': 'TEXT',
                'latitude': 'TEXT',
                'longitude': 'TEXT',
                'periode': 'TEXT'
            }
            check_and_add_columns(cursor, "kunjungan_petugas", cols, migrasi_kunjungan)

            # 3. Sinkronisasi Akun Admin Default (Keamanan Sesi)
            seed_default_admin(cursor)

            db.commit()
            print("✅ Autopilot: Database inisialisasi & migrasi berhasil.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if 'db' in locals(): db.rollback()
        finally:
            if 'db' in locals(): db.close()

def check_and_add_columns(cursor, table_name, existing_cols, new_cols_map):
    """
    HELPER SMART MIGRATION:
    Menghindari error 'Duplicate Column' saat melakukan migrasi berulang.
    """
    for col, data_type in new_cols_map.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {data_type}")
            print(f"🔧 Migrasi: Kolom [{col}] ditambahkan ke tabel [{table_name}]")

def seed_default_admin(cursor):
    """
    SEEDER CERDAS:
    Menjamin akses sistem tidak terkunci dengan menyediakan akun admin default.
    """
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        # Password default: admin123 (Segera ganti setelah login pertama)
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))
        print(f"👤 Smart Seeder: Akun '{username}' siap digunakan.")
