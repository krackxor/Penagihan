import sqlite3
import os
from flask import g, current_app

def get_db_connection():
    """
    Mengelola koneksi database tunggal per request menggunakan Flask 'g'.
    Mengambil path database dari Config aplikasi secara dinamis.
    """
    if 'db' not in g:
        # Mengambil path dari config (penagihan.db), fallback jika tidak ada
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            db_path = os.path.join(current_app.root_path, 'penagihan.db')
        
        # Timeout 30 detik untuk mencegah error 'database is locked'
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        
        # Aktifkan Write-Ahead Logging agar Read & Write bisa berjalan bersamaan
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
        
    return g.db

def init_db(app):
    """
    Inisialisasi database menggunakan schema.sql.
    Dijalankan sekali saat aplikasi pertama kali dijalankan.
    """
    with app.app_context():
        db = get_db_connection()
        # Path ke file schema.sql di root folder
        schema_path = os.path.join(app.root_path, 'schema.sql')
        
        try:
            with open(schema_path, mode='r') as f:
                db.cursor().executescript(f.read())
            db.commit()
            print("Database initialized successfully.")
        except Exception as e:
            print(f"Error initializing database: {str(e)}")
