import os

class Config:
    """
    Konfigurasi Global Aplikasi Penagihan Sunter Pro.
    """
    # Keamanan aplikasi
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sunter-pro-secret-key-2026'
    
    # Path Dasar Proyek
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Konfigurasi Database (Menggunakan penagihan.db sesuai kesepakatan)
    DATABASE = os.path.join(BASE_DIR, 'penagihan.db')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DATABASE
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Konfigurasi Upload File
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    TEMP_FOLDER = os.path.join(UPLOAD_FOLDER, 'temp')
    KUNJUNGAN_FOLDER = os.path.join(UPLOAD_FOLDER, 'kunjungan')
    
    # Limit Ukuran File (100 MB)
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    
    # Format File yang Diizinkan
    ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv', 'png', 'jpg', 'jpeg'}

    @staticmethod
    def init_app(app):
        """
        Memastikan struktur folder tersedia saat aplikasi pertama kali dijalankan.
        Mencegah error 'Folder not found' saat upload.
        """
        folders = [
            Config.UPLOAD_FOLDER,
            Config.TEMP_FOLDER,
            Config.KUNJUNGAN_FOLDER
        ]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                print(f"Directory created: {folder}")
