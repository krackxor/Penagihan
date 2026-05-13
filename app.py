import os
import importlib
from flask import Flask, redirect, url_for, render_template
from config import Config
from extensions import db, celery

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    celery.conf.update(app.config)
    
    # --- PERBAIKAN REGISTRASI BLUEPRINT ---
    api_path = os.path.join(os.path.dirname(__file__), "api")
    if os.path.exists(api_path):
        for filename in os.listdir(api_path):
            if filename.endswith("_routes.py"):
                module_name = filename[:-3]
                module = importlib.import_module(f"api.{module_name}")
                blueprint_name = module_name.replace("_routes", "_bp")
                
                if hasattr(module, blueprint_name):
                    bp = getattr(module, blueprint_name)
                    
                    # Berikan prefix otomatis berdasarkan nama file
                    # importer_routes -> /api/import
                    # daily_routes -> /monitoring/daily
                    if "importer" in module_name:
                        app.register_blueprint(bp, url_prefix='/api/import')
                    elif "daily" in module_name:
                        app.register_blueprint(bp, url_prefix='/monitoring/daily')
                    else:
                        app.register_blueprint(bp)

    @app.route('/')
    def index(): return redirect('/monitoring/daily/')
    
    @app.route('/upload')
    def upload_page(): return render_template('upload.html')

    with app.app_context():
        db.create_all()

    return app

app = create_app()
