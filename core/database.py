import sqlite3
import os
from flask import g, current_app

def get_db_connection():
    """
    Membuat koneksi ke database dengan fitur optimasi SQLite.
    """
    db_path = current_app.config['DATABASE']
    
    # timeout=30 agar sistem menunggu jika database sedang sibuk (saat upload)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    
    # AKTIFKAN OPTIMASI BERIKUT:
    # Mode WAL memungkinkan petugas lapangan membaca data (Daftar Penagihan) 
    # meskipun Admin sedang menulis data (Upload file)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    
    return conn

def init_db(app):
    """
    Menjalankan file schema.sql untuk membuat tabel saat pertama kali jalan.
    """
    with app.app_context():
        db = get_db_connection()
        schema_path = os.path.join(app.root_path, 'schema.sql')
        if os.path.exists(schema_path):
            with open(schema_path, mode='r') as f:
                db.cursor().executescript(f.read())
            db.commit()
            print("Database initialized successfully.")
