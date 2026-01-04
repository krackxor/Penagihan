import os

class Config:
    # 1. Kunci Rahasia Aplikasi
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-sunter-secret-key-2024'
    
    # 2. Path Dasar Project
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # 3. Konfigurasi Database (PENTING: Gunakan nama 'DATABASE' agar tidak KeyError)
    # Ubah DATABASE_PATH menjadi DATABASE
    DATABASE = os.path.join(BASE_DIR, 'penagihan.db') 
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DATABASE

    # 4. Folder Upload menggunakan absolute path
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    # Sesuaikan dengan serve_kunjungan_photo di app.py
    KUNJUNGAN_FOLDER = os.path.join(UPLOAD_FOLDER, 'kunjungan') 
    
    # 5. Limit Ukuran File & Ekstensi
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
            if not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
                print(f"Directory created: {folder}")
