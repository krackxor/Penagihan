import sqlite3
import os
from flask import current_app

def get_db_connection():
    """Membuat koneksi ke database dengan optimasi WAL Mode."""
    db_path = current_app.config['DATABASE']
    
    # Timeout ditingkatkan untuk menghindari 'database is locked' saat upload
    conn = sqlite3.connect(db_path, timeout=30)
    
    # row_factory mengembalikan hasil dalam bentuk yang bisa diakses seperti dictionary
    conn.row_factory = sqlite3.Row
    
    # Optimasi untuk konkurensi (WAL) dan kecepatan (Synchronous Normal)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    
    # Mengaktifkan foreign key support untuk menjaga integritas data antar periode
    conn.execute('PRAGMA foreign_keys = ON;')
    
    return conn

def init_db(app):
    """Membaca schema.sql dan memastikan tabel serta kolom baru tersedia."""
    with app.app_context():
        try:
            db = get_db_connection()
            schema_path = os.path.join(app.root_path, 'schema.sql')
            
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    content = f.read()
                    # Menjalankan script SQL untuk membuat tabel jika belum ada
                    db.cursor().executescript(content)
                
                # --- LOGIKA AUTO-MIGRASI KOLOM (Pencegah Error no column named nomet) ---
                cursor = db.cursor()
                
                # Cek kolom di master_pelanggan
                cursor.execute("PRAGMA table_info(master_pelanggan)")
                cols_pelanggan = [row['name'] for row in cursor.fetchall()]
                
                if 'nomet' not in cols_pelanggan:
                    cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN nomet TEXT")
                    print("➕ Kolom 'nomet' berhasil ditambahkan ke master_pelanggan.")
                
                if 'periode' not in cols_pelanggan:
                    cursor.execute("ALTER TABLE master_pelanggan ADD COLUMN periode TEXT")
                    print("➕ Kolom 'periode' berhasil ditambahkan ke master_pelanggan.")

                # Cek kolom periode di tabel transaksi lainnya
                tables_to_check = ['master_bayar', 'collection_harian', 'kunjungan_petugas']
                for table in tables_to_check:
                    cursor.execute(f"PRAGMA table_info({table})")
                    cols = [row['name'] for row in cursor.fetchall()]
                    if 'periode' not in cols:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN periode TEXT")
                        print(f"➕ Kolom 'periode' berhasil ditambahkan ke {table}.")

                db.commit()
                print("✅ Database initialized and migrated successfully.")
            else:
                print(f"⚠️ Warning: {schema_path} not found.")
        except Exception as e:
            print(f"❌ Error saat inisialisasi database: {e}")
