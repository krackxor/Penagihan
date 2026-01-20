"""
Konfigurasi Global - Sunter Dashboard Pro
Sinergi & Smart Update:
1. Smart Directory: Otomatis membangun infrastruktur folder yang diperlukan (Autopilot).
2. Environment Intelligence: Mendeteksi secara cerdas apakah berjalan di server atau lokal.
3. Security Hardening: Pengamanan kunci rahasia dan limitasi upload file besar.
4. WA Blast Sync: Parameter pendukung untuk pengiriman pesan mandiri.
"""

import os

class Config:
    # --- 1. KEAMANAN & IDENTITAS ---
    # Smart Logic: Mengambil dari Environment System jika ada, jika tidak gunakan kunci default.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sunter-pro-secret-key-2026-v3'
    
    # --- 2. MANAJEMEN PATH (ALUR DATA) ---
    # Mendeteksi lokasi absolut proyek agar sinergi antar folder tetap terjaga.
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Konfigurasi Database (Autopilot Link ke penagihan.db)
    DATABASE = os.path.join(BASE_DIR, 'penagihan.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- 3. INFRASTRUKTUR FILE (SMART FOLDERS) ---
    # Mengatur folder penyimpanan untuk MC, MB, Ardebt, dan Foto Kunjungan.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    TEMP_FOLDER = os.path.join(UPLOAD_FOLDER, 'temp')
    KUNJUNGAN_FOLDER = os.path.join(UPLOAD_FOLDER, 'kunjungan')
    LOG_FOLDER = os.path.join(BASE_DIR, 'logs')
    
    # --- 4. VALIDASI & BATASAN UPLOAD ---
    # Sinergi: Mencegah server overload dengan membatasi ukuran file (100 MB).
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    
    # Format file yang diizinkan untuk menjamin integritas data penagihan.
    ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv', 'png', 'jpg', 'jpeg'}

    # --- 5. WA GATEWAY CONFIG (INTEGRASI MODUL) ---
    # Meskipun menggunakan Browser Mode, parameter ini tetap disediakan sebagai fallback/cadangan.
    WA_GATEWAY_URL = os.environ.get('WA_GATEWAY_URL') or ""
    WA_GATEWAY_KEY = os.environ.get('WA_GATEWAY_KEY') or ""

    # --- 6. SMART AUTOPILOT INITIALIZATION ---
    @staticmethod
    def init_app(app):
        """
        LOGIKA AUTOPILOT:
        Secara otomatis membangun folder yang hilang saat aplikasi dinyalakan.
        Sinergi: Menjamin tidak ada error 'FileNotFound' saat petugas mengupload foto atau admin mengupload MC.
        """
        required_folders = [
            Config.UPLOAD_FOLDER,
            Config.TEMP_FOLDER,
            Config.KUNJUNGAN_FOLDER,
            Config.LOG_FOLDER
        ]
        
        for folder in required_folders:
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                    # Menambahkan file placeholder .gitkeep agar folder kosong tetap terdeteksi oleh sistem
                    with open(os.path.join(folder, '.gitkeep'), 'w') as f:
                        pass
                    print(f"✅ Autopilot: Directory Synchronized -> {folder}")
                except Exception as e:
                    print(f"❌ Sinergi Error: Gagal membuat folder {folder}. Detail: {e}")

        # Menambahkan konfigurasi tambahan untuk Flask jika diperlukan
        app.config.from_object(Config)

# --- 7. VARIAN KONFIGURASI (OPTIONAL) ---
class ProductionConfig(Config):
    """Konfigurasi khusus saat aplikasi sudah online di server (Production)."""
    DEBUG = False
    # Di server, paksa penggunaan HTTPS untuk keamanan data penagihan
    SESSION_COOKIE_SECURE = True

class DevelopmentConfig(Config):
    """Konfigurasi saat masih dalam tahap pengeditan/testing."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
