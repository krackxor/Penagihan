"""
Konfigurasi Global - Sunter Dashboard Pro (V3 - Sinergi Edition)
Perubahan Utama:
1. Unified Database: Satu jalur database sbrs_sinergi.db.
2. Stability Engine: Penambahan Connection Pooling untuk menangani data besar.
3. Expanded File Support: Mendukung format .dbf dan .txt (MC, MB, CID, Ardebt).
4. Logic Integrasi: Folder khusus untuk Master Analisa.
"""

import os

class Config:
    # --- 1. KEAMANAN & IDENTITAS ---
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sunter-pro-sinergi-2026-v3'
    
    # --- 2. MANAJEMEN PATH (DATABASE SINERGI) ---
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Satu jalur database untuk semua modul agar Sinergi (Hapus pemisahan penagihan.db vs database.db)
    DATABASE_NAME = 'sbrs_sinergi.db'
    DATABASE = os.path.join(BASE_DIR, 'database', DATABASE_NAME)
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- 3. STABILITY ENGINE (PENCEGAH DATABASE LOCKED) ---
    # Sangat krusial saat proses Mega-Merge atau integrasi MC + CID yang volumenya besar.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    }
    
    # --- 4. INFRASTRUKTUR FILE (SMART FOLDERS) ---
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    # Folder khusus Master Analisa (MC, CID, MB, Ardebt, Mainbill)
    MASTER_ANALISA_FOLDER = os.path.join(UPLOAD_FOLDER, 'master_analisa')
    TEMP_FOLDER = os.path.join(UPLOAD_FOLDER, 'temp')
    KUNJUNGAN_FOLDER = os.path.join(UPLOAD_FOLDER, 'kunjungan')
    LOG_FOLDER = os.path.join(BASE_DIR, 'logs')
    
    # --- 5. VALIDASI & BATASAN UPLOAD ---
    MAX_CONTENT_LENGTH = 150 * 1024 * 1024  # Ditingkatkan ke 150MB untuk file DBF besar
    
    # Diperbarui agar bisa menerima format file yang Anda kirimkan (dbf dan txt)
    ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv', 'png', 'jpg', 'jpeg', 'dbf', 'txt'}

    # --- 6. WA GATEWAY CONFIG ---
    WA_GATEWAY_URL = os.environ.get('WA_GATEWAY_URL') or ""
    WA_GATEWAY_KEY = os.environ.get('WA_GATEWAY_KEY') or ""

    # --- 7. SMART AUTOPILOT INITIALIZATION ---
    @staticmethod
    def init_app(app):
        """
        Membangun infrastruktur folder secara otomatis.
        Menjamin Sinergi: Tidak ada error 'Path Not Found' saat proses integrasi data.
        """
        # Pastikan folder database ada
        db_dir = os.path.dirname(Config.DATABASE)
        
        required_folders = [
            db_dir,
            Config.UPLOAD_FOLDER,
            Config.MASTER_ANALISA_FOLDER,
            Config.TEMP_FOLDER,
            Config.KUNJUNGAN_FOLDER,
            Config.LOG_FOLDER
        ]
        
        for folder in required_folders:
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                    # Menambahkan file .gitkeep agar folder kosong tetap terdeteksi Git
                    with open(os.path.join(folder, '.gitkeep'), 'w') as f:
                        pass
                    print(f"✅ Sinergi Sync: Folder Ready -> {folder}")
                except Exception as e:
                    print(f"❌ Sinergi Error: Gagal sinkronisasi folder {folder}. Detail: {e}")

        app.config.from_object(Config)

# --- 8. VARIAN KONFIGURASI ---
class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
