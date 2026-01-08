"""
Flask Application - Sunter Dashboard Pro
Mobile-first water billing dashboard with file processing

Author: Sunter Team
Updated: 2026-01-08
"""

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
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.pcez_performance import register_pcez_routes

def get_db():
    """Koneksi database terpusat dengan optimasi WAL Mode."""
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
            
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        
        # Optimasi performa untuk akses simultan banyak petugas
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Database & Pastikan Struktur Folder Unggahan Tersedia
    with app.app_context():
        Config.init_app(app)
        init_db(app) # Menjalankan migrasi otomatis kolom volume, dll.
        
        # Penanganan folder secara absolut agar robust saat deployment di VPS/Server
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'temp')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                # Set permission 755 agar folder bisa dibaca oleh web server (nginx/apache)
                os.chmod(folder, 0o755)
                print(f"📁 Folder Created & Secured: {folder}")

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- REGISTRASI BLUEPRINT API (Sinkronisasi dengan Log Error 404) ---
    # Pastikan url_prefix menggunakan tanda hubung '-' agar sesuai dengan pemanggilan fetch di frontend
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    
    # Registrasi rute performa (Full Stats & Reminders)
    register_pcez_routes(app, get_db)

    # --- RUTE NAVIGASI FRONTEND ---
    @app.route('/')
    def index(): return render_template('index.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): return render_template('belum_bayar.html')

    @app.route('/tunggakan-berekor')
    def tunggakan_berekor_page(): return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): return render_template('janji_bayar.html')

    @app.route('/galeri')
    def galeri_page(): return render_template('galeri.html')

    @app.route('/history-bayar')
    def history_bayar_page(): return render_template('history_bayar.html')

    @app.route('/performa')
    def performa_page(): return render_template('performa.html')

    @app.route('/setting-rute')
    def setting_rute_page(): return render_template('setting_rute.html')

    @app.route('/upload')
    def upload_page(): return render_template('upload.html')

    @app.route('/wa-blast')
    def wa_blast_page(): return render_template('wa_blast.html')

    @app.route('/history')
    def history_page(): return render_template('history.html')

    # --- SERVING FILES (HANDLING ROBUST FOTO KUNJUNGAN) ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        # Pastikan file benar-benar ada sebelum dikirim untuk mencegah error 404 statis
        if not os.path.isfile(os.path.join(folder, filename)):
            # Jika file tidak ada, kirim placeholder atau return 404 standar
            return "File not found", 404
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    # Mode debug dimatikan jika dalam produksi untuk keamanan
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
