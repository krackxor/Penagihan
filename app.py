"""
Flask Application - Area Service Integrated System (V12.73 High-Load + Analisa Module)
Updated: 2026-02-02
---------------------------------------------------------------------------
Fixes Log:
1. ✅ PUBLIC ACCESS: Memperbaiki logika Middleware agar 'youtube_page' dan 'materi_page' 
   dapat diakses tanpa dialihkan ke menu login.
2. ✅ FIX 413: Mempertahankan MAX_CONTENT_LENGTH (64MB) untuk multi-upload history.
3. ✅ ROUTING: Konsistensi dual-endpoint Admin/Petugas dan Database V12.97 sync.
4. ✅ WA SHARE LINK: Mengizinkan akses publik ke link preview share WA.
5. ✅ ANALISA PARETO: Menambahkan modul Top 500 khusus admin.
"""

import os
from datetime import timedelta
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify

# [IMPORT CORE]
from config import Config
from core.database import init_db, get_db_connection
from core.helpers import get_role_redirect

# [IMPORT BLUEPRINTS]
from api.auth import auth_bp
from api.dashboard import dashboard_bp 
from api.upload import upload_bp  
from api.history import history_bp
from api.rute import rute_bp
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.collection import collection_bp
from api.pcez_performance import register_pcez_routes
from api.wa_gateway import wa_bp
from api.analisa_top_500 import analisa_top500_bp  # <--- ✅ IMPORT BARU

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
    
    # --- FIX 413 ERROR: Konfigurasi Batas Unggahan (64 Megabyte) ---
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024 

    # --- 1. STARTUP PROTOCOL ---
    with app.app_context():
        init_db(app) 
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'materi')
        ]
        for folder in folders:
            os.makedirs(folder, exist_ok=True)

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # --- 2. MIDDLEWARE: SECURITY LAYER ---
    @app.before_request
    def security_layer():
        """
        [GATEKEEPER]: Mengontrol hak akses publik vs privat.
        Pengecekan menggunakan endpoint Flask (nama fungsi) untuk akurasi tinggi.
        """
        # Daftar nama fungsi yang boleh diakses publik tanpa login
        public_endpoints = [
            'login_page',
            'auth.login',
            'youtube_page',    # Fungsi halaman video sosialisasi
            'materi_page',     # Fungsi halaman literatur materi
            'static',          # Folder CSS, JS, Images
            'serve_kunjungan_photo',
            'index',           # Beranda/Landing Page
            'history.public_share_view' # <--- WA Share Link
        ]
        
        endpoint = request.endpoint
        
        # ✅ BYPASS LINK SHARE WA & STATIC FILE
        # Mengizinkan akses jika URL dimulai dengan path tertentu (meskipun endpoint mungkin berbeda)
        if request.path.startswith('/api/history/share/view/') or request.path.startswith('/static/'):
            return None

        # JIKA AKSES PUBLIK: Langsung izinkan akses
        if not endpoint or endpoint in public_endpoints:
            return

        # JIKA AKSES PRIVAT: Cek ketersediaan sesi login
        if 'role' not in session:
            # Jika akses via API atau AJAX, kirim JSON error 401
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"status": "error", "message": "Otoritas Diperlukan"}), 401
            # Jika akses via browser ke halaman terproteksi, lempar ke login
            return redirect(url_for('login_page'))
        
        # PROTEKSI ROLE KHUSUS ADMINISTRATOR
        admin_only_endpoints = [
            'admin_dashboard', 'monitoring_lokasi_page', 'wa_blast_page',
            'upload.handle_smart_upload', 'history_page',
            'analisa_top500_page' # <--- ✅ Page Baru Admin Only
        ]
        
        user_role = str(session.get('role', 'petugas')).lower()
        if endpoint in admin_only_endpoints and user_role != 'admin':
            return redirect(url_for('index'))

    # --- 3. REGISTRASI BLUEPRINTS ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection')
    app.register_blueprint(wa_bp, url_prefix='/api/wa-gateway') 
    app.register_blueprint(analisa_top500_bp, url_prefix='/api/analisa') # <--- ✅ REGISTRASI API BARU
    register_pcez_routes(app, get_db_connection)

    # --- 4. NAVIGASI FRONTEND (UI ROUTES) ---
    
    @app.route('/')
    def index(): 
        return render_template('index.html')

    @app.route('/login')
    def login_page(): 
        if 'role' in session: 
            return redirect(get_role_redirect(session['role']))
        return render_template('login.html')

    @app.route('/youtube')
    def youtube_page():
        return render_template('youtube.html')

    @app.route('/materi')
    def materi_page():
        materi_dir = os.path.join(app.root_path, 'static', 'uploads', 'materi')
        files = os.listdir(materi_dir) if os.path.exists(materi_dir) else []
        return render_template('materi.html', files=files)

    # --- RUTE TERPROTEKSI (MEMERLUKAN LOGIN) ---
    @app.route('/performa')
    def performa_page(): 
        return render_template('performa.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        return render_template('monitoring_collection.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): 
        return render_template('belum_bayar.html')

    @app.route('/tagihan-berekor')
    def ardebt_page(): 
        return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): 
        return render_template('janji_bayar.html')

    @app.route('/galeri')
    def galeri_page():
        return render_template('galeri.html')

    @app.route('/history-bayar')
    def history_bayar_page(): 
        return render_template('history_bayar.html')

    @app.route('/history-kunjungan')
    def history_kunjungan_page(): 
        return render_template('history_kunjungan.html')

    @app.route('/admin/dashboard')
    def admin_dashboard(): 
        return render_template('admin_dashboard.html')

    @app.route('/monitoring-lokasi')
    def monitoring_lokasi_page():
        return render_template('monitoring_lokasi.html')

    @app.route('/wa-blast')
    def wa_blast_page():
        return render_template('wa_blast.html')

    @app.route('/history')
    def history_page(): 
        return render_template('history.html')

    # ✅ HALAMAN BARU KHUSUS ADMIN
    @app.route('/analisa-top500')
    def analisa_top500_page():
        return render_template('analisa_top500.html')

    # --- 5. SECURE FILE SERVING ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
