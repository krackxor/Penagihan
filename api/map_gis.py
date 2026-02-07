"""
GIS Mapping API - Sunter Dashboard Pro (V2.0 Multi-Layer)
File: api/map_gis.py
"""
from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime

map_bp = Blueprint('map', __name__)

def get_active_period(cursor):
    """Mengambil periode transaksi terakhir yang aktif"""
    try:
        cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return row['periode'] if row else datetime.now().strftime('%m-%Y')
    except Exception:
        return datetime.now().strftime('%m-%Y')

@map_bp.route('/data', methods=['GET'])
def get_map_data():
    """
    API Utama untuk GIS Intelligence.
    Mengambil semua data pelanggan dan melakukan klasifikasi kategori 
    untuk pewarnaan marker di peta (Front-End).
    """
    # 1. Security Check
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode = get_active_period(cursor)

        # 2. Query Data: Mengambil SEMUA data periode ini 
        # (Subquery avg_hist untuk perbandingan anomali)
        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.kubik, p.nominal, p.status_lunas,
                p.latitude, p.longitude,
                COALESCE(
                    (SELECT AVG(m.kubik) FROM master_pelanggan m WHERE m.nomen = p.nomen), 
                    p.kubik
                ) as avg_hist
            FROM master_pelanggan p
            WHERE p.periode = ?
        """
        cursor.execute(query, (periode,))
        rows = [dict(row) for row in cursor.fetchall()]
        
        # 3. Logic Processor: Penentuan Kategori & Warna
        processed = []
        for r in rows:
            # Sanitasi Data Angka
            kubik = float(r['kubik']) if r['kubik'] is not None else 0.0
            avg = float(r['avg_hist']) if r['avg_hist'] is not None else 0.0
            lunas = int(r['status_lunas']) if r['status_lunas'] is not None else 0
            
            # Default Category
            kategori = 'NORMAL' 
            
            # --- Deteksi Anomali Teknis ---
            is_ekstrem = False
            is_drop = False
            
            if avg > 0:
                # Logika Ekstrem: Pemakaian > 500 ATAU (Diatas 20m3 DAN Naik 2x Lipat Rata2)
                if kubik > 500 or (kubik > 20 and kubik > (avg * 2)):
                    is_ekstrem = True
                
                # Logika Drop: (0 m3 padahal biasanya > 5) ATAU (Turun dibawah 50% Rata2)
                elif (kubik == 0 and avg > 5) or (kubik > 0 and kubik < (avg * 0.5)):
                    is_drop = True

            # --- Penentuan Prioritas Kategori (Hierarchy) ---
            
            # 1. NOMEN VIP (Kubik > 75) - Prioritas Tertinggi (Marker Biru/Ungu)
            if kubik > 75:
                kategori = 'NOMEN_VIP'
            
            # 2. EKSTREM (Lonjakan Tidak Wajar) - (Marker Merah)
            elif is_ekstrem:
                kategori = 'EKSTREM'
            
            # 3. DROP (Indikasi Meter Macet/Rumah Kosong) - (Marker Kuning)
            elif is_drop:
                kategori = 'DROP'
            
            # 4. BELUM BAYAR (Tunggakan Umum) - (Marker Orange)
            elif lunas == 0:
                kategori = 'BELUM_BAYAR'
            
            # 5. NORMAL (Lunas & Stabil) - (Marker Abu/Hijau)
            else:
                kategori = 'NORMAL'

            # Attach hasil analisa ke data row
            r['kategori'] = kategori
            
            # Format angka untuk tampilan (opsional, biar rapi di JSON)
            r['avg_hist'] = round(avg, 1)
            
            processed.append(r)
        
        return jsonify({"status": "success", "data": processed})

    except Exception as e:
        print(f"Error Map Data: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@map_bp.route('/save-point', methods=['POST'])
def save_point():
    """
    Menyimpan titik koordinat (Latitude/Longitude) hasil drag-and-drop
    atau auto-detect ke database.
    """
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    nomen = request.form.get('nomen')
    lat = request.form.get('lat')
    lng = request.form.get('lng')
    
    if not nomen or not lat or not lng:
        return jsonify({"status": "error", "message": "Data tidak lengkap"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Update koordinat untuk pelanggan tersebut (berlaku global untuk nomen ini)
        # Note: Idealnya master koordinat dipisah tabelnya, tapi untuk simpel 
        # kita update row yang ada atau semua row dengan nomen sama.
        cursor.execute("""
            UPDATE master_pelanggan 
            SET latitude = ?, longitude = ? 
            WHERE nomen = ?
        """, (lat, lng, nomen))
        
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
