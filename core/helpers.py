"""
Core Helpers - Sunter Dashboard Pro
Sinergi: API Handler, Data Formatter, & Autopilot Role Redirect

Author: Sunter Team
Updated: 2026-01-10 (Sinergi Level 3 - Fix ImportError)
"""

import re
from flask import jsonify

class APIResponse:
    """
    Class untuk menstandarisasi format respons JSON di seluruh aplikasi.
    Memastikan Frontend selalu menerima struktur yang sama: {status, message, data}
    """
    
    @staticmethod
    def success(data=None, message="Success", code=200):
        """Mengirim respons sukses yang terstandarisasi."""
        response = {
            "status": "success",
            "message": message,
            "data": data if data is not None else []
        }
        return jsonify(response), code

    @staticmethod
    def error(message="Error", code=400, details=None):
        """Mengirim respons gagal/error yang aman bagi pengguna."""
        response = {
            "status": "error",
            "message": message
        }
        if details:
            response["details"] = str(details)
        return jsonify(response), code

def get_role_redirect(role):
    """
    FUNGSI AUTOPILOT REDIRECT (FIX):
    Menentukan rute navigasi otomatis berdasarkan peran pengguna.
    PENTING: Nama fungsi ini harus SAMA dengan yang di-import di app.py.
    """
    role_map = {
        'admin': 'admin_dashboard',
        'petugas': 'belum_bayar_page',
        'publik': 'index',
        'guest': 'index'
    }
    # Mengambil rute berdasarkan role, default ke 'index' jika tidak ditemukan
    return role_map.get(str(role).lower(), 'index')

def format_idr(nominal):
    """
    Mengonversi angka atau string angka menjadi format Rupiah Indonesia.
    Mendukung input kotor dari Excel (Rp 50.000,00 -> 50000).
    """
    if nominal is None or str(nominal).strip() == '':
        return "Rp 0"
    
    try:
        if isinstance(nominal, str):
            nominal = re.sub(r'[^\d,.]', '', nominal)
            if ',' in nominal and '.' not in nominal:
                nominal = nominal.replace(',', '.')
            
        val = float(nominal)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    Sanitasi ID Pelanggan (Nomen) - AUTOPILOT CLEANING: 
    Mencegah IDPEL berubah jadi format ilmiah (1.23E+11) saat diproses Python.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # Tangani format scientific (E+) yang sering merusak data IDPEL
    if 'E+' in val_str.upper():
        try:
            return "{:.0f}".format(float(val_str))
        except (ValueError, TypeError):
            return val_str
            
    # Hapus spasi dan bagian desimal jika ada (.0 dari Excel)
    return val_str.split('.')[0].replace(' ', '')

def clean_phone(phone):
    """
    Sanitasi nomor HP untuk Sinergi WA Blast Gratis.
    Konversi otomatis: 08x atau 8x -> 628x.
    """
    if phone is None or str(phone).strip() in ('', '-', '0'):
        return ""
    
    # Ambil angka saja (Filter Karakter Sampah)
    cleaned = re.sub(r'\D', '', str(phone))
    
    if not cleaned:
        return ""
    
    # Autopilot: Ubah prefix nomor ke standar Internasional (62)
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    elif cleaned.startswith('8'):
        cleaned = '62' + cleaned
        
    return cleaned

def validate_periode(periode):
    """
    Memastikan format periode konsisten (MM-YYYY).
    """
    pattern = r'^(0[1-9]|1[0-2])-\d{4}$'
    if re.match(pattern, str(periode)):
        return True
    return False
