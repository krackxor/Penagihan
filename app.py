import os
from flask import Flask, render_template, redirect, url_for
from models import db
from sqlalchemy import inspect, text

# --- 1. IMPORT BLUEPRINTS ---
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 
from api.top_500 import top_500_bp 
from api.admin import admin_bp 

def sync_database_schema(app):
    """
    Fungsi Sinergi Self-Healing V5.18: Sinkronisasi Multi-Tabel Ekstrem (Anti-Crash).
    Fokus pada penambahan kolom JSONB untuk tabel lama tanpa merusak data.
    """
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        with db.engine.connect() as conn:
            # --- 1. HEALING: master_pelanggan ---
            if 'master_pelanggan' in tables:
                mp_cols = [c['name'] for c in inspector.get_columns('master_pelanggan')]
                if 'raw_data' not in mp_cols:
                    print(">>> [SINERGI-FIX] Menambah kolom 'raw_data' ke master_pelanggan...")
                    try:
                        conn.execute(text("ALTER TABLE master_pelanggan ADD COLUMN raw_data JSONB"))
                        conn.commit()
                    except Exception: pass

                mp_required = [
                    ('rayon', 'VARCHAR(50)'), ('kelurahan', 'VARCHAR(100)'),
                    ('pcez', 'VARCHAR(20)'), ('alamat', 'TEXT'),
                    ('tarif', 'VARCHAR(20)'), ('ab', 'VARCHAR(50)'),
                    ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                ]
                for col, dtype in mp_required:
                    if col not in mp_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE master_pelanggan ADD COLUMN {col} {dtype}"))
                            conn.commit()
                        except Exception: pass

            # --- 2. HEALING: data_sbrs ---
            if 'data_sbrs' in tables:
                sbrs_cols = [c['name'] for c in inspector.get_columns('data_sbrs')]
                sbrs_constraints = [c['name'] for c in inspector.get_unique_constraints('data_sbrs')]
                
                sbrs_required = [
                    ('periode', 'VARCHAR(10)'), ('ab', "VARCHAR(50) DEFAULT 'AB Sunter'"),
                    ('kelurahan', 'VARCHAR(100)'), ('pcez', 'VARCHAR(20)'),
                    ('nama', 'VARCHAR(150)'), ('alamat', 'TEXT'),
                    ('rayon', 'VARCHAR(20)'), ('tarif', 'VARCHAR(20)'),
                    ('stand_meter', 'FLOAT DEFAULT 0'), ('bulan_ini', 'FLOAT DEFAULT 0'),
                    ('rata_rata', 'FLOAT DEFAULT 15'), ('kategori_anomali', 'VARCHAR(50)'),
                    ('status_audit', 'INTEGER DEFAULT 0'), ('raw_data', 'JSONB')
                ]
                for col, dtype in sbrs_required:
                    if col not in sbrs_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE data_sbrs ADD COLUMN {col} {dtype}"))
                            conn.commit()
                        except Exception: pass
                
                if 'uix_sbrs_nomen_periode' not in sbrs_constraints:
                    try: 
                        conn.execute(text("ALTER TABLE data_sbrs ADD CONSTRAINT uix_sbrs_nomen_periode UNIQUE (nomen, periode)"))
                        conn.commit()
                    except Exception: pass

            # --- 3. HEALING: transaksi_tagihan ---
            if 'transaksi_tagihan' in tables:
                tagihan_cols = [c['name'] for c in inspector.get_columns('transaksi_tagihan')]
                tagihan_constraints = [c['name'] for c in inspector.get_unique_constraints('transaksi_tagihan')]
                
                if 'raw_data' not in tagihan_cols:
                    print(">>> [SINERGI-FIX] Menambah kolom 'raw_data' ke transaksi_tagihan...")
                    try:
                        conn.execute(text("ALTER TABLE transaksi_tagihan ADD COLUMN raw_data JSONB"))
                        conn.commit()
                    except Exception: pass
                
                if 'uix_tagihan_nomen_periode' not in tagihan_constraints:
                    try:
                        conn.execute(text("ALTER TABLE transaksi_tagihan ADD CONSTRAINT uix_tagihan_nomen_periode UNIQUE (nomen, periode)"))
                        conn.commit()
                    except Exception: pass
            
            conn.commit()

def create_app():
    app_flask = Flask(__name__)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # --- KONFIGURASI ---
    app_flask.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app_flask.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app_flask.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    app_flask.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    app_flask.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 

    db.init_app(app_flask)
    
    # --- AUTO-CREATE FOLDERS ---
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app_flask.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads', 'materi'), exist_ok=True)

    # --- REGISTRASI BLUEPRINTS ---
    app_flask.register_blueprint(monitoring_bp, url_prefix='/monitoring')
    app_flask.register_blueprint(importer_bp, url_prefix='/api/import')
    app_flask.register_blueprint(kunjungan_bp, url_prefix='/api/kunjungan')
    app_flask.register_blueprint(sbrs_bp, url_prefix='/sbrs') 
    app_flask.register_blueprint(top_500_bp, url_prefix='/monitoring/top-500') 
    app_flask.register_blueprint(admin_bp, url_prefix='/admin')

    @app_flask.route('/')
    def index():
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    # --- STARTUP PROTOCOL (DENGAN PROTEKSI RACE CONDITION) ---
    with app_flask.app_context():
        try:
            # Perintah Sakti: sqlalchemy akan membuat tabel baru (MB, Arrdebt, Mainbill)
            # hanya jika belum ada. Jika worker lain sudah membuat, dia akan skip.
            db.create_all()
            sync_database_schema(app_flask)
        except Exception as e:
            # Jika terjadi error unik karena tabrakan worker, abaikan dan lanjut boot
            print(f">>> [DATABASE-INFO] Inisialisasi dilewati atau sudah selesai oleh worker lain.")
            db.session.rollback()

    return app_flask

# =================================================================
# KUNCI GUNICORN: Harus ada di level global agar executable
# =================================================================
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
