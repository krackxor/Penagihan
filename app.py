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
    """
    Mengelola koneksi database menggunakan Flask 'g'.
    Menambahkan timeout dan mode WAL untuk mencegah 'Database is Locked'.
    """
    if 'db' not in g:
        # Menambahkan timeout agar request menunggu jika DB sedang sibuk (upload)
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            timeout=30 
        )
        g.db.row_factory = sqlite3.Row
        # Mengaktifkan Mode WAL agar Read & Write bisa berjalan bersamaan
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA synchronous=NORMAL;')
    return g.db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    with app.app_context():
        # Inisialisasi Database (Membuat tabel jika belum ada)
        init_db(app)
        # Inisialisasi Folder (uploads/temp, uploads/kunjungan, dll)
        Config.init_app(app)

    @app.teardown_appcontext
    def close_connection(exception):
        """Menutup koneksi database secara otomatis di akhir setiap request"""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # ==========================================
    # ROUTE UNTUK AKSES FOTO (PENTING UNTUK WA)
    # ==========================================
    @app.route('/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        """Agar link foto di WA bisa diklik dan muncul gambarnya"""
        return send_from_directory(app.config['KUNJUNGAN_FOLDER'], filename)

    # Register Blueprints (Prefix /api)
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(history_bp, url_prefix='/api')
    
    # Register Custom Routes (Mengirimkan fungsi get_db yang baru)
    register_belum_bayar_routes(app, get_db)
    register_pcez_routes(app, get_db)

    # ==========================================
    # ROUTE HALAMAN (FRONTEND)
    # ==========================================
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

    return app

if __name__ == '__main__':
    app = create_app()
    # Debug=True agar perubahan kode langsung terasa tanpa restart manual
    # host='0.0.0.0' agar bisa diakses dari HP melalui IP Address (penting untuk tes WA)
    app.run(host='0.0.0.0', port=5000, debug=True)
