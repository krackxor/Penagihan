import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-sunter-secret-key-2024'
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'sunter.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DATABASE_PATH = os.path.join(BASE_DIR, 'sunter.db')

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    KUNJUNGAN_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'kunjungan')
    
    # Perubahan: Set limit ke 10GB (10 * 1024^3 bytes)
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024 * 1024 
    
    ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv', 'dbf', 'png', 'jpg', 'jpeg'}

    @staticmethod
    def init_app(app):
        folders = [Config.UPLOAD_FOLDER, Config.KUNJUNGAN_FOLDER, os.path.join(Config.UPLOAD_FOLDER, 'temp')]
        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder)
