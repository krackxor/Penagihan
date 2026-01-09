"""
Core Helpers - Sunter Dashboard Pro
Standardized API Response Handler, Data Formatter & Input Sanitizer

Author: Sunter Team
Updated: 2026-01-09 (Sinergi Level 3)
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
        """
        Mengirim respons sukses yang terstandarisasi.
        :param data: Data hasil query (list atau dict), default ke list kosong jika None
        """
        response = {
            "status": "success",
            "message": message,
            "data": data if data is not None else []
        }
        return jsonify(response), code

    @staticmethod
    def error(message="Error", code=400, details=None):
        """
        Mengirim respons gagal/error yang aman bagi pengguna.
        """
        response = {
            "status": "error",
            "message": message
        }
        
        # Detail hanya ditambahkan jika ada (biasanya untuk debugging backend)
        if details:
            response["details"] = str(details)
            
        return jsonify(response), code

def format_idr(nominal):
    """
    Mengonversi angka atau string angka menjadi format Rupiah Indonesia.
    Mendukung input kotor dari Excel (Rp 50.000,00 -> 50000).
    """
    if nominal is None or str(nominal).strip() == '':
        return "Rp 0"
    
    try:
        # Jika string, bersihkan simbol Rp, spasi, dan titik ribuan
        if isinstance(nominal, str):
            # Hapus semua kecuali angka dan titik/koma desimal
            nominal = re.sub(r'[^\d,.]', '', nominal)
            # Jika menggunakan koma sebagai desimal (Standard Indo), ganti ke titik
            if ',' in nominal and '.' not in nominal:
                nominal = nominal.replace(',', '.')
            
        val = float(nominal)
        # Format ribuan dengan koma, lalu ganti koma menjadi titik (ID Standard)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    Sanitasi ID Pelanggan (Nomen). 
    PENTING: Mencegah Nomen berubah jadi '1.23E+11' saat diupload via Excel.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # Tangani format scientific dari Excel
    if 'E+' in val_str.upper():
        try:
            return "{:.0f}".format(float(val_str))
        except:
            return val_str
            
    # Hapus spasi dan bagian desimal jika ada (.0)
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
    
    if not cleaned:
        return ""
    
    # Jika diawali 0, ganti ke 62
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    
    # Jika diawali 8 (misal 812...), tambahkan 62
    if cleaned.startswith('8'):
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
