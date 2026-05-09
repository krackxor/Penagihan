import os
from flask import Flask, render_template, redirect, url_for
from models import db

# Import Blueprints (Logika dipisah di folder api/)
# Pastikan file-file ini ada di folder api/ agar tidak error
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp

def create_app():
    app = Flask(__name__)

    # --- 1. KONFIGURASI ---
    # Database tersimpan di folder 'instance' agar aman di Docker volume
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'sinergi.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    
    # Folder untuk simpan foto kunjungan
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Maksimal 16MB

    # --- 2. INISIALISASI DATABASE ---
    db.init_app(app)

    # Pastikan folder instance dan uploads dibuat otomatis saat startup
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # --- 3. REGISTRASI MODUL (BLUEPRINTS) ---
    # Membagi web menjadi beberapa bagian fungsional
    app.register_blueprint(monitoring_bp, url_prefix='/monitoring')
    app.register_blueprint(importer_bp, url_prefix='/api/import')
    app.register_blueprint(kunjungan_bp, url_prefix='/api/kunjungan')

    # --- 4. NAVIGASI UTAMA ---
    @app.route('/')
    def index():
        """
        Halaman Utama: Langsung arahkan ke monitoring AB Sunter.
        Petugas atau Admin tidak perlu pilih-pilih lagi di awal.
        """
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app.route('/upload')
    def upload_page():
        """Halaman untuk Admin upload file CID, Petugas, dan Tagihan."""
        return render_template('upload.html')

    @app.route('/lapor')
    def lapor_page():
        """Halaman untuk Petugas di lapangan melakukan input laporan."""
        return render_template('lapor.html')

    # --- 5. STARTUP PROTOCOL ---
    with app.app_context():
        # Membuat semua tabel di models.py jika file .db belum ada
        db.create_all()

    return app

if __name__ == '__main__':
    # host 0.0.0.0 wajib agar bisa diakses lewat jaringan atau Docker
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
