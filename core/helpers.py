"""
Core Helpers - Sunter Dashboard Pro (V6.5 Sinergi Edition)
Sinergi: API Standardizer, Data Sanitizer, GPS Validator, & Role Manager

Fungsi: 
Modul ini bertindak sebagai 'Filter Pusat' untuk menjamin data yang masuk ke database 
dan data yang keluar ke WhatsApp dalam kondisi bersih, valid, dan profesional.
"""

import re
from flask import jsonify

class APIResponse:
    """
    [KELAS: STANDARISASI RESPONS JSON]
    Kegunaan: Menjamin konsistensi struktur data yang dikirim dari Server ke HP Petugas/Dashboard.
    Struktur Baku: { "status": "...", "message": "...", "data": [...] }
    """
    
    @staticmethod
    def success(data=None, message="Success", code=200):
        """
        [FUNGSI: RESPONS SUKSES]
        Mengirim sinyal sukses ke frontend. 
        Data default diset sebagai list kosong [] agar JavaScript tidak crash (undefined).
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
        [FUNGSI: RESPONS GAGAL]
        Mengirim sinyal error yang informatif namun aman. 
        Parameter 'details' sangat berguna saat debugging koneksi database atau GPS.
        """
        response = {
            "status": "error",
            "message": message
        }
        if details:
            response["details"] = str(details)
        return jsonify(response), code

def get_role_redirect(role):
    """
    [FUNGSI: ROLE-BASED NAVIGATION]
    Kegunaan: Menentukan 'Landing Page' otomatis setelah login berhasil.
    Logika: 
    - Admin -> Dashboard Statistik/Monitoring.
    - Petugas -> Daftar Tagihan/Target Harian.
    """
    role_map = {
        'admin': 'admin_dashboard',
        'petugas': 'tagihan_berekor_page', # Diarahkan ke target harian (V6.0)
        'publik': 'index',
        'guest': 'index'
    }
    return role_map.get(str(role).lower(), 'index')

def format_idr(nominal):
    """
    [FUNGSI: FORMATTER RUPIAH]
    Kegunaan: Mengubah angka mentah menjadi format mata uang IDR standar.
    Input: 1500000 -> Output: Rp 1.500.000
    """
    if nominal is None or str(nominal).strip() == '':
        return "Rp 0"
    
    try:
        # Menghilangkan karakter non-angka kecuali pemisah desimal
        if isinstance(nominal, str):
            nominal = re.sub(r'[^\d,.]', '', nominal)
            if ',' in nominal and '.' not in nominal:
                nominal = nominal.replace(',', '.')
        
        val = float(nominal)
        # Menggunakan trick penggantian karakter untuk standar titik (thousand separator) Indonesia
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    [FUNGSI: IDPEL SCIENTIFIC REPAIR]
    Kegunaan: Mencegah IDPEL rusak saat import Excel (Contoh: 1.23E+11).
    Logika: Memaksa konversi float/string ke string angka murni tanpa desimal.
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # Deteksi dan perbaiki notasi ilmiah (E+) agar IDPEL tetap utuh 12 digit
    if 'E+' in val_str.upper():
        try:
            return "{:.0f}".format(float(val_str))
        except:
            return val_str
            
    # Hapus '.0' yang sering muncul jika IDPEL dianggap angka oleh Python
    return val_str.split('.')[0].replace(' ', '')

def clean_phone(phone):
    """
    [FUNGSI: WHATSAPP NUMBER SANITIZER]
    Kegunaan: Standarisasi No HP agar link WhatsApp (wa.me) tidak error.
    Logika: Mengubah prefix 08 atau 8 menjadi 628.
    """
    if phone is None or str(phone).strip() in ('', '-', '0'):
        return ""
    
    # Ambil angka murni saja (menghapus spasi, +, dan strip)
    cleaned = re.sub(r'\D', '', str(phone))
    
    if not cleaned: return ""
    
    # Transformasi prefix ke standar internasional (62)
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    elif cleaned.startswith('8'):
        cleaned = '62' + cleaned
        
    return cleaned

def clean_coordinate(coord):
    """
    [FUNGSI: GPS DATA SANITIZER]
    Kegunaan: Menjamin data Latitude/Longitude aman sebelum masuk database.
    Logika: Hanya mengizinkan angka, titik, dan tanda minus (untuk koordinat negatif).
    """
    if coord is None or str(coord).strip() == '':
        return "0.0"
    
    # Hanya izinkan format angka GPS (Contoh: -6.123456 atau 106.123456)
    cleaned = re.sub(r'[^\d.-]', '', str(coord))
    return cleaned if cleaned else "0.0"

def validate_periode(periode):
    """
    [FUNGSI: PERIOD VALIDATOR]
    Kegunaan: Memastikan format bulan-tahun (MM-YYYY) benar sebelum proses filter data.
    """
    pattern = r'^(0[1-9]|1[0-2])-\d{4}$'
    return bool(re.match(pattern, str(periode)))

def get_gmaps_link(lat, lng):
    """
    [FUNGSI: GMAPS GENERATOR]
    Kegunaan: Membuat link lokasi yang bisa diklik dari WhatsApp pimpinan.
    """
    if not lat or not lng or lat == "0.0":
        return "Lokasi tidak terlacak"
    return f"https://www.google.com/maps?q={lat},{lng}"
