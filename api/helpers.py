"""
Core Helpers - Sunter Dashboard Pro
Updated: 2026-01-22 (Ultimate Sync Version)
Sinergi: Standarisasi Data, Server Intelligence, Auto-Fixer Data, & Audit Logging.
"""

import socket
import pytz
import re
import os
from datetime import datetime
from flask import jsonify, request, current_app

class APIResponse:
    """
    Class Helper untuk standarisasi respon API di seluruh Sunter Dashboard Pro.
    Sinergi: Menjamin format JSON yang konsisten antara Backend dan Frontend.
    """
    @staticmethod
    def success(data=None, message="Success", code=200):
        # Mengembalikan respon sukses dengan data minimal list kosong jika None
        return jsonify({
            "status": "success",
            "message": message,
            "data": data if data is not None else []
        }), code

    @staticmethod
    def error(message="Error occurred", code=500, details=None):
        # Mengembalikan respon error dengan detail teknis opsional untuk debugging
        response = {
            "status": "error",
            "message": message
        }
        if details:
            response["details"] = str(details)
        return jsonify(response), code

def get_jakarta_time():
    """
    AUTOPILOT TIMEZONE:
    Mengambil waktu saat ini dengan zona Asia/Jakarta secara konsisten.
    Penting agar timestamp laporan kunjungan tidak berantakan (sinkron dengan server).
    """
    try:
        tz = pytz.timezone('Asia/Jakarta')
        return datetime.now(tz)
    except Exception:
        # Fallback jika library pytz bermasalah
        return datetime.now()

def get_server_ip():
    """
    SERVER INTELLIGENCE:
    Mendapatkan alamat IP lokal server yang aktif digunakan oleh network.
    Sinergi: Digunakan untuk membuat link foto yang bisa diakses supervisor via WhatsApp.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Menggunakan koneksi dummy (tidak benar-benar mengirim data) 
        # untuk mendeteksi IP mana yang digunakan untuk akses internet
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def format_idr(nominal):
    """
    SMART FORMATTER:
    Mengonversi angka menjadi format Rupiah standar Indonesia.
    Menghilangkan angka desimal di belakang koma untuk kerapihan laporan.
    """
    if nominal is None or str(nominal).strip() == '':
        return "Rp 0"
    
    try:
        # Membersihkan karakter non-angka sebelum konversi
        if isinstance(nominal, str):
            nominal = re.sub(r'[^\d,.]', '', nominal)
            if ',' in nominal and '.' not in nominal:
                nominal = nominal.replace(',', '.')
            
        val = float(nominal)
        # Format angka ribuan dengan titik
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    SMART AUTO-FIXER (NOMEN/IDPEL):
    Mencegah putusnya sinergi data (Match Data) akibat format Excel yang rusak.
    Cerdas menangani: format ilmiah (3.5E+08), angka desimal palsu (.0), dan spasi.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # 1. LOGIKA AUTOPILOT: Memperbaiki format ilmiah Excel (1.23E+11 -> 123000...)
    if 'E' in val_str.upper() or '+' in val_str:
        try:
            # Mengubah format ilmiah menjadi angka utuh (teks)
            return "{:.0f}".format(float(val_str))
        except (ValueError, TypeError):
            pass
            
    # 2. Membersihkan angka desimal ".0" yang sering muncul saat upload file Excel melalui Pandas
    if '.' in val_str:
        val_str = val_str.split('.')[0]
        
    # 3. Menghapus semua spasi yang tidak terlihat (liar)
    return re.sub(r'\s+', '', val_str)

def clean_phone(phone):
    """
    SMART WA SANITIZER:
    Menstandarisasi nomor HP untuk keperluan integrasi WhatsApp.
    Otomatis mengubah 0812... menjadi 62812... agar API WA tidak error.
    """
    if phone is None or str(phone).strip() in ('', '-', '0'):
        return ""
    
    # Menghapus karakter non-digit
    cleaned = re.sub(r'\D', '', str(phone))
    
    if not cleaned: return ""
    
    # Logika Autopilot: Koreksi prefix otomatis
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    elif cleaned.startswith('8'):
        cleaned = '62' + cleaned
        
    return cleaned

def get_role_redirect(role):
    """
    HELPER NAVIGASI:
    Menentukan rute redirect setelah login berdasarkan level akses user.
    Sinergi: Petugas langsung ke daftar tagihan, Admin ke pusat kendali.
    """
    redirects = {
        'admin': '/admin/dashboard',
        'petugas': '/belum-bayar',
        'publik': '/'
    }
    return redirects.get(str(role).lower(), '/')

def validate_periode(periode):
    """
    SMART VALIDATOR PERIODE:
    Memastikan format periode selalu MM-YYYY (Contoh: 01-2026).
    Mencegah error query database akibat format tanggal yang salah.
    """
    pattern = r'^(0[1-9]|1[0-2])-\d{4}$'
    if re.match(pattern, str(periode)):
        return True
    return False

def get_base_url():
    """
    AUTO-BASE URL:
    Mendeteksi protokol (http/https) dan domain secara otomatis dari request.
    Penting untuk membangun path gambar statis yang akurat di laporan.
    """
    return request.host_url.rstrip('/')

def log_action(user_id, action, module, details, ip=None):
    """
    AUDIT TRAIL ENGINE:
    Mencatat setiap aktivitas krusial (seperti upload data) ke dalam tabel system_logs.
    Sinergi: Transparansi operasional dan pelacakan error jika terjadi inkonsistensi data.
    """
    from core.database import get_db_connection
    db = get_db_connection()
    try:
        db.execute("""
            INSERT INTO system_logs (user_id, action, module, details, ip_address)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, action, module, details, ip or request.remote_addr))
        db.commit()
    except Exception as e:
        print(f"❌ Log Error: {str(e)}")
    finally:
        db.close()
