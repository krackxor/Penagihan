"""
Core Helpers - Sunter Dashboard Pro (V12.60 Intelligence)
Sinergi: API Standardizer, Data Sanitizer, GPS Validator, & Audit Logger

Update V12.60:
- Log Action Integration: Menambahkan mesin pencatat jejak digital Admin & Petugas.
- Auto-Text Shield: Proteksi IDPEL (Nomen) dari kerusakan format ilmiah Excel (E+).
- Notag Sanitizer: Menjamin join data antar periode tetap sinkron (MC, MB, Coll).
"""

import re
import sqlite3
from flask import jsonify, current_app

class APIResponse:
    """ [STANDARISASI RESPONS JSON] """
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

# ==========================================
# 1. MODUL AUDIT & LOGGING (FIX: ImportError)
# ==========================================

def log_action(user_id, action, module, details="", ip=""):
    """
    [FUNGSI: SYSTEM LOG WRITER]
    Mencatat setiap aktivitas administratif (Upload, Update, Delete) ke tabel system_logs.
    """
    from core.database import get_db_connection  # Local import to prevent circular dependency
    db = None
    try:
        db = get_db_connection()
        db.execute("""
            INSERT INTO system_logs (user_id, action, module, details, ip_address)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, action, module, details, ip))
        db.commit()
    except Exception as e:
        print(f"❌ Failed to write system log: {str(e)}")
    finally:
        if db:
            db.close()

# ==========================================
# 2. MODUL DATA SANITIZER (EXCEL REPAIR)
# ==========================================

def clean_nomen(value):
    """ [FUNGSI: IDPEL AUTO-REPAIR] - Menghapus .0 dan notasi ilmiah (E+) """
    if value is None or str(value).strip().upper() in ('NAN', 'NULL', ''):
        return ""
    
    val_str = str(value).strip()
    
    # Perbaiki notasi ilmiah (Contoh: 1.23E+11)
    if 'E+' in val_str.upper():
        try:
            val_str = "{:.0f}".format(float(val_str))
        except:
            pass
            
    # Hapus '.0' di akhir (Contoh: 12345.0 -> 12345)
    if val_str.endswith('.0'):
        val_str = val_str[:-2]
        
    return val_str.split('.')[0].replace(' ', '')

def clean_notag(value):
    """ [FUNGSI: NOTAGIHAN SANITIZER] - Join Guard """
    return clean_nomen(value)

def clean_coordinate(coord):
    """ [FUNGSI: GPS DATA SANITIZER] """
    if coord is None or str(coord).strip() == '':
        return "0.0"
    cleaned = re.sub(r'[^\d.-]', '', str(coord))
    return cleaned if cleaned else "0.0"

def clean_phone(phone):
    """ [FUNGSI: WHATSAPP NUMBER SANITIZER] """
    if phone is None or str(phone).strip() in ('', '-', '0'):
        return ""
    cleaned = re.sub(r'\D', '', str(phone))
    if not cleaned: return ""
    if cleaned.startswith('0'):
        cleaned = '62' + cleaned[1:]
    elif cleaned.startswith('8'):
        cleaned = '62' + cleaned
    return cleaned

# ==========================================
# 3. MODUL FORMATTER & NAVIGATION
# ==========================================

def get_role_redirect(role):
    """ [FUNGSI: ROLE-BASED NAVIGATION] """
    role_map = {
        'admin': '/admin/dashboard',
        'petugas': '/tunggakan-berekor',
        'guest': '/'
    }
    return role_map.get(str(role).lower(), '/')

def format_idr(nominal):
    """ [FUNGSI: FORMATTER RUPIAH] """
    try:
        val = float(nominal) if nominal else 0
        return f"Rp {val:,.0f}".replace(',', '.')
    except:
        return "Rp 0"

def get_gmaps_link(lat, lng):
    """ [FUNGSI: GMAPS GENERATOR] """
    if not lat or not lng or str(lat) == "0.0":
        return "Lokasi tidak terlacak"
    return f"https://www.google.com/maps?q={lat},{lng}"
