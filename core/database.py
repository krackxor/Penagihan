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
            
            # 2. Pastikan Tabel upload_history Tersedia (Untuk konsistensi API History)
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

            # 3. LOGIKA AUTO-MIGRASI KOLOM (Mencegah error 'no column named')
            # Migrasi master_pelanggan
            cursor.execute("PRAGMA table_info(master_pelanggan)")
            cols_pelanggan = [row['name'] for row in cursor.fetchall()]
            
            if 'nomet' not in cols_pelanggan:
                cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN nomet TEXT")
                print("➕ Kolom 'nomet' ditambahkan ke master_pelanggan.")
            
            if 'periode' not in cols_pelanggan:
                cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN periode TEXT")
                print("➕ Kolom 'periode' ditambahkan ke master_pelanggan.")

            # Migrasi tabel transaksi lainnya
            tables_to_check = ['master_bayar', 'collection_harian', 'kunjungan_petugas']
            for table in tables_to_check:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = [row['name'] for row in cursor.fetchall()]
                if 'periode' not in cols:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")
                    print(f"➕ Kolom 'periode' ditambahkan ke {table}.")

            db.commit()
            print("✅ Database initialized and migrated successfully.")
            
        except Exception as e:
            print(f"❌ Error saat inisialisasi database: {e}")
        finally:
            if 'db' in locals():
                db.close()
