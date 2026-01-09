import sqlite3
import os
from flask import current_app
from werkzeug.security import generate_password_hash

def get_db_connection():
    """Membuat koneksi ke database dengan optimasi WAL Mode yang konsisten."""
    db_path = current_app.config.get('DATABASE')
    
    if not db_path:
        db_path = os.path.join(current_app.root_path, 'penagihan.db')
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        
        # Optimasi performa untuk konkurensi tinggi
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        conn.execute('PRAGMA foreign_keys = ON;')
        
        return conn
    except sqlite3.Error as e:
        print(f"❌ Database Connection Error: {e}")
        raise

def init_db(app):
    """Membaca schema.sql dan melakukan auto-migrasi kolom agar sistem tetap robust."""
    with app.app_context():
        try:
            db = get_db_connection()
            schema_path = os.path.join(app.root_path, 'schema.sql')
            
            # 1. Jalankan Skema Dasar dari file SQL
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    content = f.read()
                    db.cursor().executescript(content)
            else:
                print(f"⚠️ Warning: {schema_path} tidak ditemukan. Menggunakan skema internal.")

            cursor = db.cursor()
            
            # 2. Pastikan Tabel User (Level 3) & History tersedia
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL, -- 'admin', 'petugas', 'publik'
                    petugas_id TEXT,    -- Mapping ke nama petugas di rute_petugas
                    no_hp TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. LOGIKA AUTO-MIGRASI (Menjaga integritas saat update versi)
            
            # --- Migrasi Tabel master_pelanggan ---
            cursor.execute("PRAGMA table_info(master_pelanggan)")
            cols_pelanggan = [row['name'] for row in cursor.fetchall()]
            if 'rayon' not in cols_pelanggan: cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN rayon TEXT")
            if 'nomet' not in cols_pelanggan: cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN nomet TEXT")
            if 'periode' not in cols_pelanggan: cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN periode TEXT")
            if 'volume' not in cols_pelanggan: cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN volume REAL DEFAULT 0")

            # --- Migrasi Tabel rute_petugas ---
            cursor.execute("PRAGMA table_info(rute_petugas)")
            cols_rute = [row['name'] for row in cursor.fetchall()]
            if 'no_admin' not in cols_rute:
                cursor.execute("ALTER TABLE rute_petugas ADD COLUMN no_admin TEXT DEFAULT '628123456789'")

            # --- Migrasi Tabel kunjungan_petugas (Geo-Tagging & Snapshot) ---
            cursor.execute("PRAGMA table_info(kunjungan_petugas)")
            cols_kunjungan = [row['name'] for row in cursor.fetchall()]
            migrasi_kunjungan = {
                'mc': 'REAL DEFAULT 0',
                'ardebt': 'REAL DEFAULT 0',
                'no_hp': 'TEXT',
                'latitude': 'TEXT',
                'longitude': 'TEXT',
                'periode': 'TEXT'
            }
            for col, val in migrasi_kunjungan.items():
                if col not in cols_kunjungan:
                    cursor.execute(f"ALTER TABLE kunjungan_petugas ADD COLUMN {col} {val}")

            # --- Migrasi Tabel ardebt ---
            cursor.execute("PRAGMA table_info(ardebt)")
            cols_ardebt = [row['name'] for row in cursor.fetchall()]
            if 'volume' not in cols_ardebt: cursor.execute("ALTER TABLE ardebt ADD COLUMN volume REAL DEFAULT 0")

            # --- Sinkronisasi Akun Admin Default ---
            seed_default_admin(cursor)

            db.commit()
            print("✅ Database initialized, migrated, and admin synced.")
            
        except Exception as e:
            print(f"❌ Error saat inisialisasi database: {e}")
            if 'db' in locals(): db.rollback()
        finally:
            if 'db' in locals(): db.close()

def seed_default_admin(cursor):
    """Menjamin adanya akun admin awal untuk akses sistem pertama kali."""
    username = 'admin_sunter'
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, password, role, petugas_id)
            VALUES (?, ?, ?, ?)
        """, (username, hashed_pw, 'admin', 'ALL'))
        print(f"👤 Akun admin default '{username}' telah dibuat (Pass: admin123).")
