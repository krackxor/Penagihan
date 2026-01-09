"""
Flask Application - Sunter Dashboard Pro
Mobile-first water billing dashboard with file processing and automated reporting.

Sinergi: 
1. Mengintegrasikan sistem pelaporan WhatsApp Internal.
2. Mendukung Pintu Ganda (MC + Ardebt) dalam satu dashboard.
3. Optimasi Database WAL Mode untuk akses simultan petugas lapangan.

Author: Sunter Team
Updated: 2026-01-09
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
from api.collection import collection_bp 
from api.pcez_performance import register_pcez_routes

def get_db():
    """Koneksi database terpusat dengan optimasi WAL Mode agar tidak locking saat banyak petugas upload foto."""
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
            
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        
        # Optimasi performa: WAL Mode sangat penting agar baca/tulis data tidak bergantian (antre)
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Database & Pastikan Struktur Folder Unggahan Tersedia
    with app.app_context():
        Config.init_app(app)
        init_db(app) # Migrasi otomatis: Menambahkan kolom no_admin, nomet, volume, rayon jika belum ada.
        
        # Penanganan folder secara absolut untuk menyimpan foto kunjungan mandatori
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'temp')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                # Permission 755 agar gambar bisa tampil di dashboard (akses publik terbatas)
                os.chmod(folder, 0o755)
                print(f"📁 Folder Ready: {folder}")

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- REGISTRASI BLUEPRINT API ---
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection') 
    
    # Registrasi rute performa (Full Stats & Reminders)
    register_pcez_routes(app, get_db)

    # --- RUTE NAVIGASI FRONTEND (SINERGI DASHBOARD) ---
    @app.route('/')
    def index(): return render_template('index.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): return render_template('monitoring_collection.html')

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

    # --- SERVING FILES (MODUL FOTO KUNJUNGAN) ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        if not os.path.isfile(os.path.join(folder, filename)):
            return "File not found", 404
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    # Host 0.0.0.0 agar bisa diakses via HP petugas di jaringan yang sama/internet
    app.run(host='0.0.0.0', port=5000, debug=True)
