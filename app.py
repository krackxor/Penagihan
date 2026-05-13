import os
import importlib
from flask import Flask, redirect, url_for, render_template
from config import Config
from extensions import db, celery

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 1. Inisialisasi Database
    db.init_app(app)

    # 2. Inisialisasi Celery agar Worker bisa mengenali App Context
    celery.conf.update(app.config)
    
    # 3. OTOMATIS REGISTRASI BLUEPRINT (Anti-Repot)
    # Mencari semua file di folder 'api/' dan meregistrasikannya secara otomatis
    api_path = os.path.join(os.path.dirname(__file__), "api")
    if os.path.exists(api_path):
        for filename in os.listdir(api_path):
            if filename.endswith("_routes.py"):
                module_name = filename[:-3] # misal 'importer_routes'
                module = importlib.import_module(f"api.{module_name}")
                # Cari objek blueprint (contoh: importer_bp)
                blueprint_name = module_name.replace("_routes", "_bp")
                if hasattr(module, blueprint_name):
                    app.register_blueprint(getattr(module, blueprint_name))

    # 4. RUTE DASAR
    @app.route('/')
    def index(): return redirect(url_for('daily.index'))
    
    @app.route('/upload')
    def upload_page(): return render_template('upload.html')

    # 5. STARTUP: Buat Folder Storage & Tabel
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['STORAGE_TMP'], exist_ok=True)
        os.makedirs(app.config['STORAGE_ARCHIVE'], exist_ok=True)

    return app

# Ekspos 'app' untuk Gunicorn dan 'celery' untuk Worker
app = create_app()
