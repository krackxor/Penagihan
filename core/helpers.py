"""
Core Helpers - Sunter Dashboard Pro
Standardized API Response Handler & Data Formatter

Author: Sunter Team
Updated: 2026-01-08
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
        :param message: Pesan sukses kustom
        :param code: HTTP Status Code (default 200)
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
        :param message: Pesan error yang akan muncul di UI
        :param code: HTTP Status Code (400, 404, 500, dll)
        :param details: Detail tambahan untuk debugging (opsional)
        """
        response = {
            "status": "error",
            "message": message
        }
        
        # Detail hanya ditambahkan jika ada (biasanya untuk logging internal)
        if details:
            response["details"] = str(details)
            
        return jsonify(response), code

def format_idr(nominal):
    """
    Mengonversi angka atau string angka menjadi format Rupiah yang rapi.
    Contoh: 50000 -> Rp 50.000
    """
    if nominal is None or str(nominal).strip() == '':
        return "Rp 0"
    
    try:
        # Bersihkan karakter non-numerik jika input berupa string (kecuali titik desimal)
        if isinstance(nominal, str):
            nominal = re.sub(r'[^\d.]', '', nominal)
            
        val = float(nominal)
        # Format ribuan dengan koma, lalu ganti koma menjadi titik (Standar Indonesia)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    Membersihkan ID Pelanggan (Nomen) dari format ilmiah atau desimal Excel.
    Penting untuk konsistensi pencarian data 'Pintu Ganda'.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    # Ambil angka bulatnya saja dan hapus spasi
    cleaned = str(value).strip().split('.')[0]
    
    # Tangani jika Excel mengubah angka panjang menjadi format Scientific (E+)
    if 'E+' in cleaned.upper():
        try:
            cleaned = "{:.0f}".format(float(value))
        except:
            pass
            
    return cleaned
