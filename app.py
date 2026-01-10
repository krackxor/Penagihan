"""
Flask Application - Sunter Dashboard Pro
Updated: 2026-01-10 (Smart Autopilot & Synergy Version)
Sinergi: 
1. Level 1 (Publik/Guest): Monitoring Realisasi & Statistik Global.
2. Level 2 (Petugas): Operasional Penagihan & Laporan Lapangan.
3. Level 3 (Admin): Pusat Kendali Data, User, & Sinkronisasi Excel.
"""

import os
from datetime import timedelta
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify

# Import Konfigurasi, Database & Helpers
from config import Config
from core.database import init_db, get_db_connection
from core.helpers import get_role_redirect

# Import Blueprints (Sistem Modular API)
from api.upload import upload_bp
from api.history import history_bp
from api.rute import rute_bp
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.collection import collection_bp
from api.pcez_performance import register_pcez_routes
from api.auth import auth_bp

def create_app():
    # Inisialisasi Flask menggunakan objek Konfigurasi Smart
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # AUTOPILOT SESSION: Durasi Sesi 12 Jam agar petugas tidak login ulang saat di lapangan
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

    # INISIALISASI DATABASE & FOLDER SISTEM (Autopilot Startup)
    with app.app_context():
        init_db(app) 
        # Memastikan infrastruktur folder static tersedia untuk penyimpanan foto & temp excel
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'temp')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                print(f"✅ Autopilot: Folder created -> {folder}")

    @app.teardown_appcontext
    def close_connection(exception):
        """Menjamin koneksi database ditutup setiap selesai request untuk mencegah 'Database Locked'."""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- MIDDLEWARE: SMART SECURITY LAYER (ACCESS CONTROL) ---
    @app.before_request
    def security_layer():
        """
        Lapis Keamanan Terpadu:
        - Guest/Publik: Bisa akses Dashboard & Grafik Realisasi.
        - Petugas/Admin: Bisa akses Data Nasabah & Input Laporan.
        """
        # DAFTAR PUTIH (Endpoint yang terbuka untuk publik/tanpa login)
        public_endpoints = [
            'index', 'monitoring_collection_page', 'auth.login', 
            'login_page', 'static', 'serve_kunjungan_photo', 
            'auth.check_session', 'get_full_stats', 'get_reminders', 
            'collection.daily_monitor'
        ]
        
        endpoint = request.endpoint
        
        # Izinkan akses jika rute masuk daftar putih atau file statis
        if not endpoint or endpoint in public_endpoints:
            return

        # 1. Validasi Sesi (User harus login untuk rute operasional)
        if 'role' not in session:
            # Jika akses via API, kirim pesan error JSON agar dashboard tidak blank
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    "status": "error", 
                    "message": "Sesi berakhir. Silakan login kembali."
                }), 401
            return redirect(url_for('login_page'))
        
        # 2. Proteksi Pusat Kendali (Admin Only)
        admin_only_endpoints = [
            'admin_dashboard', 'performa_page', 'wa_blast_page', 'history_page',
            'upload.handle_upload', 'rute.save_rute_manual'
        ]
        
        user_role = str(session.get('role', 'publik')).lower()
        
        if endpoint in admin_only_endpoints and user_role != 'admin':
            # Jika petugas mencoba akses rute admin, kembalikan ke dashboard petugas
            return redirect(url_for('belum_bayar_page'))

    # --- REGISTRASI MODUL API (BLUEPRINTS) ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection') 
    
    # Registrasi rute performa cerdas (get_full_stats & get_reminders)
    register_pcez_routes(app, get_db_connection)

    # --- NAVIGASI FRONTEND (UI ROUTES) ---
    
    # LEVEL 1: DASHBOARD MONITORING (GUEST & ALL ROLES)
    @app.route('/')
    def index(): 
        return render_template('index.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        return render_template('monitoring_collection.html')

    @app.route('/login')
    def login_page(): 
        # Jika sudah login, otomatis arahkan ke rute yang sesuai perannya
        if 'role' in session: 
            return redirect(get_role_redirect(session['role']))
        return render_template('login.html')

    # LEVEL 2: PENAGIHAN LAPANGAN (PETUGAS & ADMIN)
    @app.route('/belum-bayar')
    def belum_bayar_page(): 
        return render_template('belum_bayar.html')

    @app.route('/tunggakan-berekor')
    def tunggakan_berekor_page(): 
        return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): 
        return render_template('janji_bayar.html')

    # LEVEL 3: ADMIN CONTROL CENTER (ADMIN ONLY)
    @app.route('/admin/dashboard')
    def admin_dashboard(): 
        return render_template('admin_dashboard.html')

    @app.route('/performa')
    def performa_page(): 
        return render_template('performa.html')

    @app.route('/history')
    def history_page(): 
        return render_template('history.html')

    # --- FILE SERVING (SMART STATIC ASSETS) ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Menyajikan foto bukti kunjungan agar bisa di-audit oleh Publik/Admin."""
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

# --- RUNNER SISTEM ---
if __name__ == '__main__':
    # host 0.0.0.0 memungkinkan akses via IP lokal (Wifi) untuk testing di HP Petugas
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
