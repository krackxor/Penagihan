"""
Core Database Module - Sunter Dashboard Pro (V6.9 Sinergi Fix Edition)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi (Anti-Lock) untuk akses massal petugas.
2. Self-Healing Migration: Perbaikan otomatis kolom 'catatan' dan Snapshot GPS.
3. Integrity Guard: Menjamin keamanan relasi antar tabel dengan Foreign Keys aktif.
4. Smart Seeder: Menjamin ketersediaan akun admin pusat saat inisialisasi pertama.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    [FUNGSI: KONEKSI DATABASE]
    Kegunaan: Membuka jalur komunikasi ke SQLite dengan proteksi 'Locked Database'.
    """
    db_path = current_app.config.get('DATABASE')
    
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        
        # --- BLOK OPTIMASI SINERGI KINERJA TINGGI ---
        conn.execute('PRAGMA journal_mode=WAL;')       # Anti-Macet (Write Ahead Logging)
        conn.execute('PRAGMA synchronous=NORMAL;')     # Keseimbangan kecepatan & keamanan
        conn.execute('PRAGMA foreign_keys = ON;')      # Aktifkan proteksi relasi tabel
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    [FUNGSI: INISIALISASI & MIGRASI]
    Kegunaan: Menjalankan skema dasar dan memperbaiki struktur tabel yang tertinggal (Autopilot).
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Jalankan Skema Dasar (Jika database masih nol/kosong)
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. Periksa dan buat tabel inti jika belum ada
            check_and_create_tables(cursor)

            # 3. JALANKAN SELF-HEALING (Menambah kolom catatan, nomet, gps secara otomatis)
            run_smart_migration(cursor)

            # 4. Siapkan Akun Administrator
            seed_default_admin(cursor)

            db.commit()
            print("✅ Sinergi V6.9: Database Autopilot Siap & Kolom Telah Diperbaiki.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """
    [HELPER: VERIFIKASI TABEL]
    Kegunaan: Menjamin tabel minimal tersedia sebelum aplikasi memproses data.
    """
    # Tabel Kunjungan Petugas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            keterangan TEXT,
            foto_path TEXT,
            mc REAL DEFAULT 0,
            ardebt REAL DEFAULT 0,
            periode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Riwayat Upload
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
    [HELPER: MIGRASI OTOMATIS]
    Kegunaan: MENAMBAH KOLOM YANG HILANG (Catatan, GPS, Snapshot) TANPA MENGHAPUS DATA.
    """
    # --- 1. Perbaikan Tabel kunjungan_petugas ---
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_cols = [row['name'] for row in cursor.fetchall()]
    
    # Daftar kolom yang sering menyebabkan error jika tidak ada
    new_columns = {
        'catatan': 'TEXT',              # <-- SOLUSI ERROR 'NO SUCH COLUMN: CATATAN'
        'nomet': 'TEXT',                # Snapshot No Meter
        'nama_snapshot': 'TEXT',        # Snapshot Nama
        'alamat_snapshot': 'TEXT',      # Snapshot Alamat
        'latitude': 'TEXT',             # Koordinat GPS Lat
        'longitude': 'TEXT',            # Koordinat GPS Lng
        'no_hp': 'TEXT',                # Snapshot No HP
        'volume': 'REAL DEFAULT 0'      # Snapshot Kubikasi
    }
    
    for col, dtype in new_columns.items():
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")
                print(f"🔧 Migrasi: Kolom [{col}] berhasil ditambahkan otomatis.")
            except Exception as e:
                print(f"⚠️ Gagal migrasi kolom {col}: {e}")

    # --- 2. Perbaikan Tabel master_pelanggan ---
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
            print(f"🔧 Migrasi: Kolom [{col}] ditambahkan ke master_pelanggan")

def seed_default_admin(cursor):
    """
    [HELPER: ADMIN SEEDER]
    Kegunaan: Menjamin ada akses masuk saat database baru dibuat.
    """
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))
        print(f"👤 Smart Seeder: Akun Admin '{username}' siap digunakan.")

def get_db():
    """
    [HELPER: AKSES GLOBAL]
    """
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
