import socket
import pytz
import re
from datetime import datetime

def get_jakarta_time():
    """
    Mengambil waktu saat ini dengan zona Asia/Jakarta secara konsisten.
    Digunakan untuk timestamp laporan kunjungan agar sesuai dengan waktu operasional lapangan.
    """
    try:
        tz = pytz.timezone('Asia/Jakarta')
        return datetime.now(tz)
    except Exception:
        # Fallback jika pytz bermasalah
        return datetime.now()

def get_server_ip():
    """
    Mendapatkan alamat IP lokal server secara robust.
    Digunakan untuk menyusun URL foto bukti kunjungan agar link di WhatsApp tetap valid.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Mencoba koneksi keluar untuk mendapatkan IP lokal yang aktif di jaringan
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        # Fallback jika tidak ada koneksi internet/jaringan
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def format_idr(nominal):
    """
    Mengonversi angka menjadi format mata uang Rupiah (IDR) yang standar.
    Contoh: 50000 -> Rp 50.000
    """
    if nominal is None or nominal == '':
        return "Rp 0"
    
    try:
        # Pastikan input adalah angka bersih (hapus karakter non-angka jika perlu)
        if isinstance(nominal, str):
            nominal = re.sub(r'[^\d.]', '', nominal)
            
        val = float(nominal)
        # Format ribuan dengan koma, lalu ubah koma menjadi titik sesuai standar Indonesia
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    Membersihkan data Nomen atau Nomor Tagihan dari format ilmiah (E+) atau desimal (.0).
    Sangat krusial untuk menjaga konsistensi 'Pintu Ganda' saat join antar tabel.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    # Hapus spasi dan ambil bagian sebelum titik (mencegah format desimal dari Excel)
    cleaned = str(value).strip().split('.')[0]
    
    # Mencegah ID pelanggan berubah menjadi format ilmiah (misal: 1.23E+10)
    if 'E+' in cleaned.upper():
        try:
            cleaned = "{:.0f}".format(float(value))
        except:
            pass
            
    return cleaned
