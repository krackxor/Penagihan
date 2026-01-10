"""
Core Database Module - Sunter Dashboard Pro (V3.6 Smart Autopilot)
Sinergi & Smart Update:
1. WAL Mode Autopilot: Optimasi konkurensi anti-'Database Locked'.
2. Auto-Migration Engine: Perbaikan otomatis kolom 'tipe' dan tabel harian.
3. Integrity Guard: Proteksi relasi data antar tabel.
"""

import sqlite3
import os
from flask import current_app
from werkzeug.security import generate_password_hash

def get_db_connection():
    """
    MEMBUAT KONEKSI DATABASE (SMART CONFIG):
    Menggunakan WAL Mode agar proses baca (admin) dan tulis (petugas) 
    bisa berjalan beriringan tanpa crash di server Ubuntu.
    """
    db_path = current_app.config.get('DATABASE')
    
    if not db_path:
        db_path = os.path.join(current_app.root_path, 'penagihan.db')
    
    try:
        # Timeout 30 detik untuk antrean proses tulis massal
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row 
        
        # --- OPTIMASI SINERGI SERVER ---
        conn.execute('PRAGMA journal_mode=WAL;')      # Anti-Locking Mode
        conn.execute('PRAGMA synchronous=NORMAL;')    # Optimal Speed
        conn.execute('PRAGMA foreign_keys = ON;')     # Data Integrity
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """
    INISIALISASI & AUTO-MIGRASI (AUTOPILOT):
    Memperbaiki struktur tabel secara otomatis saat aplikasi dijalankan.
    """
    with app.app_context():
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            # 1. Jalankan Skema Dasar dari file SQL
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    cursor.executescript(f.read())

            # 2. LOGIKA AUTO-MIGRASI (SMART FIXER)
            
            # --- FIX: Tabel collection_harian ---
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
                print("🔧 Autopilot: Tabel [collection_harian] berhasil dibuat.")

            # --- FIX: Tabel upload_history ---
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='upload_history'")
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE upload_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT, file_type TEXT, periode TEXT,
                        row_count INTEGER, status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                print("🔧 Autopilot: Tabel [upload_history] berhasil dibuat.")

            # --- SMART MIGRATION: master_pelanggan ---
            # Menangani penambahan kolom 'tipe' untuk membedakan MC dan ARDEBT
            cursor.execute("PRAGMA table_info(master_pelanggan)")
            cols = [row['name'] for row in cursor.fetchall()]
            check_and_add_columns(cursor, "master_pelanggan", cols, {
                'rayon': 'TEXT',
                'nomet': 'TEXT',
                'periode': 'TEXT',
                'volume': 'REAL DEFAULT 0',
                'no_hp': 'TEXT',
                'tipe': 'TEXT DEFAULT "MC"',  # <--- FIX: Solusi Error Upload MC Anda
                'status_lunas': 'INTEGER DEFAULT 0',
                'tgl_lunas': 'TEXT'
            })

            # --- SMART MIGRATION: kunjungan_petugas ---
            cursor.execute("PRAGMA table_info(kunjungan_petugas)")
            cols = [row['name'] for row in cursor.fetchall()]
            check_and_add_columns(cursor, "kunjungan_petugas", cols, {
                'mc': 'REAL DEFAULT 0',
                'ardebt': 'REAL DEFAULT 0',
                'latitude': 'TEXT',
                'longitude': 'TEXT',
                'no_hp': 'TEXT'
            })

            # 3. Sinkronisasi Akun Admin Default
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
    Menambah kolom secara dinamis tanpa menghapus data nasabah yang sudah ada.
    """
    for col, data_type in new_cols_map.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {data_type}")
            print(f"🔧 Migrasi: Kolom [{col}] ditambahkan ke tabel [{table_name}]")

def seed_default_admin(cursor):
    """
    SEEDER CERDAS:
    Menjamin akses sistem selalu terbuka bagi Administrator.
    """
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ADMIN_PUSAT'))
        print(f"👤 Smart Seeder: Akun '{username}' siap digunakan.")
