"""
Core Helpers - Sunter Dashboard Pro
Updated: 2026-01-09 (Sinergi Level 3)
Standardized Data Sanitizer & Server Intelligence
"""

import socket
import pytz
import re
import os
from datetime import datetime
from flask import jsonify, request

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
            "data": data if data is not None else []
        }), code

    @staticmethod
    def error(message="Error occurred", code=500, details=None):
        response = {
            "status": "error",
            "message": message
        }
        if details:
            response["details"] = str(details)
        return jsonify(response), code

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
        # Mencoba koneksi dummy untuk memicu pencarian rute network asli
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
    if nominal is None or str(nominal).strip() == '':
        return "Rp 0"
    
    try:
        if isinstance(nominal, str):
            # Hapus semua karakter kecuali angka dan titik/koma desimal
            nominal = re.sub(r'[^\d,.]', '', nominal)
            if ',' in nominal and '.' not in nominal: # Handle format Indo (koma desimal)
                nominal = nominal.replace(',', '.')
            
        val = float(nominal)
        # Format ribuan dengan koma, lalu ganti menjadi standar Indonesia (titik)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    Membersihkan Nomen/IDPEL dari format ilmiah Excel (1.23E+11) atau spasi liar.
    Sinergi: Menjamin 'Pintu Ganda' (Match Data) tidak error karena salah format ID.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # Tangani format Scientific (E+) yang sering muncul dari Excel
    if 'E' in val_str.upper() or '+' in val_str:
        try:
            return "{:.0f}".format(float(val_str))
        except (ValueError, TypeError):
            pass
            
    # Hapus spasi dan bagian desimal .0 yang sering muncul otomatis di pandas/excel
    return val_str.split('.')[0].replace(' ', '')

def clean_phone(phone):
    """
    Sanitasi nomor HP untuk Sinergi WA Blast.
    Mengonversi 0812... atau +62812... menjadi 62812...
    """
    if phone is None or str(phone).strip() in ('', '-', '0'):
        return ""
    
    # Ambil angka saja
    cleaned = re.sub(r'\D', '', str(phone))
    
    if not cleaned: return ""
    
    # Jika diawali 0, ganti ke 62
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    
    # Jika diawali 8 (misal 812...), tambahkan 62
    if cleaned.startswith('8'):
        cleaned = '62' + cleaned
        
    return cleaned

def get_role_redirect(role):
    """
    Helper Sinergi: Menentukan rute Dashboard spesifik per Level Akses.
    """
    redirects = {
        'admin': '/admin/dashboard',
        'petugas': '/belum-bayar',
        'publik': '/'
    }
    return redirects.get(role.lower(), '/')

def get_base_url():
    """
    Mendeteksi Base URL secara otomatis (HTTP/HTTPS + IP + Port).
    Penting untuk validasi file path statis di laporan WhatsApp.
    """
    return request.host_url.rstrip('/')
