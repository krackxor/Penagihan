import sqlite3
import os
from flask import current_app

def get_db_connection():
    """Membuat koneksi ke database dengan optimasi WAL Mode yang konsisten."""
    db_path = current_app.config.get('DATABASE')
    
    # Validasi path database
    if not db_path:
        db_path = os.path.join(current_app.root_path, 'penagihan.db')
    
    try:
        # Timeout ditingkatkan untuk menghindari 'database is locked' saat proses upload masif
        conn = sqlite3.connect(db_path, timeout=30)
        
        # row_factory mengembalikan hasil dalam bentuk yang bisa diakses seperti dictionary
        conn.row_factory = sqlite3.Row
        
        # Optimasi performa untuk lingkungan mobile-first/multi-user
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        
        # Menjaga integritas data relasional
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
            
            # 1. Jalankan Skema Dasar
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    content = f.read()
                    db.cursor().executescript(content)
            else:
                print(f"⚠️ Warning: {schema_path} tidak ditemukan, menggunakan tabel yang ada.")

            cursor = db.cursor()
            
            # 2. Pastikan Tabel Dasar Tersedia
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS upload_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT,
                    file_type TEXT,
                    periode TEXT,
                    row_count INTEGER,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- SINERGI: Tabel Users untuk Login 3 Level ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL, -- 'admin', 'petugas', 'publik'
                    petugas_id TEXT,    -- Mapping ke nama petugas di rute_petugas
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✅ Tabel 'users' siap (Sinergi Login 3 Level).")

            # 3. LOGIKA AUTO-MIGRASI KOLOM (Mencegah OperationalError)
            
            # --- Migrasi Tabel master_pelanggan ---
            cursor.execute("PRAGMA table_info(master_pelanggan)")
            cols_pelanggan = [row['name'] for row in cursor.fetchall()]
            
            if 'rayon' not in cols_pelanggan:
                cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN rayon TEXT")
                print("➕ Kolom 'rayon' ditambahkan.")

            if 'nomet' not in cols_pelanggan:
                cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN nomet TEXT")
                print("➕ Kolom 'nomet' ditambahkan.")
            
            if 'periode' not in cols_pelanggan:
                cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN periode TEXT")
            
            if 'volume' not in cols_pelanggan:
                cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN volume REAL DEFAULT 0")

            # --- Migrasi Tabel rute_petugas (Tambahkan No Admin) ---
            cursor.execute("PRAGMA table_info(rute_petugas)")
            cols_rute = [row['name'] for row in cursor.fetchall()]
            if 'no_admin' not in cols_rute:
                cursor.execute("ALTER TABLE rute_petugas ADD COLUMN no_admin TEXT DEFAULT '628123456789'")
                print("➕ Kolom 'no_admin' ditambahkan ke rute_petugas.")

            # --- Migrasi Tabel collection_harian ---
            cursor.execute("PRAGMA table_info(collection_harian)")
            cols_coll = [row['name'] for row in cursor.fetchall()]
            if 'pay_dt' not in cols_coll:
                cursor.execute("ALTER TABLE collection_harian ADD COLUMN pay_dt TEXT")

            # --- Migrasi Tabel ardebt ---
            cursor.execute("PRAGMA table_info(ardebt)")
            cols_ardebt = [row['name'] for row in cursor.fetchall()]
            if 'volume' not in cols_ardebt:
                cursor.execute("ALTER TABLE ardebt ADD COLUMN volume REAL DEFAULT 0")

            # --- Migrasi tabel transaksi lainnya untuk kolom periode ---
            tables_to_check = ['master_bayar', 'collection_harian', 'kunjungan_petugas']
            for table in tables_to_check:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = [row['name'] for row in cursor.fetchall()]
                if 'periode' not in cols:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")

            db.commit()
            print("✅ Database initialized and migrated successfully.")
            
        except Exception as e:
            print(f"❌ Error saat inisialisasi database: {e}")
        finally:
            if 'db' in locals():
                db.close()
