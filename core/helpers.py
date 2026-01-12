"""
Core Helpers - Sunter Dashboard Pro (V6.7 Intelligence Edition)
Sinergi: API Standardizer, Data Sanitizer, GPS Validator, & Role Manager

Update V6.7:
- Auto-Text Shield: Memperkuat clean_nomen untuk menangani format .0 dari Excel secara otomatis.
- Notag Sanitizer: Menambahkan fungsi khusus pembersih Nomor Tagihan.
- GMaps Logic: Mengoptimalkan generator link lokasi.
"""

import re
from flask import jsonify

class APIResponse:
    """
    [KELAS: STANDARISASI RESPONS JSON]
    Kegunaan: Menjamin konsistensi struktur data yang dikirim dari Server ke HP Petugas/Dashboard.
    """
    
    @staticmethod
    def success(data=None, message="Success", code=200):
        response = {
            "status": "success",
            "message": message,
            "data": data if data is not None else []
        }
        return jsonify(response), code

    @staticmethod
    def error(message="Error", code=400, details=None):
        response = {
            "status": "error",
            "message": message
        }
        if details:
            response["details"] = str(details)
        return jsonify(response), code

def get_role_redirect(role):
    """[FUNGSI: ROLE-BASED NAVIGATION]"""
    role_map = {
        'admin': 'admin_dashboard',
        'petugas': 'tagihan_berekor_page',
        'publik': 'index',
        'guest': 'index'
    }
    return role_map.get(str(role).lower(), 'index')

def format_idr(nominal):
    """[FUNGSI: FORMATTER RUPIAH]"""
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
    [FUNGSI: IDPEL AUTO-REPAIR]
    Mencegah IDPEL menjadi 1.23E+11 atau kehilangan nol di depan.
    Juga otomatis menghapus '.0' yang sering muncul dari pembacaan float Excel.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # 1. Perbaiki notasi ilmiah (Contoh: 1.23E+11)
    if 'E+' in val_str.upper():
        try:
            val_str = "{:.0f}".format(float(val_str))
        except:
            pass
            
    # 2. Hapus '.0' di akhir jika terbaca sebagai float (Contoh: 12345.0 -> 12345)
    if val_str.endswith('.0'):
        val_str = val_str[:-2]
        
    # 3. Ambil bagian sebelum titik (jika ada desimal lain) dan bersihkan spasi
    return val_str.split('.')[0].replace(' ', '')

def clean_notag(value):
    """
    [FUNGSI: NOTAGIHAN SANITIZER]
    Sangat penting untuk JOIN antara tabel MC, MB, dan COLLECTION agar dashboard tidak BLANK.
    """
    return clean_nomen(value)

def clean_phone(phone):
    """[FUNGSI: WHATSAPP NUMBER SANITIZER]"""
    if phone is None or str(phone).strip() in ('', '-', '0'):
        return ""
    cleaned = re.sub(r'\D', '', str(phone))
    if not cleaned: return ""
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    elif cleaned.startswith('8'):
        cleaned = '62' + cleaned
    return cleaned

def clean_coordinate(coord):
    """[FUNGSI: GPS DATA SANITIZER]"""
    if coord is None or str(coord).strip() == '':
        return "0.0"
    cleaned = re.sub(r'[^\d.-]', '', str(coord))
    return cleaned if cleaned else "0.0"

def validate_periode(periode):
    """[FUNGSI: PERIOD VALIDATOR]"""
    pattern = r'^(0[1-9]|1[0-2])-\d{4}$'
    return bool(re.match(pattern, str(periode)))

def get_gmaps_link(lat, lng):
    """[FUNGSI: GMAPS GENERATOR]"""
    if not lat or not lng or str(lat) == "0.0":
        return "Lokasi tidak terlacak"
    return f"https://www.google.com/maps?q={lat},{lng}"
