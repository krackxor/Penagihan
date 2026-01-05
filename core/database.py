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
    """Membaca schema.sql dan membuat tabel jika belum ada."""
    with app.app_context():
        try:
            db = get_db_connection()
            schema_path = os.path.join(app.root_path, 'schema.sql')
            
            if os.path.exists(schema_path):
                with open(schema_path, mode='r') as f:
                    content = f.read()
                    # Menjalankan script SQL
                    # executescript sangat kuat untuk menjalankan banyak perintah CREATE TABLE sekaligus
                    db.cursor().executescript(content)
                db.commit()
                print("✅ Database initialized successfully with dynamic period support.")
            else:
                print(f"⚠️ Warning: {schema_path} not found.")
        except Exception as e:
            # Jika masih error, print detail error untuk debug
            print(f"❌ Error saat inisialisasi database: {e}")
