# core/database.py
def init_db(app):
    db = sqlite3.connect('sunter.db')
    cursor = db.cursor()
    # ... tabel lainnya ...
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kunjungan_petugas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nomen TEXT NOT NULL,
        petugas_name TEXT,
        keterangan TEXT, -- 'Janji Bayar', 'Rumah Kosong', dll
        tgl_janji_bayar TEXT,
        foto_path TEXT,
        latitude TEXT,
        longitude TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    db.commit()
