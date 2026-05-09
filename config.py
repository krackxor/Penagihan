import os

class Config:
    """
    Konfigurasi Utama Aplikasi Sinergi V16.6
    Didesain untuk skalabilitas dan kemudahan deployment (Docker Ready).
    """
    
    # 1. PATH DASAR
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # 2. KEAMANAN
    # Ganti dengan string acak yang kuat jika dipasang di server publik
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sinergi-pam-jaya-secret-2026'
    
    # 3. DATABASE (SQLAlchemy)
    # Database dipusatkan di folder 'instance' sesuai standar Flask modern
    INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(INSTANCE_PATH, 'sinergi.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 4. PENGATURAN UPLOAD
    # Folder pusat untuk semua file yang masuk
    UPLOAD_BASE_PATH = os.path.join(BASE_DIR, 'static', 'uploads')
    
    # Sub-folder khusus agar file tidak berantakan
    UPLOAD_KUNJUNGAN = os.path.join(UPLOAD_BASE_PATH, 'kunjungan')
    UPLOAD_DATA_MASTER = os.path.join(UPLOAD_BASE_PATH, 'materi')
    
    # Batas maksimal ukuran file (16 MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'xlsx', 'xls', 'csv'}

    # 5. DEFAULT OPERASIONAL
    DEFAULT_AB = 'AB Sunter'
    
    @staticmethod
    def init_app(app):
        """Memastikan semua folder yang dibutuhkan sistem tersedia saat startup."""
        folders = [
            Config.INSTANCE_PATH,
            Config.UPLOAD_BASE_PATH,
            Config.UPLOAD_KUNJUNGAN,
            Config.UPLOAD_DATA_MASTER
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                print(f"[*] Folder Dibuat: {folder}")

# Alias untuk mempermudah pemanggilan di app.py
config = Config()
