"""
Premium Customer API - Sunter Dashboard Pro (V2.3 Anomaly Detection)
File: api/premium.py
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime
import pytz

premium_bp = Blueprint('premium', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def get_active_period(cursor):
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else get_wib_time().strftime('%m-%Y')

@premium_bp.route('/list', methods=['GET'])
def get_premium_customers():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        req_periode = request.args.get('periode')
        if req_periode:
            try:
                parts = req_periode.split('-')
                periode = f"{parts[1]}-{parts[0]}"
            except:
                periode = get_active_period(cursor)
        else:
            periode = get_active_period(cursor)

        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.rayon, p.pcez, 
                p.nominal, p.kubik, p.status_lunas,
                COALESCE(r.petugas, 'UNMAPPED') as petugas_rute,
                (SELECT ROUND(AVG(mp.kubik), 1) FROM master_pelanggan mp WHERE mp.nomen = p.nomen) as avg_kubik_historis
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? AND p.kubik > 75 AND avg_kubik_historis > 75
            ORDER BY p.kubik DESC
        """
        
        cursor.execute(query, (periode,))
        rows = [dict(row) for row in cursor.fetchall()]

        # ✅ LOGIKA DETEKSI ANOMALI (Python Side)
        processed_rows = []
        for r in rows:
            curr = float(r['kubik'])
            avg = float(r['avg_kubik_historis']) if r['avg_kubik_historis'] else 0
            
            r['anomali_status'] = 'NORMAL'
            
            if avg > 0:
                # Jika Melonjak > 50% dari rata-rata (Contoh: Biasa 100, skrg 160)
                if curr > (avg * 1.5):
                    r['anomali_status'] = 'HIGH' 
                # Jika Anjlok > 50% dari rata-rata (Contoh: Biasa 100, skrg 40)
                elif curr < (avg * 0.5):
                    r['anomali_status'] = 'LOW'

            processed_rows.append(r)

        data_34 = [r for r in processed_rows if r['rayon'] == '34']
        data_35 = [r for r in processed_rows if r['rayon'] == '35']

        return jsonify({
            "status": "success",
            "periode": periode,
            "data_34": data_34,
            "data_35": data_35
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# ... (Route /history/<nomen> TETAP SAMA seperti sebelumnya, jangan dihapus) ...
@premium_bp.route('/history/<nomen>', methods=['GET'])
def get_premium_history(nomen):
    if session.get('role') != 'admin':
        return jsonify({"status": "error"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT periode, kubik, nominal, status_lunas 
            FROM master_pelanggan 
            WHERE nomen = ? 
            ORDER BY id DESC LIMIT 12
        """
        cursor.execute(query, (nomen,))
        rows = cursor.fetchall()
        history = []
        for row in reversed(rows): 
            history.append({
                "periode": row['periode'], 
                "kubik": row['kubik'],
                "nominal": row['nominal'],
                "lunas": row['status_lunas']
            })
        return jsonify({"status": "success", "data": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
