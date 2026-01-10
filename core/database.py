"""
Core Database Module - Sunter Dashboard Pro (V3.6 Smart Autopilot)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi agar aplikasi tidak 'Database Locked'.
2. Auto-Migration Engine: Perbaikan otomatis kolom 'tipe', 'is_high_value', dan tabel harian.
3. Integrity Guard: Menjamin keamanan relasi antar tabel (Foreign Keys).
"""

import sqlite3
import os
from flask import current_app
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    MEMBUAT KONEKSI DATABASE (SMART CONFIG):
    Menggunakan WAL Mode untuk memungkinkan proses baca (admin) dan 
    tulis (petugas) berjalan beriringan tanpa hambatan di server Ubuntu.
    """
    db_path = current_app.config.get('DATABASE')
    
    # Fallback autopilot jika path tidak ditemukan di config
    if not db_path:
        db_path = os.path.join(current_app.root_path, 'penagihan.db')
    
    try:
        # Timeout 30 detik untuk antrean proses tulis massal dari Excel
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row # Akses data menggunakan nama kolom
        
        # --- BLOK OPTIMASI SINERGI SERVER ---
        conn.execute('PRAGMA journal_mode=WAL;')      # Mode tulis-cepat (Anti-Lock)
        conn.execute('PRAGMA synchronous=NORMAL;')    # Kecepatan maksimal dengan aman
        conn.execute('PRAGMA foreign_keys = ON;')     # Integritas data antar tabel
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    INISIALISASI & AUTO-MIGRASI (AUTOPILOT):
    Mendeteksi struktur tabel saat aplikasi dinyalakan.
    Memperbaiki tabel 'collection_harian' dan 'upload_history' yang hilang otomatis.
    """
    with app.app_context():
        db = None
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Jalankan Skema Dasar dari file SQL (schema.sql)
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. LOGIKA AUTO-MIGRASI TABEL (SMART FIXER)
            
            # --- FIX: Tabel collection_harian (Solusi error 500 OperationalError) ---
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='collection_harian'")
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE collection_harian (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nomen TEXT NOT NULL,
                        notag TEXT,
                        nominal REAL DEFAULT 0,
                        pay_dt TEXT,
                        periode TEXT,
                        petugas_input TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(nomen, notag, periode)
                    )
                """)
                print("🔧 Autopilot: Tabel [collection_harian] berhasil dibuat otomatis.")

            # --- FIX: Tabel upload_history ---
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='upload_history'")
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE upload_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT,
                        file_type TEXT,
                        periode TEXT,
                        row_count INTEGER,
                        status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                print("🔧 Autopilot: Tabel [upload_history] berhasil dibuat otomatis.")

            # 3. LOGIKA AUTO-MIGRASI KOLOM (SMART UPDATE)
            
            # --- Migrasi Tabel master_pelanggan ---
            cursor.execute("PRAGMA table_info(master_pelanggan)")
            cols_mc = [row['name'] for row in cursor.fetchall()]
            check_and_add_columns(cursor, "master_pelanggan", cols_mc, {
                'rayon': 'TEXT',
                'nomet': 'TEXT',
                'periode': 'TEXT',
                'volume': 'REAL DEFAULT 0',
                'no_hp': 'TEXT',
                'tipe': 'TEXT DEFAULT "MC"',         # FIX: Kolom tipe yang hilang
                'is_high_value': 'INTEGER DEFAULT 0', # FIX: Kolom is_high_value yang hilang
                'status_lunas': 'INTEGER DEFAULT 0',
                'tgl_lunas': 'TEXT'
            })

            # --- Migrasi Tabel kunjungan_petugas ---
            cursor.execute("PRAGMA table_info(kunjungan_petugas)")
            cols_kunj = [row['name'] for row in cursor.fetchall()]
            check_and_add_columns(cursor, "kunjungan_petugas", cols_kunj, {
                'mc': 'REAL DEFAULT 0',
                'ardebt': 'REAL DEFAULT 0',
                'latitude': 'TEXT',
                'longitude': 'TEXT',
                'no_hp': 'TEXT'
            })

            # 4. Sinkronisasi Akun Admin Default
            seed_default_admin(cursor)

            db.commit()
            print("✅ Autopilot: Database inisialisasi & migrasi berhasil.")
            
        except Exception as e:
            print(f"❌ Sinergi Database Error: {e}")
            if db: db.rollback()
        finally:
            if db: db.close()

def check_and_add_columns(cursor, table_name, existing_cols, new_cols_map):
    """
    HELPER SMART MIGRATION:
    Menambah kolom secara dinamis tanpa menghapus data yang sudah ada.
    """
    for col, data_type in new_cols_map.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {data_type}")
            print(f"🔧 Migrasi: Kolom [{col}] ditambahkan ke tabel [{table_name}]")

def seed_default_admin(cursor):
    """
    SEEDER CERDAS:
    Menjamin akses sistem tidak terkunci dengan menyediakan akun admin pusat.
    """
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))
        print(f"👤 Smart Seeder: Akun '{username}' (pw: admin123) siap digunakan.")
