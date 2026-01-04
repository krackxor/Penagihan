import os
import sqlite3
from flask import Flask, render_template, g, send_from_directory, current_app
from core.database import init_db
from config import Config

# Import API Routes
from api.upload import upload_bp
from api.history import history_bp
from api.belum_bayar import register_belum_bayar_routes
from api.pcez_performance import register_pcez_routes

def get_db():
    """Mengelola koneksi database dengan mode WAL & Timeout"""
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE')
        if not db_path:
            db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'penagihan.db')
            
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    with app.app_context():
        init_db(app)
        Config.init_app(app)

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # Register Blueprints & Custom Routes
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    
    register_belum_bayar_routes(app, get_db)
    register_pcez_routes(app, get_db)

    # Routes Frontend
    @app.route('/')
    def index(): return render_template('index.html')

    @app.route('/upload')
    def upload_page(): return render_template('upload.html')

    @app.route('/history')
    def history_page(): return render_template('history.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): return render_template('belum_bayar.html')

    @app.route('/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        return send_from_directory(app.config['KUNJUNGAN_FOLDER'], filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
