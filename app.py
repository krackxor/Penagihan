import os
from flask import Flask, render_template, redirect, url_for
from models import db

# --- 1. IMPORT BLUEPRINTS ---
# Memastikan semua modul (Monitoring, Importer, Kunjungan, SBRS) terdaftar
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 

def create_app():
    app = Flask(__name__)

    # --- 2. KONFIGURASI DATABASE & KEAMANAN ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Mengambil koneksi PostgreSQL dari environment Docker (Setel di docker-compose.yml)
    # Sangat stabil untuk query 1 juta data pelanggan
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    
    # Folder upload foto kunjungan petugas lapangan
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    
    # --- 3. LIMIT UPLOAD 1 GB ---
    # Penting agar upload file cid.txt raksasa tidak terputus (Error 413)
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 

    # --- 4. INISIALISASI & FOLDER AUTO-CREATE ---
    db.init_app(app)

    # Memastikan folder penting dibuat otomatis saat aplikasi pertama kali nyala
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
        """Halaman Utama: Langsung arahkan ke dashboard AB Sunter."""
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app.route('/upload')
    def upload_page():
        """Halaman sentral untuk upload file teks sistem (; semicolon)."""
        return render_template('upload.html')

    @app.route('/lapor')
    def lapor_page():
        """Halaman input laporan lapangan petugas penagihan."""
        return render_template('lapor.html')

    # --- 7. STARTUP PROTOCOL ---
    with app.app_context():
        # Membuat tabel di PostgreSQL jika belum ada secara otomatis
        db.create_all()

    return app

if __name__ == '__main__':
    # Host 0.0.0.0 wajib agar bisa diakses lewat IP VPS / Docker
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
