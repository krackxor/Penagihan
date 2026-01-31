"""
Flask Application - Area Service Integrated System (V12.68 Stable)
Updated: 2026-01-31
---------------------------------------------------------------------------
Pembaruan:
1. Full Route Mapping: Mendaftarkan 17 halaman (History Bayar, Janji Bayar, Performa, dll).
2. Security Layer Sync: Menyesuaikan proteksi rute admin dan publik sesuai daftar terbaru.
3. Integrity Check: Penambahan rute eksplisit untuk mendukung navigasi base.html.
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

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

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

    # --- 2. MIDDLEWARE: SECURITY LAYER V12.68 ---
    @app.before_request
    def security_layer():
        # Endpoint yang bisa diakses tanpa login
        public_endpoints = [
            'index', 
            'monitoring_collection_page', 
            'dashboard.get_pusat_kendali', 
            'auth.login', 
            'login_page', 
            'static', 
            'serve_kunjungan_photo', 
            'youtube_page', 
            'materi_page'
        ]
        
        endpoint = request.endpoint
        if not endpoint or endpoint in public_endpoints:
            return

        # Proteksi Sesi (Harus Login)
        if 'role' not in session:
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"status": "error", "message": "Sesi Berakhir"}), 401
            return redirect(url_for('login_page'))
        
        # Proteksi Khusus Admin
        admin_only_endpoints = [
            'admin_dashboard', 
            'monitoring_lokasi_page', 
            'wa_blast_page',
            'upload.handle_smart_upload',
            'history_page' # Halaman log upload excel
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
    register_pcez_routes(app, get_db_connection)

    # --- 4. NAVIGASI FRONTEND (UI ROUTES) ---
    
    # [DASHBOARD & MONITORING]
    @app.route('/')
    def index(): 
        return render_template('index.html')

    @app.route('/performa')
    def performa_page(): 
        return render_template('performa.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        return render_template('monitoring_collection.html')

    @app.route('/login')
    def login_page(): 
        if 'role' in session: 
            return redirect(get_role_redirect(session['role']))
        return render_template('login.html')

    # [UNIT PELAKSANA LAPANGAN]
    @app.route('/belum-bayar')
    def belum_bayar_page(): 
        return render_template('belum_bayar.html')

    @app.route('/tunggakan-berekor')
    def ardebt_page(): 
        return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): 
        return render_template('janji_bayar.html')

    @app.route('/galeri')
    def galeri_page():
        return render_template('galeri.html')

    # [RIWAYAT & ARSIP]
    @app.route('/history-bayar')
    def history_bayar_page(): 
        return render_template('history_bayar.html')

    @app.route('/history-kunjungan')
    def history_kunjungan_page(): 
        return render_template('history_kunjungan.html')

    # [ADMINISTRASI STRATEGIS & AUDIT]
    @app.route('/admin/dashboard')
    def admin_dashboard(): 
        return render_template('admin_dashboard.html')

    @app.route('/admin/monitoring-lokasi')
    def monitoring_lokasi_page():
        return render_template('monitoring_lokasi.html')

    @app.route('/admin/wa-blast')
    def wa_blast_page():
        return render_template('wa_blast.html')

    @app.route('/admin/history-upload')
    def history_page(): 
        return render_template('history.html')

    # [MEDIA & EDUKASI]
    @app.route('/youtube')
    def youtube_page():
        return render_template('youtube.html')

    @app.route('/materi')
    def materi_page():
        materi_dir = os.path.join(app.root_path, 'static', 'uploads', 'materi')
        files = os.listdir(materi_dir) if os.path.exists(materi_dir) else []
        return render_template('materi.html', files=files)

    # --- 5. SECURE FILE SERVING ---
    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
