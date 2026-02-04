"""
Premium Customer API - Sunter Dashboard Pro (V2.0 Stability Logic)
Update: 2026-02-04
---------------------------------------------------------------------------
Pembaruan:
1. ✅ STABILITY CHECK: Menghitung rata-rata pemakaian historis.
2. ✅ FILTER GANDA: Hanya menampilkan jika (Bulan Ini > 75) DAN (Rata-rata > 75).
   (Menghindari masuknya pelanggan kecil yang tiba-tiba bocor pipa).
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

        # -----------------------------------------------------------
        # QUERY LOGIC: PREMIUM STABIL
        # 1. Ambil data bulan ini.
        # 2. Hitung rata-rata kubik dari seluruh riwayat orang tersebut.
        # -----------------------------------------------------------
        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.rayon, p.pcez, 
                p.nominal, p.kubik, p.status_lunas,
                COALESCE(r.petugas, 'UNMAPPED') as petugas_rute,
                
                -- SUBQUERY: Hitung Rata-rata Kubik Historis
                (
                    SELECT ROUND(AVG(mp.kubik), 1) 
                    FROM master_pelanggan mp 
                    WHERE mp.nomen = p.nomen
                ) as avg_kubik_historis

            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? 
            
            -- SYARAT 1: Bulan ini harus tinggi (Premium)
            AND p.kubik > 75  
            
            -- SYARAT 2: Rata-rata historis juga harus tinggi (Stabil)
            -- Ini memfilter pelanggan kecil yang tiba-tiba melonjak karena bocor
            AND avg_kubik_historis > 75

            ORDER BY p.kubik DESC
        """
        
        cursor.execute(query, (periode,))
        rows = [dict(row) for row in cursor.fetchall()]

        data_34 = [r for r in rows if r['rayon'] == '34']
        data_35 = [r for r in rows if r['rayon'] == '35']

        return jsonify({
            "status": "success",
            "periode": periode,
            "total_count": len(rows),
            "data_34": data_34,
            "data_35": data_35
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
