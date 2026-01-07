"""
Flask Application - Sunter Dashboard Pro
Mobile-first water billing dashboard with file processing

Author: Sunter Team
Updated: 2026-01-07
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
    """
    Koneksi database terpusat dengan optimasi WAL Mode.
    """
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
            
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        
        # Optimasi Write-Ahead Logging untuk performa tinggi
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Database & Pastikan Folder Upload Ada
    with app.app_context():
        Config.init_app(app)
        init_db(app)
        
        # Buat folder kunjungan jika belum ada
        upload_path = app.config.get('KUNJUNGAN_FOLDER', 'static/uploads/kunjungan')
        if not os.path.exists(upload_path):
            os.makedirs(upload_path, exist_ok=True)
            print(f"📁 Created upload folder: {upload_path}")

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- REGISTRASI BLUEPRINT API ---
    # Perbaikan: url_prefix disesuaikan agar menjadi /api/upload/upload dan /api/upload/data-status
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    
    app.register_blueprint(history_bp, url_prefix='/api')
    app.register_blueprint(rute_bp, url_prefix='/api')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    
    # --- REGISTRASI RUTE DINAMIS ---
    register_pcez_routes(app, get_db)

    # --- RUTE NAVIGASI FRONTEND ---
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/belum-bayar')
    def belum_bayar_page():
        return render_template('belum_bayar.html')

    @app.route('/tunggakan-berekor')
    def tunggakan_berekor_page():
        return render_template('tagihan_berekor.html')

    @app.route('/history-bayar')
    def history_bayar_page():
        return render_template('history_bayar.html')

    @app.route('/performa')
    def performa_page():
        return render_template('performa.html')

    @app.route('/setting-rute')
    def setting_rute_page():
        return render_template('setting_rute.html')

    @app.route('/upload')
    def upload_page():
        return render_template('upload.html')

    @app.route('/wa-blast')
    def wa_blast_page():
        return render_template('wa_blast.html')

    @app.route('/history')
    def history_page():
        return render_template('history.html')

    # --- SERVING FILES ---
    @app.route('/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        return send_from_directory(app.config.get('KUNJUNGAN_FOLDER', 'static/uploads/kunjungan'), filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
