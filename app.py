import os
from flask import Flask, render_template, redirect, url_for
from models import db

# --- 1. IMPORT BLUEPRINTS ---
# Pastikan semua file di folder api/ sudah lengkap
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp # <--- Tambahan modul SBRS

def create_app():
    app = Flask(__name__)

    # --- 2. KONFIGURASI ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    # Database tersimpan di instance/ agar aman di Docker volume
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'sinergi.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    
    # Folder upload foto
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # Ditingkatkan ke 100MB agar upload CID lancar

    # --- 3. INISIALISASI DATABASE ---
    db.init_app(app)

    # Pastikan folder penting dibuat otomatis saat startup
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads', 'materi'), exist_ok=True)

    # --- 4. REGISTRASI MODUL (BLUEPRINTS) ---
    app.register_blueprint(monitoring_bp, url_prefix='/monitoring')
    app.register_blueprint(importer_bp, url_prefix='/api/import')
    app.register_blueprint(kunjungan_bp, url_prefix='/api/kunjungan')
    app.register_blueprint(sbrs_bp, url_prefix='/sbrs') # <--- Registrasi SBRS

    # --- 5. NAVIGASI UTAMA ---
    @app.route('/')
    def index():
        """Halaman utama langsung ke monitoring Sunter."""
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app.route('/upload')
    def upload_page():
        """Halaman Admin untuk upload semua jenis file."""
        return render_template('upload.html')

    @app.route('/lapor')
    def lapor_page():
        """Halaman untuk Petugas input laporan lapangan."""
        return render_template('lapor.html')

    # --- 6. STARTUP PROTOCOL ---
    with app.app_context():
        # Buat tabel otomatis jika belum ada
        db.create_all()

    return app

if __name__ == '__main__':
    # Host 0.0.0.0 agar bisa diakses lewat Docker/Nginx
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
