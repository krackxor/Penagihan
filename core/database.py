"""
Core Database Module - Sunter Dashboard Pro (V7.0 Sinergi Final Edition)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi (Anti-Lock) untuk akses massal petugas.
2. Self-Healing Migration V2: Perbaikan otomatis semua kolom (mc, ardebt, catatan, dll).
3. Integrity Guard: Menjamin keamanan relasi antar tabel dengan Foreign Keys aktif.
4. Smart Seeder: Menjamin ketersediaan akun admin pusat saat inisialisasi pertama.
"""

import sqlite3
import os
from flask import current_app, g
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    [FUNGSI: KONEKSI DATABASE UTAMA]
    Kegunaan: Membuka jalur komunikasi ke SQLite dengan proteksi 'Locked Database'.
    Logika:
    - WAL Mode: Agar proses baca dan tulis bisa berjalan bersamaan (Petugas lapor vs Admin upload).
    - Synchronous Normal: Meningkatkan kecepatan tulis tanpa mengorbankan integritas data.
    """
    db_path = current_app.config.get('DATABASE')
    
    # Fallback jika path di konfigurasi tidak ditemukan
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row # Memungkinkan akses data dengan nama kolom (contoh: row['nama'])
        
        # --- BLOK OPTIMASI SINERGI KINERJA TINGGI ---
        conn.execute('PRAGMA journal_mode=WAL;')       # Mencegah database terkunci saat akses bersamaan
        conn.execute('PRAGMA synchronous=NORMAL;')     # Mengoptimalkan kecepatan transaksi
        conn.execute('PRAGMA foreign_keys = ON;')      # Menjaga integritas relasi antar tabel
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    [FUNGSI: INISIALISASI & MIGRASI OTOMATIS]
    Kegunaan: Menjalankan skema awal dan memperbaiki struktur tabel secara mandiri.
    Alur: Schema.sql -> Check Tables -> Run Migration -> Seed Admin.
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Eksekusi Skema Dasar (Khusus untuk instalasi database baru)
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. Verifikasi Keberadaan Tabel Inti
            check_and_create_tables(cursor)

            # 3. JALANKAN SELF-HEALING (Solusi permanen untuk kolom mc, catatan, ardebt, dll)
            run_smart_migration(cursor)

            # 4. Pastikan Akun Administrator Selalu Tersedia
            seed_default_admin(cursor)

            db.commit()
            print("✅ Sinergi V7.0: Database Berhasil Diperbarui & Siap Digunakan.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """
    [HELPER: VERIFIKASI STRUKTUR TABEL]
    Kegunaan: Menjamin tabel minimal tersedia sebelum proses migrasi kolom dilakukan.
    """
    # Pastikan tabel kunjungan petugas sudah ada
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Pastikan tabel riwayat upload admin sudah ada
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
    [HELPER: MIGRASI KOLOM DINAMIS]
    Kegunaan: MENAMBAH KOLOM YANG KURANG SECARA OTOMATIS TANPA MERUSAK DATA LAMA.
    Penting: Menangani error 'no such column' untuk mc, ardebt, dan catatan.
    """
    # --- 1. Audit Tabel kunjungan_petugas ---
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_cols = [row['name'] for row in cursor.fetchall()]
    
    # Daftar kolom wajib untuk fitur Snapshot & GPS V7.0
    new_columns = {
        'mc': 'REAL DEFAULT 0',         # Saldo MC saat kunjungan
        'ardebt': 'REAL DEFAULT 0',     # Saldo Piutang lama saat kunjungan
        'catatan': 'TEXT',              # Komentar tambahan petugas
        'keterangan': 'TEXT',           # Hasil koordinasi lapangan
        'foto_path': 'TEXT',            # Nama file bukti foto
        'nomet': 'TEXT',                # Snapshot Nomor Meter
        'nama_snapshot': 'TEXT',        # Snapshot Nama Pelanggan
        'alamat_snapshot': 'TEXT',      # Snapshot Alamat Lengkap
        'latitude': 'TEXT',             # Koordinat Lintang GPS
        'longitude': 'TEXT',            # Koordinat Bujur GPS
        'no_hp': 'TEXT',                # Snapshot No HP Pelanggan
        'volume': 'REAL DEFAULT 0',     # Snapshot Angka Meter/Kubikasi
        'periode': 'TEXT'               # Periode Laporan (MM-YYYY)
    }
    
    for col, dtype in new_columns.items():
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")
                print(f"🔧 Migrasi Sinergi: Kolom [{col}] berhasil ditambahkan otomatis.")
            except Exception as e:
                print(f"⚠️ Gagal migrasi kolom {col}: {e}")

    # --- 2. Audit Tabel master_pelanggan ---
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
    [HELPER: PEMBUAT AKUN ADMIN OTOMATIS]
    Kegunaan: Menjamin sistem tidak terkunci jika akun admin tidak sengaja terhapus.
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
        print(f"👤 Smart Seeder: Akun Administrator Default '{username}' siap.")

def get_db():
    """
    [HELPER: GLOBAL DATABASE ACCESS]
    Kegunaan: Dipanggil di file lain untuk mendapatkan koneksi database aktif.
    """
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
