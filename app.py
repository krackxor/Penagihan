import os
from flask import Flask, render_template, redirect, url_for
from models import db
from sqlalchemy import inspect, text # Keamanan & Audit Database

# --- 1. IMPORT BLUEPRINTS ---
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 

def sync_database_schema(app):
    """
    Fungsi Sinergi Self-Healing: Otomatis sinkronisasi struktur PostgreSQL.
    Memasukkan semua kolom yang dibutuhkan agar tidak terjadi 'UndefinedColumn' error.
    """
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Target Audit: Tabel data_sbrs
        if 'data_sbrs' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('data_sbrs')]
            
            # DAFTAR KOLOM WAJIB (Termasuk status_audit untuk fix error)
            required_columns = [
                ('periode', 'VARCHAR(10)'),
                ('ab', "VARCHAR(50) DEFAULT 'AB Sunter'"),
                ('kelurahan', 'VARCHAR(100)'),
                ('pcez', 'VARCHAR(20)'),
                ('nama', 'VARCHAR(150)'),
                ('alamat', 'TEXT'),
                ('status_audit', 'INTEGER DEFAULT 0') # <-- FIX UNTUK ERROR TADI
            ]
            
            with db.engine.connect() as conn:
                for col_name, col_type in required_columns:
                    if col_name not in columns:
                        print(f">>> [SINERGI-FIX] Menambah kolom '{col_name}' ke data_sbrs...")
                        conn.execute(text(f"ALTER TABLE data_sbrs ADD COLUMN {col_name} {col_type}"))
                conn.commit()

def create_app():
    app = Flask(__name__)

    # --- 2. KONFIGURASI SINERGI & KEAMANAN ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Koneksi DB: Sangat stabil untuk data raksasa
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    
    # Folder Media & Upload
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 # Limit 1 GB

    # --- 3. INISIALISASI & FOLDER AUTO-CREATE ---
    db.init_app(app)

    # Memastikan folder sistem tersedia
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads', 'materi'), exist_ok=True)

    # --- 4. REGISTRASI MODUL (BLUEPRINTS) ---
    app.register_blueprint(monitoring_bp, url_prefix='/monitoring')
    app.register_blueprint(importer_bp, url_prefix='/api/import')
    app.register_blueprint(kunjungan_bp, url_prefix='/api/kunjungan')
    app.register_blueprint(sbrs_bp, url_prefix='/sbrs') 

    # --- 5. NAVIGASI UTAMA ---
    @app.route('/')
    def index():
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app.route('/upload')
    def upload_page():
        return render_template('upload.html')

    @app.route('/lapor')
    def lapor_page():
        return render_template('lapor.html')

    # --- 6. STARTUP PROTOCOL ---
    with app.app_context():
        # Buat tabel jika benar-benar kosong
        db.create_all()
    
    # Jalankan audit kolom otomatis (Self-Healing)
    sync_database_schema(app)

    return app

if __name__ == '__main__':
    # Aktifkan debug=True untuk memantau log perbaikan kolom di terminal
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
