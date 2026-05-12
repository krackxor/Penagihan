import os
from flask import Flask, render_template, redirect, url_for
from models import db
from sqlalchemy import inspect, text # Jantung Audit & Sinkronisasi Database

# --- 1. IMPORT BLUEPRINTS ---
from api.monitoring import monitoring_bp
from api.daily import daily_bp  # Import Blueprint Daily Collection
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 
from api.top_500 import top_500_bp # Blueprint Top 500
from api.admin import admin_bp # Blueprint Admin Control (V18)
from api.ocr import ocr_bp # Blueprint Tools OCR
from api.converter import converter_bp # Blueprint Konversi Dokumen
from api.optimizer import optimizer_bp # Blueprint Kompresi Gambar
from api.search import search_bp # Blueprint Global Search

def sync_database_schema(app):
    """
    Fungsi Sinergi Self-Healing V5.18: Sinkronisasi Multi-Tabel Ekstrem (Anti-Crash).
    Menjamin tabel CID, SBRS, MC, MB, Arrdebt, dan MainBill 
    memiliki struktur dan gembok unik yang siap menelan format JSONB.
    """
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        with db.engine.connect() as conn:
            # --- 1. HEALING: master_pelanggan ---
            if 'master_pelanggan' in tables:
                mp_cols = [c['name'] for c in inspector.get_columns('master_pelanggan')]
                if 'raw_data' not in mp_cols:
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
                
                # --- OPTIMASI SEARCH: Tambahkan Index agar Pencarian Global < 100ms ---
                try:
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_search_nomen ON master_pelanggan (nomen);"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_search_nama ON master_pelanggan (nama);"))
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
                    ('status_audit', 'INTEGER DEFAULT 0'), ('raw_data', 'JSONB'),
                    ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'), ('tgl_audit', 'TIMESTAMP'),
                    ('catatan_lapangan', 'TEXT'), ('foto_meter_path', 'VARCHAR(255)'),
                    ('latitude', 'VARCHAR(50)'), ('longitude', 'VARCHAR(50)')
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
                    try:
                        conn.execute(text("ALTER TABLE transaksi_tagihan ADD COLUMN raw_data JSONB"))
                        conn.commit()
                    except Exception: pass
                
                if 'uix_tagihan_nomen_periode' not in tagihan_constraints:
                    try:
                        conn.execute(text("""
                            DELETE FROM transaksi_tagihan a USING transaksi_tagihan b 
                            WHERE a.id < b.id AND a.nomen = b.nomen AND a.periode = b.periode;
                        """))
                        conn.execute(text("ALTER TABLE transaksi_tagihan ADD CONSTRAINT uix_tagihan_nomen_periode UNIQUE (nomen, periode)"))
                        conn.commit()
                    except Exception: pass

            # --- 4. CREATE: data_mb ---
            if 'data_mb' not in tables:
                try:
                    conn.execute(text("""
                        CREATE TABLE data_mb (
                            id SERIAL PRIMARY KEY, nomen VARCHAR(50), periode VARCHAR(10),
                            tgl_bayar VARCHAR(50), nominal FLOAT, denda FLOAT, lks_bayar VARCHAR(100),
                            raw_data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT uix_mb_nomen_periode UNIQUE (nomen, periode)
                        )
                    """))
                    conn.commit()
                except Exception: pass

            # --- 5. CREATE: data_arrdebt ---
            if 'data_arrdebt' not in tables:
                try:
                    conn.execute(text("""
                        CREATE TABLE data_arrdebt (
                            id SERIAL PRIMARY KEY, nomen VARCHAR(50), periode VARCHAR(10),
                            nominal FLOAT, raw_data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT uix_arrdebt_nomen_periode UNIQUE (nomen, periode)
                        )
                    """))
                    conn.commit()
                except Exception: pass

            # --- 6. CREATE: data_mainbill ---
            if 'data_mainbill' not in tables:
                try:
                    conn.execute(text("""
                        CREATE TABLE data_mainbill (
                            id SERIAL PRIMARY KEY, nomen VARCHAR(50), periode VARCHAR(10),
                            total_tagihan FLOAT, konsumsi FLOAT, raw_data JSONB,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT uix_mainbill_nomen_periode UNIQUE (nomen, periode)
                        )
                    """))
                    conn.commit()
                except Exception: pass
            
            conn.commit()

def create_app():
    app_flask = Flask(__name__)

    # --- 2. KONFIGURASI SINERGI & KEAMANAN ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app_flask.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app_flask.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app_flask.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sinergi-pam-jaya-2026')
    
    app_flask.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    app_flask.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 # 1 GB

    # --- 3. INISIALISASI & FOLDER AUTO-CREATE ---
    db.init_app(app_flask)
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app_flask.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads', 'materi'), exist_ok=True)

    # --- 4. REGISTRASI MODUL (BLUEPRINTS) ---
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

    # --- 5. NAVIGASI UTAMA ---
    @app_flask.route('/')
    def index():
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app_flask.route('/upload')
    def upload_page():
        return render_template('upload.html')

    @app_flask.route('/lapor')
    def lapor_page():
        return render_template('lapor.html')

    # --- 6. STARTUP PROTOCOL ---
    with app_flask.app_context():
        try:
            db.create_all()
            sync_database_schema(app_flask)
        except Exception as e:
            print(f"Schema Sync Error: {e}")
            db.session.rollback()

    return app_flask

# --- KUNCI SAKTI GUNICORN ---
app = create_app()

if __name__ == '__main__':
    # Debug mode diaktifkan untuk development, host 0.0.0.0 agar bisa diakses dalam network Docker
    app.run(host='0.0.0.0', port=5000, debug=True)
