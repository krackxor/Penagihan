import os
import sqlite3
from flask import Flask, render_template, g, send_from_directory, current_app

# Import Konfigurasi
from config import Config

# Import Database & Helpers
from core.database import init_db

# Import API Routes (Blueprints & Register Functions)
from api.upload import upload_bp
from api.history import history_bp
from api.rute import rute_bp  # Blueprint baru untuk Setting Petugas
from api.belum_bayar import register_belum_bayar_routes
from api.pcez_performance import register_pcez_routes

def get_db():
    """
    Manajemen koneksi database terpusat dengan mode WAL.
    Mencegah error 'database is locked' saat akses bersamaan.
    """
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            # Fallback path jika config tidak terbaca
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
            
        # Timeout 30 detik agar query antri saat database sibuk (seperti saat upload)
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        
        # Aktifkan Mode WAL (Write-Ahead Logging) 
        # Sangat penting agar petugas bisa buka 'Daftar Penagihan' saat Admin sedang 'Upload'
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Database & Struktur Folder saat startup
    with app.app_context():
        Config.init_app(app)
        init_db(app)

    @app.teardown_appcontext
    def close_connection(exception):
        """Menutup koneksi database setiap kali request selesai"""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- REGISTRASI API (BLUEPRINTS) ---
    # Prefix /api ditambahkan agar rute API terorganisir
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    app.register_blueprint(rute_bp, url_prefix='/api') # Registrasi API Rute/Petugas Manual
    
    # --- REGISTRASI RUTE DINAMIS ---
    # Mengirimkan fungsi get_db agar API bisa mengakses database yang sama
    register_belum_bayar_routes(app, get_db)
    register_pcez_routes(app, get_db)

    # --- RUTE FRONTEND (RENDERING HALAMAN) ---
    
    @app.route('/')
    def index():
        """Dashboard Utama"""
        return render_template('index.html')

    @app.route('/performa')
    def performa_page():
        """Halaman Grafik Performa Petugas (Leaderboard)"""
        return render_template('performa.html')

    @app.route('/belum-bayar')
    def belum_bayar_page():
        """Halaman Daftar Penagihan (Tugas Lapangan)"""
        return render_template('belum_bayar.html')

    @app.route('/upload')
    def upload_page():
        """Halaman Form Upload Master Data (MC, MB, Col, Ardebt)"""
        return render_template('upload.html')

    @app.route('/history')
    def history_page():
        """Halaman Log Riwayat Kunjungan"""
        return render_template('history.html')

    @app.route('/setting-rute')
    def setting_rute_page():
        """Halaman Mapping PCEZ ke Petugas secara Manual"""
        return render_template('setting_rute.html')

    @app.route('/wa-blast')
    def wa_blast_page():
        """Fitur Tambahan: Pengiriman Pesan WhatsApp"""
        return render_template('wa_blast.html')

    # --- SERVING FILES (FOTO BUKTI) ---
    @app.route('/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Menampilkan foto bukti kunjungan untuk admin/laporan"""
        return send_from_directory(app.config['KUNJUNGAN_FOLDER'], filename)

    return app

# Entry Point Aplikasi
if __name__ == '__main__':
    app = create_app()
    # Debug=True untuk development
    # host='0.0.0.0' wajib agar bisa dibuka via IP Address di HP petugas
    app.run(host='0.0.0.0', port=5000, debug=True)
