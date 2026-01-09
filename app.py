"""
Flask Application - Sunter Dashboard Pro
Sinergi: 
1. Sistem Login 3 Level (Publik, Petugas, Admin).
2. Proteksi Rute: Middleware otomatis untuk keamanan field & administratif.
3. Admin Control Center: Manajemen rute & Sinkronisasi Intelijen Excel.
"""

import os
import sqlite3
from flask import Flask, render_template, g, send_from_directory, current_app, session, redirect, url_for, request

# Import Konfigurasi & Core
from config import Config
from core.database import init_db, get_db_connection

# Import Blueprints (API System)
from api.upload import upload_bp
from api.history import history_bp
from api.rute import rute_bp
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.collection import collection_bp 
from api.pcez_performance import register_pcez_routes
from api.auth import auth_bp 

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Environment & Folder Sistem
    with app.app_context():
        init_db(app) # Inisialisasi Tabel & User Admin Default (admin_sunter)
        
        # Pastikan folder penyimpanan tersedia (Sinergi Foto Bukti)
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'temp')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)

    @app.teardown_appcontext
    def close_connection(exception):
        """Pembersihan koneksi DB setiap request selesai untuk mencegah 'Database is locked'."""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- MIDDLEWARE: SECURITY LAYER 3 ---
    @app.before_request
    def security_layer():
        """
        Lapis Keamanan Server:
        1. Mencegah akses rute internal tanpa login.
        2. Filter Level Akses: Admin, Petugas, Publik.
        """
        # Daftar rute yang terbuka untuk umum
        public_endpoints = [
            'index', 'monitoring_collection_page', 'auth.login', 
            'login_page', 'static', 'serve_kunjungan_photo'
        ]
        
        endpoint = request.endpoint
        if not endpoint or endpoint in public_endpoints:
            return

        # Cek Status Login
        if 'role' not in session:
            return redirect(url_for('login_page'))
        
        # Proteksi Khusus Level Admin (Pusat Kendali)
        admin_only_endpoints = [
            'upload_page', 'setting_rute_page', 'wa_blast_page', 
            'admin_dashboard', 'performa_page', 'history_page'
        ]
        
        if endpoint in admin_only_endpoints and session.get('role') != 'admin':
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
    register_pcez_routes(app, get_db_connection)

    # --- RUTE NAVIGASI FRONTEND (SINERGI TEMPLATES) ---
    
    # LEVEL 1: AKSES UMUM
    @app.route('/')
    def index(): 
        return render_template('index.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        return render_template('monitoring_collection.html')

    @app.route('/login')
    def login_page(): 
        if 'role' in session: 
            return redirect(url_for('index'))
        return render_template('login.html')

    # LEVEL 2: OPERASIONAL PETUGAS
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

    # LEVEL 3: PUSAT KENDALI ADMIN
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

    # --- FILE SERVING (Audit Visual) ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Akses aman untuk melihat foto bukti laporan petugas."""
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    # Host 0.0.0.0 agar dashboard bisa dibuka oleh banyak HP petugas di jaringan yang sama
    app.run(host='0.0.0.0', port=5000, debug=True)
