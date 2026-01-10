"""
Flask Application - Sunter Dashboard Pro (V7.1 Enterprise Edition)
Updated: 2026-01-11 (Mimetype Optimization & Public Access Edition)

LOGIKA SINERGI AKSES (Security Matrix):
1. Level 1 (Publik/Guest): Statistik Global, Dashboard Realisasi, Youtube, & Pusat Materi.
2. Level 2 (Petugas): Fokus Target Harian, Penagihan, GPS Reporting, & Edukasi Internal.
3. Level 3 (Admin): Audit Lokasi (GPS), Management File, Kendali Data Master, User Control.
"""

import os
from datetime import timedelta
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify

# [IMPORT CORE]: Mengambil Konfigurasi, Fungsi Database, dan Helper Navigasi
from config import Config
from core.database import init_db, get_db_connection
from core.helpers import get_role_redirect

# [IMPORT BLUEPRINTS]: Sistem Modular API untuk pemisahan logika bisnis
from api.upload import upload_bp
from api.history import history_bp
from api.rute import rute_bp
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.collection import collection_bp
from api.pcez_performance import register_pcez_routes
from api.auth import auth_bp
from api.wa_gateway import wa_bp 

def create_app():
    """
    [FUNGSI UTAMA: create_app]
    Kegunaan: Engine utama untuk inisialisasi Flask, Middleware, dan registrasi Route UI/API.
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # [KONFIGURASI SESI]: Durasi login 12 jam, optimal untuk shift kerja lapangan petugas
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

    # --- 1. STARTUP AUTOPILOT: Inisialisasi Infrastruktur ---
    with app.app_context():
        # [DB INITIALIZE]: Auto-Migration untuk tabel GPS, NOMET, dan Snapshot Profiling
        init_db(app) 
        
        # [FOLDER SYNC]: Menjamin ketersediaan direktori penyimpanan file
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'temp'),
            os.path.join(app.root_path, 'static', 'uploads', 'materi')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                print(f"🚀 Infrastruktur Ready -> {folder}")

    @app.teardown_appcontext
    def close_connection(exception):
        """[FUNGSI: close_connection] Mencegah 'Database Locked' pada SQLite."""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- 2. MIDDLEWARE: SMART SECURITY LAYER (ACCESS CONTROL) ---
    @app.before_request
    def security_layer():
        """
        [FUNGSI: security_layer] Penjaga gerbang akses berdasarkan Role & Session.
        Materi dan Youtube sekarang terbuka untuk akses publik (Level 1).
        """
        # [WHITELIST]: Halaman yang bisa diakses tanpa login (Sinergi Publik)
        public_endpoints = [
            'index', 'monitoring_collection_page', 'auth.login', 
            'login_page', 'static', 'serve_kunjungan_photo', 
            'auth.check_session', 'get_full_stats', 'get_reminders', 
            'collection.daily_monitor', 'youtube_page', 'materi_page',
            'serve_materi_file' # Penting agar file materi bisa dirender publik
        ]
        
        endpoint = request.endpoint
        if not endpoint or endpoint in public_endpoints:
            return

        # [SESSION CHECK]: Proteksi area operasional Petugas & Admin
        if 'role' not in session:
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"status": "error", "message": "Sesi Berakhir"}), 401
            return redirect(url_for('login_page'))
        
        # [ROLE CHECK]: Membatasi fitur Administrator (Audit & Data Master)
        admin_only_endpoints = [
            'admin_dashboard', 'performa_page', 'wa_blast_page', 
            'history_page', 'monitoring_lokasi_page', 'upload.handle_upload'
        ]
        
        user_role = str(session.get('role', 'petugas')).lower()
        if endpoint in admin_only_endpoints and user_role != 'admin':
            return redirect(url_for('tunggakan_berekor_page'))

    # --- 3. REGISTRASI BLUEPRINTS (SMART API SYSTEM) ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection')
    app.register_blueprint(wa_bp, url_prefix='/api/wa-gateway') 
    register_pcez_routes(app, get_db_connection)

    # --- 4. NAVIGASI FRONTEND (UI ROUTES) ---
    
    @app.route('/')
    def index(): 
        """Menampilkan Dashboard Realisasi Capaian Global."""
        return render_template('index.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        """Menampilkan Monitoring Realisasi Collection Harian Petugas."""
        return render_template('monitoring_collection.html')

    @app.route('/youtube')
    def youtube_page():
        """Pusat Edukasi Video: Memuat konten dinamis YouTube PAM JAYA."""
        return render_template('youtube.html')

    @app.route('/materi')
    def materi_page():
        """Pusat Materi Online: Menampilkan daftar PDF/Word (Public Access)."""
        materi_dir = os.path.join(app.root_path, 'static', 'uploads', 'materi')
        files = os.listdir(materi_dir) if os.path.exists(materi_dir) else []
        return render_template('materi.html', files=files)

    @app.route('/login')
    def login_page(): 
        """Halaman Login dengan Autopilot Redirect."""
        if 'role' in session: 
            return redirect(get_role_redirect(session['role']))
        return render_template('login.html')

    # [OPERASIONAL LAPANGAN]
    @app.route('/tunggakan-berekor')
    def tunggakan_berekor_page(): 
        return render_template('tagihan_berekor.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): 
        return render_template('belum_bayar.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): 
        return render_template('janji_bayar.html')

    # [ADMINISTRASI & AUDIT]
    @app.route('/admin/dashboard')
    def admin_dashboard(): 
        return render_template('admin_dashboard.html')

    @app.route('/admin/monitoring-lokasi')
    def monitoring_lokasi_page():
        return render_template('monitoring_lokasi.html')

    @app.route('/performa')
    def performa_page(): 
        return render_template('performa.html')

    @app.route('/history')
    def history_page(): 
        return render_template('history.html')

    @app.route('/wa-blast')
    def wa_blast_page(): 
        return render_template('wa_blast.html')

    # --- 5. FILE SERVING & SECURITY ASSETS ---

    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Menyajikan foto bukti koordinasi lapangan."""
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    @app.route('/static/uploads/materi/<filename>')
    def serve_materi_file(filename):
        """
        [FUNGSI KRUSIAL]: Menyajikan file dengan Mimetype yang tepat.
        Logika: Mencegah browser menampilkan kode sumber dengan memaksa tipe 'application/pdf'.
        """
        folder = os.path.join(app.root_path, 'static', 'uploads', 'materi')
        # Optimasi: Deteksi otomatis ekstensi file untuk merender konten bukan kode
        ext = os.path.splitext(filename)[1].lower()
        mtype = 'application/pdf' if ext == '.pdf' else 'application/octet-stream'
        
        return send_from_directory(folder, filename, mimetype=mtype)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
