"""
Flask Application - Sunter Dashboard Pro (V3 Smart Edition)
Updated: 2026-01-10 (Smart Autopilot & Synergy Version)

LOGIKA SINERGI AKSES:
1. Level 1 (Publik/Guest): Monitoring Realisasi & Statistik Global.
2. Level 2 (Petugas): Operasional Penagihan & Laporan Lapangan.
3. Level 3 (Admin): Pusat Kendali Data, User, WA Blast, & Sinkronisasi Excel.
"""

import os
from datetime import timedelta
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify

# Import Konfigurasi, Database & Helpers Terpadu
from config import Config
from core.database import init_db, get_db_connection
from core.helpers import get_role_redirect

# Import Blueprints (Sistem Modular API Sinergi)
from api.upload import upload_bp
from api.history import history_bp
from api.rute import rute_bp
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.collection import collection_bp
from api.pcez_performance import register_pcez_routes
from api.auth import auth_bp
from api.wa_gateway import wa_bp  # Modul WA Blast Baru

def create_app():
    # Inisialisasi Flask menggunakan objek Konfigurasi Smart
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # AUTOPILOT SESSION: Durasi Sesi 12 Jam (Cocok untuk shift kerja petugas lapangan)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

    # --- 1. STARTUP AUTOPILOT: Inisialisasi Infrastruktur ---
    with app.app_context():
        init_db(app) # Pastikan tabel-tabel (Users, MC, MB, ARDEBT) tersedia
        
        # Sinergi Folder: Memastikan folder upload foto & temp excel tersedia otomatis
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'temp')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                print(f"🚀 Autopilot: Infrastruktur siap -> {folder}")

    @app.teardown_appcontext
    def close_connection(exception):
        """Mencegah 'Database Locked' dengan menutup koneksi setiap akhir request."""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- 2. MIDDLEWARE: SMART SECURITY LAYER (ACCESS CONTROL) ---
    @app.before_request
    def security_layer():
        """
        Lapis Keamanan Terpadu:
        Menentukan siapa yang boleh melihat data sensitif nasabah.
        """
        # DAFTAR PUTIH: Bisa diakses tanpa login (Dashboard Publik)
        public_endpoints = [
            'index', 'monitoring_collection_page', 'auth.login', 
            'login_page', 'static', 'serve_kunjungan_photo', 
            'auth.check_session', 'get_full_stats', 'get_reminders', 
            'collection.daily_monitor'
        ]
        
        endpoint = request.endpoint
        
        # Jika rute tidak ada (404) atau masuk daftar putih, izinkan lewat
        if not endpoint or endpoint in public_endpoints:
            return

        # Proteksi Sesi: User wajib login untuk akses fitur operasional
        if 'role' not in session:
            # Sinergi API: Berikan response JSON jika yang merequest adalah sistem/JS
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"status": "error", "message": "Sesi berakhir. Login ulang."}), 401
            return redirect(url_for('login_page'))
        
        # Proteksi Role: Membatasi rute khusus Administrator
        admin_only_endpoints = [
            'admin_dashboard', 'performa_page', 'wa_blast_page', 
            'history_page', 'upload.handle_upload', 'rute.save_rute_manual'
        ]
        
        user_role = str(session.get('role', 'petugas')).lower()
        if endpoint in admin_only_endpoints and user_role != 'admin':
            return redirect(url_for('belum_bayar_page'))

    # --- 3. REGISTRASI BLUEPRINTS (SMART API SYSTEM) ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection')
    app.register_blueprint(wa_bp, url_prefix='/api/wa-gateway') # Integrasi WA Blast
    
    # Registrasi rute performa cerdas (Proyeksi & Analitik)
    register_pcez_routes(app, get_db_connection)

    # --- 4. NAVIGASI FRONTEND (UI ROUTES) ---
    
    # LEVEL 1: DASHBOARD MONITORING (PUBLIK/SEMUA ROLE)
    @app.route('/')
    def index(): 
        return render_template('index.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        return render_template('monitoring_collection.html')

    @app.route('/login')
    def login_page(): 
        # Autopilot Redirect: Jika sudah login, dilarang balik ke halaman login
        if 'role' in session: 
            return redirect(get_role_redirect(session['role']))
        return render_template('login.html')

    # LEVEL 2: PENAGIHAN & LAPORAN (PETUGAS & ADMIN)
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

    @app.route('/wa-blast')
    def wa_blast_page(): 
        return render_template('wa_blast.html')

    # --- 5. FILE SERVING (SMART ASSETS) ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Serving bukti foto lapangan agar bisa diaudit publik/admin."""
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

# --- RUNNER SISTEM ---
if __name__ == '__main__':
    # Host 0.0.0.0 agar aplikasi bisa diakses via Wifi oleh smartphone petugas
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
