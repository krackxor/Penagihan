"""
GIS Mapping API - Sunter Dashboard Pro (V2.0 Multi-Layer)
File: api/map_gis.py
"""
from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime

map_bp = Blueprint('map', __name__)

def get_active_period(cursor):
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@map_bp.route('/data', methods=['GET'])
def get_map_data():
    if session.get('role') != 'admin':
        return jsonify({"status": "error"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode = get_active_period(cursor)

        # UPDATE 1: Query mengambil SEMUA data tanpa filter aneh-aneh
        # Tujuannya agar semua pelanggan (termasuk yang normal) bisa muncul
        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.kubik, p.nominal, p.status_lunas,
                p.latitude, p.longitude,
                (SELECT ROUND(AVG(m.kubik), 1) FROM master_pelanggan m WHERE m.nomen = p.nomen) as avg_hist
            FROM master_pelanggan p
            WHERE p.periode = ?
        """
        cursor.execute(query, (periode,))
        rows = [dict(row) for row in cursor.fetchall()]
        
        # LOGIKA BARU: Penentuan Kategori & Warna
        processed = []
        for r in rows:
            kubik = float(r['kubik']) if r['kubik'] else 0
            avg = float(r['avg_hist']) if r['avg_hist'] else 1.0
            lunas = int(r['status_lunas'])
            
            kategori = 'NORMAL' # Default
            
            # Cek kondisi teknis dulu
            is_ekstrem = False
            is_drop = False
            
            if avg > 0:
                if kubik > 500 or (kubik > 20 and kubik > (avg * 2)):
                    is_ekstrem = True
                elif (kubik == 0 and avg > 5) or (kubik < (avg * 0.5)):
                    is_drop = True
            
            # URUTAN PRIORITAS BARU (Sesuai Request):
            # 1. NOMEN VIP (Kubik > 75) - Tidak peduli nunggak/lancar, tetap ungu
            if kubik > 75:
                kategori = 'NOMEN_VIP'    # UNGU
            # 2. EKSTREM (Lonjakan)
            elif is_ekstrem:
                kategori = 'EKSTREM'      # MERAH
            # 3. DROP (Turun Drastis)
            elif is_drop:
                kategori = 'DROP'         # KUNING
            # 4. BELUM BAYAR (Umum / < 75 kubik)
            elif lunas == 0:
                kategori = 'BELUM_BAYAR'  # ORANGE
            # 5. Sisanya NORMAL
            else:
                kategori = 'NORMAL'       # ABU-ABU

            r['kategori'] = kategori
            processed.append(r)
        
        return jsonify({"status": "success", "data": processed})
    finally:
        conn.close()

# Fungsi Simpan Titik (TIDAK DIHAPUS)
@map_bp.route('/save-point', methods=['POST'])
def save_point():
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 403
    
    nomen = request.form.get('nomen')
    lat = request.form.get('lat')
    lng = request.form.get('lng')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE master_pelanggan SET latitude=?, longitude=? WHERE nomen=?", (lat, lng, nomen))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
