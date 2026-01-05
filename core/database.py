import sqlite3
import os
from flask import current_app

def get_db_connection():
    """
    Membuat koneksi ke database dengan optimasi tingkat tinggi untuk mobilitas.
    """
    db_path = current_app.config['DATABASE']
    
    # timeout=30 menghindari error 'database is locked' saat proses upload masif
    conn = sqlite3.connect(db_path, timeout=30)
    
    # row_factory = sqlite3.Row memperbaiki TypeError 'dictionary' pada cursor
    # Ini memungkinkan kita mengakses kolom dengan nama (row['nama']) bukan index
    conn.row_factory = sqlite3.Row
    
    # --- OPTIMASI SQLITE ---
    # WAL Mode: Petugas tetap bisa akses data saat Admin sedang upload Excel
    conn.execute('PRAGMA journal_mode=WAL;')
    # Synchronous NORMAL: Mempercepat proses tulis data (Upload) tanpa resiko korupsi data
    conn.execute('PRAGMA synchronous=NORMAL;')
    # Cache Size: Menyimpan data di RAM untuk pencarian (Search) yang lebih instan
    conn.execute('PRAGMA cache_size=-2000;') 
    
    return conn

def init_db(app):
    """
    Inisialisasi database berdasarkan file schema.sql.
    Memastikan semua tabel (master_pelanggan, kunjungan_petugas, dll) terbuat.
    """
    with app.app_context():
        try:
            db = get_db_connection()
            # Mencari file schema.sql di root project sesuai struktur repositori
            schema_path = os.path.join(app.root_path, 'schema.sql')
            
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    db.cursor().executescript(f.read())
                db.commit()
                print("✅ Database & Tabel berhasil diinisialisasi.")
            else:
                print(f"⚠️ Peringatan: {schema_path} tidak ditemukan.")
                
        except Exception as e:
            print(f"❌ Error saat inisialisasi database: {e}")
