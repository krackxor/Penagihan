import os

class Config:
    """
    Konfigurasi Utama Aplikasi Sinergi V18 (PostgreSQL Optimized)
    Didesain untuk skalabilitas dan stabilitas koneksi data besar.
    """
    
    # 1. PATH DASAR
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # 2. KEAMANAN
    # Mengambil secret key dari environment vps atau default jika tidak ada
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sinergi-pam-jaya-secret-2026'
    
    # 3. DATABASE (SQLAlchemy - PostgreSQL Optimized)
    INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
    
    # AMBIL DATABASE_URL DARI DOCKER-COMPOSE (POSTGRESQL)
    # Jika tidak ada (misal jalan lokal tanpa docker), otomatis balik ke SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f"sqlite:///{os.path.join(INSTANCE_PATH, 'sinergi.db')}"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # FIX COLD START: Memastikan koneksi ke database selalu siap (Warm Connection)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # Cek koneksi sebelum query, mencegah 'Server Closed Connection'
        "pool_recycle": 300,    # Reset koneksi setiap 5 menit agar tidak dianggap idle oleh VPS
        "pool_size": 10,        # Jumlah antrian koneksi
        "max_overflow": 20      # Tambahan koneksi saat upload sangat sibuk
    }

    # 4. PENGATURAN UPLOAD
    UPLOAD_BASE_PATH = os.path.join(BASE_DIR, 'static', 'uploads')
    UPLOAD_KUNJUNGAN = os.path.join(UPLOAD_BASE_PATH, 'kunjungan')
    UPLOAD_DATA_MASTER = os.path.join(UPLOAD_BASE_PATH, 'materi')
    
    # Batas maksimal ukuran file ditingkatkan untuk mendukung Master CID Full
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'xlsx', 'xls', 'csv', 'txt'}

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
                print(f"[*] Folder Siap: {folder}")

# Alias untuk mempermudah pemanggilan di app.py
config = Config()
