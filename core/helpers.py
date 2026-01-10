"""
Core Helpers - Sunter Dashboard Pro (V4.5 Sinergi Edition)
Sinergi: API Handler, Data Formatter, & Autopilot Role Redirect

Fungsi: Modul pendukung utama untuk validasi data, standarisasi respons API, 
dan pembersihan data (sanitasi) dari input Excel yang kotor.
"""

import re
from flask import jsonify

class APIResponse:
    """
    [KELAS: STANDARISASI RESPONS API]
    Kegunaan: Menjamin konsistensi struktur data JSON yang dikirim ke Frontend.
    Struktur: { "status": "...", "message": "...", "data": [...] }
    """
    
    @staticmethod
    def success(data=None, message="Success", code=200):
        """
        [FUNGSI: RESPONS SUKSES]
        Mengirim sinyal sukses ke aplikasi petugas/admin.
        Data default berupa list kosong [] untuk mencegah error 'undefined' di JavaScript.
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
        [FUNGSI: RESPONS ERROR]
        Mengirim pesan kegagalan yang aman. 
        Parameter 'details' opsional untuk membantu debugging developer tanpa mengekspos sistem.
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
    [FUNGSI: AUTOPILOT REDIRECT NAVIGASI]
    Kegunaan: Menentukan halaman pertama (Home) saat user berhasil login.
    Logika: 
    - Admin diarahkan ke Dashboard Statistik.
    - Petugas diarahkan langsung ke daftar penagihan (Belum Bayar).
    - Publik/Guest diarahkan ke halaman landing.
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
    [FUNGSI: FORMATTER MATA UANG RUPIAH]
    Kegunaan: Mengubah angka mentah (float/int) menjadi teks Rp yang rapi.
    Logika Sinergi:
    1. Membersihkan karakter non-angka dari input (seperti koma atau Rp dari Excel).
    2. Mengonversi ke float.
    3. Menghasilkan format: Rp 1.500.000 (ribuan dipisahkan titik).
    """
    if nominal is None or str(nominal).strip() == '':
        return "Rp 0"
    
    try:
        if isinstance(nominal, str):
            # Hapus semua karakter kecuali angka, koma, dan titik
            nominal = re.sub(r'[^\d,.]', '', nominal)
            # Standarisasi koma menjadi titik untuk pemrosesan desimal Python
            if ',' in nominal and '.' not in nominal:
                nominal = nominal.replace(',', '.')
            
        val = float(nominal)
        # Format ribuan dengan koma, lalu ganti menjadi titik (Standar Indonesia)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

def clean_nomen(value):
    """
    [FUNGSI: SANITASI ID PELANGGAN (IDPEL)]
    Kegunaan: Memperbaiki IDPEL yang rusak akibat format Excel (Scientific E+).
    PENTING: Tanpa fungsi ini, IDPEL 123456789012 bisa berubah jadi 1.23E+11.
    Logika:
    1. Deteksi notasi ilmiah.
    2. Paksa konversi kembali ke string angka utuh tanpa desimal (.0).
    """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # Menangani format scientific (E+) agar IDPEL tidak terpotong saat di-import
    if 'E+' in val_str.upper():
        try:
            return "{:.0f}".format(float(val_str))
        except (ValueError, TypeError):
            return val_str
            
    # Hapus bagian desimal '.0' yang sering muncul dari pembacaan file Excel
    return val_str.split('.')[0].replace(' ', '')

def clean_phone(phone):
    """
    [FUNGSI: SINERGI WHATSAPP CLEANER]
    Kegunaan: Menyiapkan nomor HP agar siap digunakan untuk API WhatsApp.
    Logika Autopilot:
    - 0812... -> 62812...
    - 812...  -> 62812...
    - Menghapus spasi, strip (-), dan karakter non-angka lainnya.
    """
    if phone is None or str(phone).strip() in ('', '-', '0'):
        return ""
    
    # Hanya ambil karakter angka saja
    cleaned = re.sub(r'\D', '', str(phone))
    
    if not cleaned:
        return ""
    
    # Konversi prefix nomor ke standar Internasional (62) untuk WhatsApp
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    elif cleaned.startswith('8'):
        cleaned = '62' + cleaned
        
    return cleaned

def validate_periode(periode):
    """
    [FUNGSI: VALIDATOR PERIODE SINERGI]
    Kegunaan: Memastikan input periode dari user atau file Excel sesuai standar sistem.
    Format yang diizinkan: MM-YYYY (Contoh: 01-2026).
    """
    pattern = r'^(0[1-9]|1[0-2])-\d{4}$'
    if re.match(pattern, str(periode)):
        return True
    return False
