"""
Core Database Module - Sunter Dashboard Pro (V7.1 Sinergi Final Edition)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi (Anti-Lock) untuk akses massal petugas.
2. Self-Healing Migration V2: Perbaikan otomatis semua kolom (mc, ardebt, catatan, dll).
3. Performance Indexing: Menambahkan Index pada kolom krusial agar loading data secepat kilat.
4. Smart Seeder: Menjamin ketersediaan akun admin pusat saat inisialisasi pertama.
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
    
    # Menentukan lokasi file database secara otomatis
    if not db_path:
        db_path = os.path.join(os.getcwd(), 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        
        # --- BLOK OPTIMASI KINERJA TINGGI ---
        conn.execute('PRAGMA journal_mode=WAL;')       # Aktifkan Write-Ahead Logging (Sangat penting untuk sinergi)
        conn.execute('PRAGMA synchronous=NORMAL;')     # Mengurangi beban disk I/O untuk kecepatan maksimal
        conn.execute('PRAGMA foreign_keys = ON;')      # Memastikan integritas data antar tabel terjaga
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    [FUNGSI: INISIALISASI OTOMATIS]
    Kegunaan: Mempersiapkan infrastruktur database saat aplikasi pertama kali dijalankan.
    Alur Kerja: Membaca skema -> Membuat tabel -> Migrasi kolom baru -> Optimasi Index.
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Menjalankan skema SQL dasar jika tersedia
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. Verifikasi tabel-tabel utama agar tidak terjadi error 500
            check_and_create_tables(cursor)

            # 3. Jalankan Migrasi Kolom (Snapshot, GPS, Saldo)
            run_smart_migration(cursor)
            
            # 4. Optimasi Performa (Membuat Index agar loading tidak lambat)
            optimize_performance(cursor)

            # 5. Siapkan akun Admin cadangan
            seed_default_admin(cursor)

            db.commit()
            print("✅ Sinergi V7.1: Database Siap & Performa Telah Dioptimasi.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_create_tables(cursor):
    """
    [HELPER: PENJAGA STRUKTUR TABEL]
    Kegunaan: Menjamin tabel minimal tersedia agar aplikasi bisa 'start' dengan aman.
    """
    # Tabel Laporan Kunjungan Lapangan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_petugas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomen TEXT NOT NULL,
            petugas_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel Audit Log untuk unggahan data admin
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
    [HELPER: MEKANISME SELF-HEALING]
    Kegunaan: MENAMBAH KOLOM BARU SECARA OTOMATIS tanpa merusak data yang sudah ada.
    Logika: Mengecek list kolom, jika kolom (seperti 'mc' atau 'catatan') belum ada, maka ditambahkan.
    """
    cursor.execute("PRAGMA table_info(kunjungan_petugas)")
    existing_cols = [row['name'] for row in cursor.fetchall()]
    
    # Daftar kolom Snapshot V7.1 (Pusat Data Kunjungan)
    new_columns = {
        'mc': 'REAL DEFAULT 0',         # Saldo Tagihan berjalan
        'ardebt': 'REAL DEFAULT 0',     # Saldo Tunggakan berekor
        'catatan': 'TEXT',              # Catatan/Komentar petugas
        'keterangan': 'TEXT',           # Hasil koordinasi
        'foto_path': 'TEXT',            # Nama file foto bukti
        'nomet': 'TEXT',                # Snapshot No Meter
        'nama_snapshot': 'TEXT',        # Snapshot Nama Pelanggan
        'alamat_snapshot': 'TEXT',      # Snapshot Alamat Lengkap
        'latitude': 'TEXT',             # Data GPS (Lintang)
        'longitude': 'TEXT',            # Data GPS (Bujur)
        'no_hp': 'TEXT',                # No HP Konsumen
        'volume': 'REAL DEFAULT 0',     # Snapshot angka meter
        'periode': 'TEXT'               # Periode tagihan
    }
    
    for col, dtype in new_columns.items():
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {dtype}")
                print(f"🔧 Migrasi: Kolom [{col}] ditambahkan otomatis.")
            except Exception as e:
                print(f"⚠️ Peringatan Migrasi: {e}")

def optimize_performance(cursor):
    """
    [HELPER: TURBO LOADING]
    Kegunaan: Membuat INDEX pada kolom NOMEN.
    Logika: Tanpa index, database mencari data seperti membaca buku dari halaman 1. 
    Dengan index, database langsung menuju halaman yang tepat.
    """
    try:
        # Index untuk mempercepat hitungan progres dan pencarian tagihan
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_nomen ON master_pelanggan (nomen)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas (nomen)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kunjungan_periode ON kunjungan_petugas (periode)")
        print("🚀 Performa: Indexing aktif (Loading akan lebih cepat).")
    except Exception as e:
        print(f"ℹ️ Info Performa: {e}")

def seed_default_admin(cursor):
    """
    [HELPER: PENGAMAN AKSES]
    Kegunaan: Menjamin ada minimal 1 akun Admin jika database kosong.
    """
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))
        print(f"👤 Seeder: Akun Admin '{username}' siap (Pass: admin123).")

def get_db():
    """
    [HELPER: AKSES GLOBAL FLASK]
    Kegunaan: Mengambil koneksi database yang sedang aktif dalam satu request.
    """
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db
