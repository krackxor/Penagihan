import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-sunter-secret-key-2024'
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Path Database Utama
    DATABASE = os.path.join(BASE_DIR, 'penagihan.db')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DATABASE

    # Folder Upload
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    KUNJUNGAN_FOLDER = os.path.join(UPLOAD_FOLDER, 'kunjungan')
    
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024 * 1024  # 10 GB
    ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv', 'dbf', 'png', 'jpg', 'jpeg'}

    @staticmethod
    def init_app(app):
        """Memastikan folder yang diperlukan dibuat saat aplikasi start"""
        folders = [
            app.config['UPLOAD_FOLDER'],
            os.path.join(app.config['UPLOAD_FOLDER'], 'temp'),
            app.config['KUNJUNGAN_FOLDER']
        ]
        for folder in folders:
            os.makedirs(folder, exist_ok=True)
