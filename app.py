import os
import sqlite3
from flask import Flask, render_template, g, send_from_directory, current_app

# Import Konfigurasi dari config.py
from config import Config

# Import Helper Database
from core.database import init_db

# Import Blueprints (API)
from api.upload import upload_bp
from api.history import history_bp
from api.rute import rute_bp
# Perbaikan: Import blueprint, bukan fungsi register
from api.belum_bayar import belum_bayar_bp 
from api.pcez_performance import register_pcez_routes

def get_db():
    """
    Koneksi database terpusat dengan optimasi WAL Mode.
    Sangat penting agar aplikasi tidak 'Locked' saat banyak petugas akses.
    """
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
            
        # Timeout 30 detik untuk menangani antrian penulisan data
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        
        # Optimasi SQLite untuk kecepatan tinggi (High Speed)
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Database & Folder Upload (Kunjungan Petugas)
    with app.app_context():
        Config.init_app(app)
        init_db(app)

    @app.teardown_appcontext
    def close_connection(exception):
        """Menutup koneksi database secara otomatis di akhir request"""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- REGISTRASI BLUEPRINT API ---
    # Prefix /api memisahkan logika data dengan tampilan
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    app.register_blueprint(rute_bp, url_prefix='/api')
    
    # Perbaikan: Registrasi belum_bayar menggunakan Blueprint
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    
    # --- REGISTRASI RUTE DINAMIS ---
    # PCEZ tetap menggunakan fungsi register jika belum diubah ke Blueprint
    register_pcez_routes(app, get_db)

    # --- RUTE NAVIGASI FRONTEND (Tampilan) ---

    @app.route('/')
    def index():
        """Halaman Dashboard Utama / Ringkasan Penagihan"""
        return render_template('index.html')

    @app.route('/belum-bayar')
    def belum_bayar_page():
        """Halaman Daftar Kerja Petugas (Target MC)"""
        return render_template('belum_bayar.html')

    @app.route('/tagihan-berekor')
    def tagihan_berekor_page():
        """Halaman khusus untuk menangani tunggakan lama (Ardebt)"""
        return render_template('tagihan_berekor.html')

    @app.route('/performa')
    def performa_page():
        """Halaman Grafik & Leaderboard Petugas"""
        return render_template('performa.html')

    @app.route('/setting-rute')
    def setting_rute_page():
        """Halaman Mapping Petugas ke PCEZ secara Manual/Upload"""
        return render_template('setting_rute.html')

    @app.route('/upload')
    def upload_page():
        """Halaman Panel Upload Excel (MC/MB/Col/Ardebt/Rute)"""
        return render_template('upload.html')

    @app.route('/wa-blast')
    def wa_blast_page():
        """Halaman Pengiriman Pesan Massal (WA Blast)"""
        return render_template('wa_blast.html')

    @app.route('/history')
    def history_page():
        """Halaman Riwayat Log Kunjungan & Upload"""
        return render_template('history.html')

    # --- SERVING FILES (FOTO) ---
    @app.route('/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Menyajikan foto bukti kunjungan agar muncul di browser/WA"""
        # Pastikan KUNJUNGAN_FOLDER didefinisikan di config.py
        return send_from_directory(app.config.get('KUNJUNGAN_FOLDER', 'static/uploads/kunjungan'), filename)

    return app

# Main Entry Point
if __name__ == '__main__':
    app = create_app()
    # Host '0.0.0.0' agar bisa diakses lewat IP LAN oleh HP petugas lapangan
    app.run(host='0.0.0.0', port=5000, debug=True)
