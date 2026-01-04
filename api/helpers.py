import socket
import pytz
from datetime import datetime

def get_jakarta_time():
    """
    Mengambil waktu saat ini dengan zona Asia/Jakarta.
    Berguna untuk timestamp kunjungan dan log aktivitas.
    """
    tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(tz)

def get_server_ip():
    """
    Mendapatkan alamat IP lokal server.
    Digunakan untuk menyusun URL bukti foto agar bisa diakses melalui link WhatsApp.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Menghubungkan ke DNS Google untuk mendeteksi IP keluar
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = 'localhost'
    finally:
        s.close()
    return ip

def format_idr(nominal):
    """
    Mengonversi angka menjadi format mata uang Rupiah (IDR).
    Contoh: 50000 -> Rp 50.000
    """
    try:
        val = float(nominal)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    Membersihkan data nomen (NOTAGIHAN/NOTAG) dari spasi atau format angka ilmiah.
    """
    if value is None:
        return ""
    return str(value).split('.')[0].strip()
