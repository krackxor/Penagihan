"""
Core Helpers - Sunter Dashboard Pro
Standardized API Response Handler

Author: Sunter Team
"""

from flask import jsonify

class APIResponse:
    """
    Class untuk menstandarisasi format respons JSON di seluruh aplikasi.
    Memastikan Frontend selalu menerima struktur yang sama: {status, message, data}
    """
    
    @staticmethod
    def success(data=None, message="Success", code=200):
        """
        Mengirim respons sukses.
        :param data: Data hasil query (list atau dict)
        :param message: Pesan sukses kustom
        :param code: HTTP Status Code (default 200)
        """
        response = {
            "status": "success",
            "message": message,
            "data": data
        }
        return jsonify(response), code

    @staticmethod
    def error(message="Error", code=400, details=None):
        """
        Mengirim respons gagal/error.
        :param message: Pesan error yang akan muncul di UI
        :param code: HTTP Status Code (400, 404, 500, dll)
        :param details: Detail tambahan untuk debugging (opsional)
        """
        response = {
            "status": "error",
            "message": message
        }
        if details:
            response["details"] = details
            
        return jsonify(response), code

def format_idr(amount):
    """Helper tambahan untuk memformat angka ke Rupiah di sisi server jika diperlukan"""
    try:
        return f"Rp {int(amount):,}".replace(",", ".")
    except:
        return "Rp 0"
