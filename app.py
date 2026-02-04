"""
Flask Application - Area Service Integrated System (V13.4 Security Patch)
Updated: 2026-02-05
---------------------------------------------------------------------------
Fixes Log:
1. ✅ PUBLIC ACCESS: Middleware fix for youtube/materi.
2. ✅ FIX 413: Sync Max upload size with Config (64MB-100MB).
3. ✅ WA SHARE LINK: Public access allowed.
4. ✅ ANALISA PARETO: Modul Top 500 Admin.
5. ✅ PREMIUM CUSTOMER: Modul Monitoring Pelanggan > 75m3 (Stabil).
6. ✅ PELANGGAN EKSTREM: Modul Investigasi Lonjakan > 100%.
7. ✅ PELANGGAN DROP: Modul Investigasi Penurunan > 50%.
8. ✅ GIS MAPPING: Peta Sebaran Anomali & Tagging Lokasi.
9. 🔒 SECURITY: Added login requirement for visit photos.
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
from api.analisa_top_500 import analisa_top500_bp 
from api.premium import premium_bp 
from api.ekstrem import ekstrem_bp 
from api.drop import drop_bp 
from api.map_gis import map_bp 

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
    
    # Menjamin batas unggahan mengikuti Config atau default 64MB jika tidak disetel
    app.config['MAX_CONTENT_LENGTH'] = getattr(Config, 'MAX_CONTENT_LENGTH', 64 * 1024 * 1024) 

    # --- 1. STARTUP PROTOCOL ---
    with app.app_context():
        init_db(app) 
        # Folder diinisialisasi melalui Config.init_app untuk konsistensi
        Config.init_app(app)

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
        """
        endpoint = request.endpoint
        
        # ✅ BYPASS OTOMATIS: Static files & WA Public Share Link
        if not endpoint or endpoint == 'static' or request.path.startswith('/api/history/share/view/'):
            return None

        # Daftar nama fungsi publik
        public_endpoints = [
            'login_page',
            'auth.login',
            'youtube_page',
            'materi_page',
            'index'
        ]

        # JIKA AKSES PUBLIK: Izinkan
        if endpoint in public_endpoints:
            return

        # JIKA AKSES PRIVAT: Cek Login
        if 'role' not in session:
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"status": "error", "message": "Otoritas Diperlukan"}), 401
            return redirect(url_for('login_page'))
        
        # PROTEKSI ROLE ADMINISTRATOR
        admin_only_endpoints = [
            'admin_dashboard', 'monitoring_lokasi_page', 'wa_blast_page',
            'upload.handle_smart_upload', 'history_page',
            'analisa_top500_page', 'premium_customer_page',
            'pelanggan_ekstrem_page', 'pelanggan_drop_page',
            'peta_sebaran_page'
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
    app.register_blueprint(analisa_top500_bp, url_prefix='/api/analisa')
    app.register_blueprint(premium_bp, url_prefix='/api/premium')
    app.register_blueprint(ekstrem_bp, url_prefix='/api/ekstrem') 
    app.register_blueprint(drop_bp, url_prefix='/api/drop') 
    app.register_blueprint(map_bp, url_prefix='/api/map')
    
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

    @app.route('/analisa-top500')
    def analisa_top500_page():
        return render_template('analisa_top500.html')

    @app.route('/premium-customer')
    def premium_customer_page():
        return render_template('premium_customer.html')

    @app.route('/pelanggan-ekstrem')
    def pelanggan_ekstrem_page():
        return render_template('pelanggan_ekstrem.html')

    @app.route('/pelanggan-drop')
    def pelanggan_drop_page():
        return render_template('pelanggan_drop.html')

    @app.route('/peta-sebaran')
    def peta_sebaran_page():
        return render_template('peta_sebaran.html')

    # --- 5. SECURE FILE SERVING ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        # Tambahan Keamanan: Hanya user login yang bisa akses foto
        if 'role' not in session:
            return abort(403)
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
