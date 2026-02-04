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

        # Ambil data lengkap untuk penentuan logika di Python
        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.kubik, p.nominal, p.status_lunas,
                p.latitude, p.longitude,
                (SELECT ROUND(AVG(m.kubik), 1) FROM master_pelanggan m WHERE m.nomen = p.nomen) as avg_hist
            FROM master_pelanggan p
            WHERE p.periode = ?
            -- Filter: Ambil yang bermasalah ATAU Premium ATAU sudah punya koordinat
            AND (
                p.kubik > 75 OR             -- Premium
                p.status_lunas = 0 OR       -- Belum Bayar
                p.kubik > 500 OR            -- Ekstrem Kasar
                p.kubik = 0 OR              -- Drop Kasar
                (p.latitude IS NOT NULL AND p.latitude != '') -- Yang sudah di-tag
            )
        """
        cursor.execute(query, (periode,))
        rows = [dict(row) for row in cursor.fetchall()]
        
        # LOGIKA PRIORITAS WARNA (Python Logic)
        processed = []
        for r in rows:
            kubik = float(r['kubik'])
            avg = float(r['avg_hist']) if r['avg_hist'] else 1.0
            lunas = int(r['status_lunas'])
            
            kategori = 'NORMAL' # Default
            
            # 1. Cek Anomali Teknis (Paling Atas)
            is_ekstrem = False
            is_drop = False
            
            if avg > 0:
                if kubik > 500 or (kubik > 20 and kubik > (avg * 2)):
                    is_ekstrem = True
                elif (kubik == 0 and avg > 5) or (kubik < (avg * 0.5)):
                    is_drop = True
            
            # 2. Penentuan Kategori Map (Berdasarkan Prioritas Risiko)
            if is_ekstrem:
                kategori = 'EKSTREM'    # MERAH
            elif is_drop:
                kategori = 'DROP'       # KUNING
            elif kubik > 75 and lunas == 0:
                kategori = 'PREMIUM_NUNGGAK' # UNGU (Bahaya Besar)
            elif lunas == 0:
                kategori = 'BELUM_BAYAR'     # ORANGE
            elif kubik > 75:
                kategori = 'PREMIUM'         # BIRU
            else:
                kategori = 'NORMAL'          # ABU-ABU (Jarang muncul karena filter query)

            r['kategori'] = kategori
            processed.append(r)
        
        return jsonify({"status": "success", "data": processed})
    finally:
        conn.close()

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
