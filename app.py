import os
from flask import Flask, render_template, redirect, url_for
from models import db
from sqlalchemy import inspect, text # Jantung Audit & Sinkronisasi Database

# --- 1. IMPORT BLUEPRINTS ---
from api.monitoring import monitoring_bp
from api.importer import importer_bp
from api.kunjungan import kunjungan_bp
from api.sbrs import sbrs_bp 
from api.top_500 import top_500_bp # TAMBAHAN: Import Blueprint Top 500

def sync_database_schema(app):
    """
    Fungsi Sinergi Self-Healing V5.13: Sinkronisasi Multi-Tabel.
    Menjamin master_pelanggan dan data_sbrs memiliki struktur fisik yang identik dengan models.py.
    """
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        with db.engine.connect() as conn:
            # --- 1. HEALING: master_pelanggan (Tabel Induk) ---
            # Menjamin kolom induk tersedia agar Auto-Provisioning tidak crash
            if 'master_pelanggan' in tables:
                mp_cols = [c['name'] for c in inspector.get_columns('master_pelanggan')]
                mp_required = [
                    ('rayon', 'VARCHAR(50)'),
                    ('kelurahan', 'VARCHAR(50)'),
                    ('pcez', 'VARCHAR(20)'),
                    ('alamat', 'TEXT'),
                    ('tarif', 'VARCHAR(20)'),
                    ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP') # <-- SOLUSI ERROR created_at
                ]
                for col, dtype in mp_required:
                    if col not in mp_cols:
                        print(f">>> [SINERGI-FIX] Menambah kolom '{col}' ke master_pelanggan...")
                        conn.execute(text(f"ALTER TABLE master_pelanggan ADD COLUMN {col} {dtype}"))

            # --- 2. HEALING: data_sbrs (Tabel Transaksi) ---
            if 'data_sbrs' in tables:
                sbrs_cols = [c['name'] for c in inspector.get_columns('data_sbrs')]
                sbrs_constraints = [c['name'] for c in inspector.get_unique_constraints('data_sbrs')]
                
                sbrs_required = [
                    ('periode', 'VARCHAR(10)'),
                    ('ab', "VARCHAR(50) DEFAULT 'AB Sunter'"),
                    ('kelurahan', 'VARCHAR(100)'),
                    ('pcez', 'VARCHAR(20)'),
                    ('nama', 'VARCHAR(150)'),
                    ('alamat', 'TEXT'),
                    ('rayon', 'VARCHAR(20)'),
                    ('tarif', 'VARCHAR(20)'),
                    ('stand_meter', 'FLOAT DEFAULT 0'),
                    ('bulan_ini', 'FLOAT DEFAULT 0'),
                    ('rata_rata', 'FLOAT DEFAULT 15'),
                    ('kategori_anomali', 'VARCHAR(50)'),
                    ('status_audit', 'INTEGER DEFAULT 0'),
                    ('raw_data', 'JSONB'),
                    ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                    ('tgl_audit', 'TIMESTAMP'),
                    ('catatan_lapangan', 'TEXT'),
                    ('foto_meter_path', 'VARCHAR(255)'),
                    ('latitude', 'VARCHAR(50)'),
                    ('longitude', 'VARCHAR(50)')
                ]
                
                for col, dtype in sbrs_required:
                    if col not in sbrs_cols:
                        print(f">>> [SINERGI-FIX] Menambah kolom '{col}' ke data_sbrs...")
                        conn.execute(text(f"ALTER TABLE data_sbrs ADD COLUMN {col} {dtype}"))
                
                # Pasang Gembok Unik (Wajib untuk Sinkronisasi Upsert)
                if 'uix_sbrs_nomen_periode' not in sbrs_constraints:
                    print(">>> [SINERGI-FIX] Menciptakan Gembok Unik SBRS...")
                    try:
                        conn.execute(text("ALTER TABLE data_sbrs ADD CONSTRAINT uix_sbrs_nomen_periode UNIQUE (nomen, periode)"))
                    except Exception:
                        print("!!! Gagal pasang gembok: Bersihkan data duplikat dulu, Bos!")
            
            conn.commit()

def create_app():
    app = Flask(__name__)

    # --- 2. KONFIGURASI SINERGI & KEAMANAN ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'sinergi-pam-jaya-2026'
    
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 # 1 GB untuk file raksasa

    # --- 3. INISIALISASI & FOLDER AUTO-CREATE ---
    db.init_app(app)
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'uploads', 'materi'), exist_ok=True)

    # --- 4. REGISTRASI MODUL ---
    app.register_blueprint(monitoring_bp, url_prefix='/monitoring')
    app.register_blueprint(importer_bp, url_prefix='/api/import')
    app.register_blueprint(kunjungan_bp, url_prefix='/api/kunjungan')
    app.register_blueprint(sbrs_bp, url_prefix='/sbrs') 
    
    # TAMBAHAN: Daftarkan rute Top 500 yang baru
    app.register_blueprint(top_500_bp, url_prefix='/monitoring/top-500') 

    # --- 5. NAVIGASI UTAMA ---
    @app.route('/')
    def index():
        return redirect(url_for('monitoring.list_tagihan', ab='AB Sunter'))

    @app.route('/upload')
    def upload_page():
        return render_template('upload.html')

    @app.route('/lapor')
    def lapor_page():
        return render_template('lapor.html')

    # --- 6. STARTUP PROTOCOL ---
    with app.app_context():
        db.create_all()
    
    # Jalankan audit kolom & gembok unik secara otomatis di semua tabel
    sync_database_schema(app)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
