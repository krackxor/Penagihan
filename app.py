"""
Flask Application - Sunter Dashboard Pro
Sinergi: 
1. Sistem Login 3 Level (Publik, Petugas, Admin).
2. Proteksi Rute: Kunci rute penagihan per Petugas (Field Security).
3. Admin Control Center: Manajemen Rute, WA Blast, & Sinkronisasi Excel.
"""

import os
import sqlite3
from flask import Flask, render_template, g, send_from_directory, current_app, session, redirect, url_for, request

# Import Konfigurasi & Core
from config import Config
from core.database import init_db

# Import Blueprints (API System)
from api.upload import upload_bp
from api.history import history_bp
from api.rute import rute_bp
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.collection import collection_bp 
from api.pcez_performance import register_pcez_routes
from api.auth import auth_bp 

def get_db():
    """Mengelola koneksi database dengan optimasi WAL Mode."""
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        # WAL Mode untuk konkurensi tinggi (Petugas lapor bersamaan)
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    with app.app_context():
        Config.init_app(app)
        init_db(app) # Inisialisasi Tabel & User Admin Default
        
        # Pastikan folder penyimpanan foto bukti tersedia
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'temp')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- MIDDLEWARE: SECURITY LEVEL 3 ---
    @app.before_request
    def security_layer():
        """
        Melindungi rute operasional. 
        Petugas tidak bisa masuk ke menu Admin (Upload/Mapping).
        Publik tidak bisa melihat rute penagihan.
        """
        public_routes = [
            'index', 'monitoring_collection_page', 'auth.login', 
            'login_page', 'static', 'serve_kunjungan_photo'
        ]
        
        # Jika bukan rute publik, cek status login
        if request.endpoint and request.endpoint not in public_routes:
            if 'role' not in session:
                return redirect(url_for('login_page'))
            
            # Filter Admin Only (Hanya role 'admin' yang bisa mengakses menu manajemen)
            admin_only_routes = [
                'upload_page', 'setting_rute_page', 'wa_blast_page', 
                'history_page', 'admin_dashboard', 'performa_page'
            ]
            if request.endpoint in admin_only_routes and session.get('role') != 'admin':
                return redirect(url_for('index'))

    # --- REGISTRASI BLUEPRINT API ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection') 
    
    # Registrasi rute performa PCEZ (Mapping rute lapangan)
    register_pcez_routes(app, get_db)

    # --- RUTE NAVIGASI FRONTEND ---
    
    # LEVEL 1: AKSES UMUM (Dashboard & Realisasi Harian)
    @app.route('/')
    def index(): 
        return render_template('index.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        return render_template('monitoring_collection.html')

    @app.route('/login')
    def login_page(): 
        if 'role' in session: return redirect(url_for('index'))
        return render_template('login.html')

    # LEVEL 2: OPERASIONAL PETUGAS (Field Work)
    @app.route('/belum-bayar')
    def belum_bayar_page(): 
        return render_template('belum_bayar.html')

    @app.route('/tunggakan-berekor')
    def tunggakan_berekor_page(): 
        return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): 
        return render_template('janji_bayar.html')

    @app.route('/galeri')
    def galeri_page(): 
        return render_template('galeri.html')

    # LEVEL 3: PUSAT KENDALI (Administrator Only)
    @app.route('/admin/dashboard')
    def admin_dashboard(): 
        return render_template('admin_dashboard.html')

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

    # --- FILE SERVING ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Melayani foto bukti kunjungan petugas untuk audit Admin."""
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    # Host 0.0.0.0 agar bisa diakses oleh HP Petugas di jaringan yang sama
    app.run(host='0.0.0.0', port=5000, debug=True)
