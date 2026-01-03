import os
from flask import Flask, render_template, g
from core.database import init_db, get_db_connection
from core.helpers import APIResponse
from config import Config

# Import API Routes
from api.upload import upload_bp
from api.history import history_bp
from api.belum_bayar import register_belum_bayar_routes
from api.pcez_performance import register_pcez_routes
from api.kpi import kpi_bp
from api.analisa import analisa_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi Database & Folder Upload
    with app.app_context():
        init_db(app)
        # Pastikan folder foto kunjungan tersedia
        upload_path = os.path.join('static', 'uploads', 'kunjungan')
        if not os.path.exists(upload_path):
            os.makedirs(upload_path)

    # Database teardown
    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    # Fungsi Helper untuk Database di API
    def get_db():
        return get_db_connection()

    # --- Register Blueprints ---
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    app.register_blueprint(kpi_bp, url_prefix='/api')
    app.register_blueprint(analisa_bp, url_prefix='/api')
    
    # Register Custom Routes (Manual Register)
    register_belum_bayar_routes(app, get_db)
    register_pcez_routes(app, get_db)

    # --- Page Routes (Frontend) ---
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/upload')
    def upload_page():
        return render_template('upload.html')

    @app.route('/history')
    def history_page():
        return render_template('history.html')

    @app.route('/belum-bayar')
    def belum_bayar_page():
        """Halaman utama petugas untuk Cureent & Tunggakan"""
        return render_template('belum_bayar.html')

    @app.route('/leaderboard')
    def leaderboard_page():
        """Halaman pemantauan performa petugas"""
        return render_template('menu.html') # Bisa diarahkan ke template khusus

    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('500.html'), 500

    return app

if __name__ == '__main__':
    app = create_app()
    # Jalankan di host 0.0.0.0 agar bisa diakses dari HP petugas di jaringan yang sama
    app.run(host='0.0.0.0', port=5000, debug=True)
