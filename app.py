import os
from flask import Flask, render_template, g
from core.database import init_db, get_db_connection
from api.helpers import APIResponse  # Perbaikan path import
from config import Config

# Import API Routes
from api.upload import upload_bp
from api.history import history_bp
from api.belum_bayar import register_belum_bayar_routes
from api.pcez_performance import register_pcez_routes

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    with app.app_context():
        # Inisialisasi Database
        init_db(app)
        # Inisialisasi Folder (uploads/temp, dll)
        Config.init_app(app)

    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    def get_db():
        return get_db_connection()

    # Register Blueprints
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    
    # Register Custom Routes
    register_belum_bayar_routes(app, get_db)
    register_pcez_routes(app, get_db)

    @app.route('/')
    def index(): return render_template('index.html')

    @app.route('/upload')
    def upload_page(): return render_template('upload.html')

    @app.route('/history')
    def history_page(): return render_template('history.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): return render_template('belum_bayar.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
