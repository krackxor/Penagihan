import os
from flask import Flask, render_template, redirect, url_for
from models import db

# --- 1. IMPORT BLUEPRINTS ---
# Memastikan semua modul fungsional terdaftar
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 

def create_app():
    app = Flask(__name__)

    # --- 2. KONFIGURASI (DIPERBARUI UNTUK POSTGRESQL) ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Mengambil koneksi PostgreSQL dari environment Docker
    # Alamat ini disetel di docker-compose.yml: DATABASE_URL
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    
    # Folder upload foto kunjungan
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    
    # Kapasitas ditingkatkan ke 1 GB (1024 * 1024 * 1024 bytes)
    # Penting agar upload file CID se-Jakarta tidak terputus di tengah jalan
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

    # --- 3. INISIALISASI DATABASE ---
    db.init_app(app)

    # Pastikan folder penyimpanan data dibuat otomatis saat startup
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
        """Arahkan langsung ke dashboard Monitoring AB Sunter."""
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app.route('/upload')
    def upload_page():
        """Halaman sentral untuk upload file teks sistem dan excel."""
        return render_template('upload.html')

    @app.route('/lapor')
    def lapor_page():
        """Halaman input laporan lapangan untuk petugas penagihan."""
        return render_template('lapor.html')

    # --- 6. STARTUP PROTOCOL ---
    with app.app_context():
        # PostgreSQL akan otomatis membuat tabel-tabel sesuai models.py
        # jika tabel tersebut belum ada di database server
        db.create_all()

    return app

if __name__ == '__main__':
    # Pastikan host diatur ke 0.0.0.0 agar Docker bisa melakukan pemetaan port
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
