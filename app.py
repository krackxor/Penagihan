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
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
            
        # Timeout 30 detik untuk antrian query
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        
        # Mode WAL (Write-Ahead Logging) untuk stabilitas
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Database & Folder Upload saat startup
    with app.app_context():
        Config.init_app(app)
        init_db(app)

    @app.teardown_appcontext
    def close_connection(exception):
        """Menutup koneksi database setiap request selesai"""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- REGISTRASI API ---
    # Menggunakan Blueprint untuk Upload & History
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    
    # Menggunakan Register Function untuk rute dinamis
    register_belum_bayar_routes(app, get_db)
    register_pcez_routes(app, get_db)

    # --- RUTE FRONTEND (RENDERING) ---
    @app.route('/')
    def index():
        """Halaman Dashboard Utama"""
        return render_template('index.html')

    @app.route('/performa')
    def performa_page():
        """Halaman Performa Tim / Leaderboard Petugas"""
        return render_template('performa.html')

    @app.route('/belum-bayar')
    def belum_bayar_page():
        """Halaman Daftar Penagihan / Tugas Lapangan"""
        return render_template('belum_bayar.html')

    @app.route('/upload')
    def upload_page():
        """Halaman Upload File Master (MC/MB)"""
        return render_template('upload.html')

    @app.route('/history')
    def history_page():
        """Halaman Log Riwayat Upload & Kunjungan"""
        return render_template('history.html')

    @app.route('/wa-blast')
    def wa_blast_page():
        """Halaman Pengiriman Pesan Massal WhatsApp"""
        return render_template('wa_blast.html')

    # --- SERVING FILES ---
    @app.route('/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Menyajikan foto bukti kunjungan agar bisa diakses browser/WA"""
        return send_from_directory(app.config['KUNJUNGAN_FOLDER'], filename)

    return app

# Entry Point Aplikasi
if __name__ == '__main__':
    app = create_app()
    # Host 0.0.0.0 agar bisa diakses dari HP petugas dalam satu jaringan
    app.run(host='0.0.0.0', port=5000, debug=True)
