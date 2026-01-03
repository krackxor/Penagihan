import os
from flask import Flask, render_template, g
from core.database import init_db, get_db_connection
from api.helpers import APIResponse # Pastikan sudah diubah dari core ke api
from config import Config

# Import API Routes
from api.upload import upload_bp
from api.history import history_bp # Sekarang file ini sudah ada
from api.belum_bayar import register_belum_bayar_routes
from api.pcez_performance import register_pcez_routes

# KOMENTARI jika file berikut belum ada di folder api/
# from api.kpi import kpi_bp 
# from api.analisa import analisa_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    with app.app_context():
        init_db(app)
        upload_path = os.path.join('static', 'uploads', 'kunjungan')
        if not os.path.exists(upload_path):
            os.makedirs(upload_path)

    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    def get_db():
        return get_db_connection()

    # --- Register Blueprints ---
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    
    # Register Custom Routes
    register_belum_bayar_routes(app, get_db)
    register_pcez_routes(app, get_db)

    # --- Page Routes ---
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
        return render_template('belum_bayar.html')

    @app.route('/leaderboard')
    def leaderboard_page():
        return render_template('menu.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
