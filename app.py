"""
Flask Application - Sunter Dashboard Pro
Sinergi: 
1. Sistem Login 3 Level (Publik, Petugas, Admin).
2. Global Monitoring: Dashboard & Stats terbuka untuk Guest (Universal Data).
3. Admin Control Center: Manajemen Terpadu (User, Rute, & Sinkronisasi Excel).
"""

import os
from datetime import timedelta
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify

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
    
    # Durasi Sesi: 12 Jam (Mencegah Logout paksa saat jam operasional lapangan)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

    # Inisialisasi Environment & Folder Sistem
    with app.app_context():
        init_db(app) 
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

    # --- MIDDLEWARE: SECURITY LAYER 5 (FULL GUEST ACCESS FOR DASHBOARD) ---
    @app.before_request
    def security_layer():
        """
        Lapis Keamanan Terpadu:
        - Membuka akses rute statistik agar Guest bisa melihat Dashboard Realisasi.
        - Mengunci data pribadi nasabah dan fitur administratif.
        """
        # DAFTAR PUTIH (Endpoint yang BISA diakses TANPA LOGIN)
        public_endpoints = [
            'index',                        # Halaman Home
            'monitoring_collection_page',   # Halaman Monitoring Harian
            'auth.login',                   # API Login
            'login_page',                   # Halaman Login HTML
            'static',                       # File CSS/JS/Gambar
            'serve_kunjungan_photo',        # Foto Bukti (Audit Publik)
            'auth.check_session',           # Validasi Sesi Frontend
            'get_full_stats',               # API Statistik Dashboard Utama
            'get_reminders',                # API Janji Bayar Dashboard
            'collection.daily_monitor'      # API Monitoring Harian
        ]
        
        endpoint = request.endpoint
        
        # Izinkan jika endpoint ada dalam daftar putih
        if not endpoint or endpoint in public_endpoints:
            return

        # 1. Validasi Sesi: Jika rute tidak publik dan tidak ada sesi, blokir.
        if 'role' not in session:
            # Jika permintaan dari AJAX/API, kirim JSON 401 (agar dashboard tidak blank)
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    "status": "error", 
                    "message": "Sesi berakhir. Navigasi memerlukan login."
                }), 401
            return redirect(url_for('login_page'))
        
        # 2. Otorisasi Admin: Proteksi fitur Pusat Kendali
        admin_only_endpoints = [
            'admin_dashboard', 'performa_page', 'wa_blast_page', 'history_page'
        ]
        
        user_role = str(session.get('role', 'publik')).lower()
        
        if endpoint in admin_only_endpoints and user_role != 'admin':
            if request.path.startswith('/api/'):
                return jsonify({
                    "status": "error", 
                    "message": "Akses Ditolak: Memerlukan level Admin."
                }), 403
            return redirect(url_for('index'))

    # --- REGISTRASI BLUEPRINT API ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection') 
    
    # Registrasi rute performa (get_full_stats & get_reminders)
    register_pcez_routes(app, get_db_connection)

    # --- RUTE NAVIGASI FRONTEND ---
    
    # LEVEL 1: INFORMASI PUBLIK (Guest & All Roles)
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

    # LEVEL 2: OPERASIONAL (Hanya Petugas & Admin)
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

    # LEVEL 3: PUSAT KENDALI (Hanya Admin)
    @app.route('/admin/dashboard')
    def admin_dashboard(): 
        return render_template('admin_dashboard.html')

    @app.route('/performa')
    def performa_page(): 
        return render_template('performa.html')

    @app.route('/wa-blast')
    def wa_blast_page(): 
        return render_template('wa_blast.html')

    @app.route('/history')
    def history_page(): 
        return render_template('history.html')

    # --- REDIRECTS LEGACY ---
    @app.route('/upload')
    @app.route('/setting-rute')
    def legacy_redirects():
        return redirect(url_for('admin_dashboard'))

    # --- FILE SERVING ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
