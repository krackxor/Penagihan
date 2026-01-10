"""
WA Gateway Module - Sunter Dashboard Pro (V3 Smart Autopilot)
Sinergi & Smart Update:
1. Auto-Format: Konversi nomor otomatis ke standar 62 (Autopilot).
2. URL Encoder: Proteksi karakter khusus pesan WhatsApp.
3. Bulk Sync: Mendukung update massal nomor HP dari Excel (Sinergi Database).
"""

import urllib.parse
import pandas as pd
from flask import Blueprint, request, jsonify
from core.database import get_db_connection

# Inisialisasi Blueprint untuk rute API WA
wa_bp = Blueprint('wa_gateway', __name__)

def generate_wa_link(no_hp, pesan):
    """
    FUNGSI GENERATOR LINK (GRATIS):
    Membangun URL API WhatsApp yang valid secara otomatis.
    """
    if not no_hp:
        return "#"
        
    # Membersihkan nomor HP dari karakter sampah (spasi, strip, petik)
    clean_no = "".join(filter(str.isdigit, str(no_hp)))
    
    # Autopilot: Konversi otomatis nomor lokal ke format internasional 62
    if clean_no.startswith('0'):
        clean_no = '62' + clean_no[1:]
    elif clean_no.startswith('8'):
        clean_no = '62' + clean_no
        
    # Sinergi: Encode pesan agar aman untuk URL (menangani enter/baris baru)
    encoded_msg = urllib.parse.quote(pesan)
    
    return f"https://api.whatsapp.com/send?phone={clean_no}&text={encoded_msg}"

@wa_bp.route('/sync-contacts', methods=['POST'])
def sync_contacts_autopilot():
    """
    FUNGSI SINKRONISASI MASSAL (AUTOPILOT):
    Menerima file Excel dengan kolom 'NOMEN' & 'NO_HP'.
    Sistem akan memasangkan nomor HP tersebut ke database pelanggan yang belum bayar.
    """
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File Excel tidak ditemukan"}), 400
        
    file = request.files['file']
    try:
        # Membaca file Excel secara cerdas
        df = pd.read_excel(file)
        
        # Standarisasi nama kolom agar tidak sensitif huruf besar/kecil
        df.columns = [c.upper().strip() for c in df.columns]
        
        if 'NOMEN' not in df.columns or 'NO_HP' not in df.columns:
            return jsonify({"status": "error", "message": "Excel harus memiliki kolom 'NOMEN' dan 'NO_HP'"}), 400
            
        db = get_db_connection()
        count_updated = 0
        
        # Looping data Excel untuk sinkronisasi ke Database
        for _, row in df.iterrows():
            nomen = str(row['NOMEN']).strip()
            raw_phone = str(row['NO_HP']).strip()
            
            # Autopilot Cleaning: Pastikan hanya angka yang masuk
            clean_phone = "".join(filter(str.isdigit, raw_phone))
            
            if clean_phone and nomen:
                # Sinergi Update: Simpan nomor HP ke profil nasabah secara permanen
                db.execute(
                    "UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", 
                    (clean_phone, nomen)
                )
                count_updated += 1
                
        db.commit()
        db.close()
        
        return jsonify({
            "status": "success", 
            "message": f"Sinergi Berhasil! {count_updated} kontak pelanggan telah diperbarui."
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal memproses file: {str(e)}"}), 500

@wa_bp.route('/update-single', methods=['POST'])
def update_single_contact():
    """
    FUNGSI UPDATE MANUAL:
    Digunakan saat petugas input nomor HP satu per satu di lapangan.
    """
    data = request.json
    nomen = data.get('nomen')
    phone = data.get('phone')
    
    if not nomen or not phone:
        return jsonify({"status": "error", "message": "Data tidak lengkap"}), 400
        
    db = get_db_connection()
    try:
        db.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (phone, nomen))
        db.commit()
        return jsonify({"status": "success", "message": "Kontak diperbarui secara permanen."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()
