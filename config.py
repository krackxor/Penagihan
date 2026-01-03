import os

class Config:
    """
    Konfigurasi Dasar Aplikasi Sunter Dashboard Pro
    """
    # Secret key untuk sesi Flask (CSRF Protection)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-sunter-secret-key-2024'
    
    # Lokasi Base Directory Project
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Pengaturan Database SQLite
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'sunter.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DATABASE_PATH = os.path.join(BASE_DIR, 'sunter.db')

    # Pengaturan Folder Upload (Sesuai Struktur Project)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    # Folder spesifik untuk foto kunjungan petugas
    KUNJUNGAN_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    
    # Limit Ukuran File Upload (Misal: 16 Megabytes)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Daftar Ekstensi File yang Diizinkan (Sesuai requirements.txt)
    ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv', 'dbf', 'png', 'jpg', 'jpeg'}

    @staticmethod
    def init_app(app):
        """
        Memastikan folder yang diperlukan sudah dibuat saat aplikasi start
        """
        folders = [
            Config.UPLOAD_FOLDER,
            Config.KUNJUNGAN_FOLDER,
            os.path.join(Config.UPLOAD_FOLDER, 'temp')
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder)
                print(f"Directory created: {folder}")

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    # Di produksi, pastikan SECRET_KEY diambil dari environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY')

# Mapping konfigurasi
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
