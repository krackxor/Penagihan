import socket
import pytz
import re
from datetime import datetime
from flask import jsonify

class APIResponse:
    """
    Class Helper untuk standarisasi respon API di seluruh Sunter Dashboard Pro.
    Sinergi: Menjamin format JSON yang konsisten antara Backend dan Frontend.
    """
    @staticmethod
    def success(data=None, message="Success", code=200):
        return jsonify({
            "status": "success",
            "message": message,
            "data": data
        }), code

    @staticmethod
    def error(message="Error occurred", code=500):
        return jsonify({
            "status": "error",
            "message": message
        }), code

def get_jakarta_time():
    """
    Mengambil waktu saat ini dengan zona Asia/Jakarta secara konsisten.
    Digunakan untuk timestamp laporan kunjungan agar sesuai waktu operasional.
    """
    try:
        tz = pytz.timezone('Asia/Jakarta')
        return datetime.now(tz)
    except Exception:
        return datetime.now()

def get_server_ip():
    """
    Mendapatkan alamat IP lokal server secara robust.
    Sinergi: Penting agar link foto di WhatsApp bisa dibuka oleh Admin/Supervisor.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def format_idr(nominal):
    """
    Mengonversi angka menjadi format Rupiah standar Indonesia.
    Contoh: 1250500 -> Rp 1.250.500
    """
    if nominal is None or nominal == '':
        return "Rp 0"
    
    try:
        if isinstance(nominal, str):
            nominal = re.sub(r'[^\d.]', '', nominal)
            
        val = float(nominal)
        # Gunakan format ribuan dengan koma, lalu tukar koma menjadi titik
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    Membersihkan Nomen/NoTag dari format ilmiah Excel (E+).
    Sinergi: Menjamin 'Pintu Ganda' (Match Data) tidak error karena salah format ID.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # Tangani format Scientific (E+) yang sering muncul dari Excel
    if 'E' in val_str.upper() or '+' in val_str:
        try:
            return "{:.0f}".format(float(val_str))
        except:
            return val_str.split('.')[0]
            
    return val_str.split('.')[0]

def get_role_redirect(role):
    """
    Helper Sinergi: Menentukan halaman tujuan pertama setelah login.
    """
    redirects = {
        'admin': '/admin/dashboard',
        'petugas': '/belum-bayar',
        'publik': '/'
    }
    return redirects.get(role, '/')
