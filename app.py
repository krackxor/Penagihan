import os
from flask import Flask, render_template, redirect, url_for
from models import db
from sqlalchemy import inspect, text # Tambahan untuk inspeksi database otomatis

# --- 1. IMPORT BLUEPRINTS ---
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 

def sync_database_schema(app):
    """
    Fungsi Otomatis (Self-Healing) untuk sinkronisasi kolom database.
    Mencegah error 'UndefinedColumn' pada PostgreSQL.
    """
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Cek apakah tabel data_sbrs sudah ada
        if 'data_sbrs' in inspector.get_table_names():
            # Ambil daftar nama kolom yang ada saat ini
            columns = [c['name'] for c in inspector.get_columns('data_sbrs')]
            
            # 1. Tambah kolom 'periode' jika belum ada
            if 'periode' not in columns:
                print(">>> [AUTO-SYNC] Menambah kolom 'periode' ke data_sbrs...")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE data_sbrs ADD COLUMN periode VARCHAR(10)"))
                    conn.commit()
            
            # 2. Tambah kolom 'ab' jika belum ada (untuk filter wilayah)
            if 'ab' not in columns:
                print(">>> [AUTO-SYNC] Menambah kolom 'ab' ke data_sbrs...")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE data_sbrs ADD COLUMN ab VARCHAR(50) DEFAULT 'AB Sunter'"))
                    conn.commit()
            
            # 3. Tambah kolom 'kelurahan' jika belum ada (untuk sebaran anomali)
            if 'kelurahan' not in columns:
                print(">>> [AUTO-SYNC] Menambah kolom 'kelurahan' ke data_sbrs...")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE data_sbrs ADD COLUMN kelurahan VARCHAR(100)"))
                    conn.commit()

def create_app():
    app = Flask(__name__)

    # --- 2. KONFIGURASI DATABASE & KEAMANAN ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Koneksi PostgreSQL dari environment Docker
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    
    # Folder upload foto kunjungan & materi
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    
    # --- 3. LIMIT UPLOAD 1 GB ---
    # Mendukung upload file CID dan MC raksasa
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 

    # --- 4. INISIALISASI & FOLDER AUTO-CREATE ---
    db.init_app(app)

    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads', 'materi'), exist_ok=True)

    # --- 5. REGISTRASI MODUL (BLUEPRINTS) ---
    app.register_blueprint(monitoring_bp, url_prefix='/monitoring')
    app.register_blueprint(importer_bp, url_prefix='/api/import')
    app.register_blueprint(kunjungan_bp, url_prefix='/api/kunjungan')
    app.register_blueprint(sbrs_bp, url_prefix='/sbrs') 

    # --- 6. NAVIGASI UTAMA ---
    @app.route('/')
    def index():
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app.route('/upload')
    def upload_page():
        return render_template('upload.html')

    @app.route('/lapor')
    def lapor_page():
        return render_template('lapor.html')

    # --- 7. STARTUP PROTOCOL ---
    with app.app_context():
        # Buat tabel baru jika belum ada sama sekali
        db.create_all()
    
    # Jalankan pemeriksaan kolom (Self-Healing) untuk tabel lama
    sync_database_schema(app)

    return app

if __name__ == '__main__':
    app = create_app()
    # Host 0.0.0.0 wajib untuk akses lewat Docker/VPS
    app.run(host='0.0.0.0', port=5000, debug=True)
