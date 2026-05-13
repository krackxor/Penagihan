import os
from flask import Flask, render_template, redirect, url_for
from models import db
from sqlalchemy import text 
from celery import Celery # Import Celery untuk tugas asinkron

# --- 1. IMPORT BLUEPRINTS ---
from api.monitoring import monitoring_bp
from api.daily import daily_bp  
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 
from api.top_500 import top_500_bp 
from api.admin import admin_bp 
from api.ocr import ocr_bp 
from api.converter import converter_bp 
from api.optimizer import optimizer_bp 
from api.search import search_bp 

def create_app():
    app_flask = Flask(__name__)

    # --- 2. KONFIGURASI SINERGI & KEAMANAN ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app_flask.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app_flask.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app_flask.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sinergi-pam-jaya-2026')
    
    app_flask.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    app_flask.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 # 1 GB

    # --- 3. KONFIGURASI CELERY & REDIS ---
    # Diambil dari environment variable yang didefinisikan di docker-compose.yml
    app_flask.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    app_flask.config['CELERY_RESULT_BACKEND'] = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

    # --- 4. INISIALISASI & FOLDER AUTO-CREATE ---
    db.init_app(app_flask)
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app_flask.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads', 'materi'), exist_ok=True)

    # --- 5. REGISTRASI MODUL (BLUEPRINTS) ---
    app_flask.register_blueprint(monitoring_bp, url_prefix='/monitoring')
    app_flask.register_blueprint(daily_bp, url_prefix='/monitoring/daily') 
    app_flask.register_blueprint(importer_bp, url_prefix='/api/import')
    app_flask.register_blueprint(kunjungan_bp, url_prefix='/api/kunjungan')
    app_flask.register_blueprint(sbrs_bp, url_prefix='/sbrs') 
    app_flask.register_blueprint(top_500_bp, url_prefix='/monitoring/top-500') 
    app_flask.register_blueprint(admin_bp, url_prefix='/admin')
    app_flask.register_blueprint(ocr_bp, url_prefix='/tools/ocr')
    app_flask.register_blueprint(converter_bp, url_prefix='/tools/converter')
    app_flask.register_blueprint(optimizer_bp, url_prefix='/tools/optimizer')
    app_flask.register_blueprint(search_bp, url_prefix='/search')

    # --- 6. NAVIGASI UTAMA ---
    @app_flask.route('/')
    def index():
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app_flask.route('/upload')
    def upload_page():
        return render_template('upload.html')

    @app_flask.route('/lapor')
    def lapor_page():
        return render_template('lapor.html')

    # --- 7. STARTUP PROTOCOL (V18 CLEAN ARCHITECTURE) ---
    with app_flask.app_context():
        try:
            db.create_all()
            with db.engine.connect() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_search_nama ON master_pelanggan (nama);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_search_serial ON master_pelanggan (serial);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_search_wa ON master_pelanggan (wa);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_search_hp ON master_pelanggan (hp);"))
                conn.commit()
            print("Database V18 Siap dan Tersinkronisasi dengan models.py!")
        except Exception as e:
            print(f"Startup Database Error: {e}")
            db.session.rollback()

    return app_flask

# --- 8. INTEGRASI CELERY (UNTUK WORKER) ---
# Fungsi ini memastikan Celery memiliki akses ke context Flask (Database, dll)
def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

# Inisialisasi Aplikasi
app = create_app()
# Inisialisasi Objek Celery untuk digunakan oleh Worker [cite: 226]
celery = make_celery(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
