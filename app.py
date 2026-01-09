import os
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify
from config import Config
from core.database import init_db, get_db_connection
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

    @app.before_request
    def security_layer():
        # Tambahkan endpoint publik agar navigasi dasar muncul
        public_endpoints = [
            'index', 'monitoring_collection_page', 'auth.login', 
            'login_page', 'static', 'serve_kunjungan_photo', 'auth.check_session'
        ]
        
        endpoint = request.endpoint
        if not endpoint or endpoint in public_endpoints:
            return

        if 'role' not in session:
            # Jika permintaan API, kirim JSON 401 (Bukan redirect HTML)
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"status": "error", "message": "Sesi berakhir. Silakan login ulang."}), 401
            return redirect(url_for('login_page'))
        
        admin_only = ['upload_page', 'setting_rute_page', 'admin_dashboard', 'performa_page', 'history_page']
        user_role = str(session.get('role', '')).lower()
        
        if endpoint in admin_only and user_role != 'admin':
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Akses Admin diperlukan"}), 403
            return redirect(url_for('index'))

    # Registrasi Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection') 
    
    register_pcez_routes(app, get_db_connection)

    @app.route('/')
    def index(): return render_template('index.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): return render_template('monitoring_collection.html')

    @app.route('/login')
    def login_page(): 
        if 'role' in session: return redirect(url_for('index'))
        return render_template('login.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): return render_template('belum_bayar.html')

    @app.route('/tunggakan-berekor')
    def tunggakan_berekor_page(): return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): return render_template('janji_bayar.html')

    @app.route('/admin/dashboard')
    def admin_dashboard(): return render_template('admin_dashboard.html')

    @app.route('/upload')
    def upload_page(): return render_template('upload.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
