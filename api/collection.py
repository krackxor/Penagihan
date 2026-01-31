"""
Collection API - Sunter Dashboard Pro (V12.80 - Dynamic Rayon Nominal Fix)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ DYNAMIC BREK: Otomatis mencari bulan_rek H-1 dari periode dashboard (02-2026 -> 012026).
2. ✅ NOMINAL VISIBILITY: Menampilkan angka asli MC 34, MC 35, UNDUE 34, dan UNDUE 35.
3. ✅ RUMUS: (Kumulatif Lapangan + Total UNDUE sesuai filter BREK) / Target MC.
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime
from dateutil.relativedelta import relativedelta

collection_bp = Blueprint('collection', __name__)

def get_active_period(cursor):
    """Mendeteksi periode dashboard aktif terbaru."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

def get_dynamic_bulan_rek(periode_str):
    """
    Mengubah format periode 'MM-YYYY' menjadi 'MMYYYY' satu bulan sebelumnya.
    Contoh: '02-2026' -> '012026'
    """
    try:
        dt = datetime.strptime(periode_str, '%m-%Y')
        target_dt = dt - relativedelta(months=1)
        return target_dt.strftime('%m%Y')
    except:
        return "122025" # Fallback

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Dashboard dengan rincian nominal transparan per Rayon."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)
        
        # 1. NOMINAL TARGET MC PER RAYON
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as mc_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as mc_35,
                COALESCE(SUM(nominal), 0) as mc_total
            FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'
        """, (periode_req,))
        target = dict(cursor.fetchone())

        # 2. NOMINAL UNDUE (BANK) PER RAYON (Filter Dinamis Bulan Rekening)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35,
                COALESCE(SUM(mb.nominal), 0) as undue_total
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        undue = dict(cursor.fetchone())

        # 3. REALISASI LAPANGAN
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END) as f34,
                SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END) as f35
            FROM collection_harian c
            JOIN master_pelanggan p ON c.nomen = p.nomen AND c.periode = p.periode
            WHERE c.periode = ? AND c.kategori = 'CURRENT'
        """, (periode_req,))
        field = dict(cursor.fetchone())
        
        total_realisasi_all = undue['undue_total'] + (field['f34'] or 0) + (field['f35'] or 0)

        return jsonify({
            "status": "success",
            "summary": {
                "periode": periode_req,
                "bulan_rek_filter": brek_req,
                "target_nominal": target, # mc_34, mc_35
                "undue_nominal": undue,   # undue_34, undue_35
                "realisasi_total": total_realisasi_all,
                "pct_total": round((total_realisasi_all / max(1, target['mc_total']) * 100), 2)
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Tren harian dengan rincian nominal dinamis per Rayon."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)

        # 1. Target MC per Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as mc_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as mc_35,
                COALESCE(SUM(nominal), 0) as mc_total
            FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'
        """, (periode_req,))
        target = dict(cursor.fetchone())

        # 2. Total UNDUE per Rayon (Filter Dinamis)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        undue_total = dict(cursor.fetchone())

        # 3. Realisasi Lapangan Harian
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END) as f34,
                SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END) as f35
            FROM collection_harian c
            JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.periode = ?
            GROUP BY c.pay_dt ORDER BY c.pay_dt ASC
        """, (periode_req,))
        rows = cursor.fetchall()

        daily_data = []
        cum_f34, cum_f35 = 0, 0
        
        for r in rows:
            tgl_str = str(r['tgl'])
            if len(tgl_str) < 8: continue 
            
            cum_f34 += r['f34']
            cum_f35 += r['f35']
            
            # Rumus Dinamis per Rayon
            real_34 = cum_f34 + undue_total['undue_34']
            real_35 = cum_f35 + undue_total['undue_35']
            real_all = real_34 + real_35

            daily_data.append({
                "tgl": tgl_str,
                "nominal_ref": {
                    "mc_34": target['mc_34'],
                    "mc_35": target['mc_35'],
                    "undue_34": undue_total['undue_34'],
                    "undue_35": undue_total['undue_35']
                },
                "r34": {
                    "rp_lapangan": r['f34'],
                    "cum_total": real_34,
                    "pct": round((real_34 / max(1, target['mc_34']) * 100), 2)
                },
                "r35": {
                    "rp_lapangan": r['f35'],
                    "cum_total": real_35,
                    "pct": round((real_35 / max(1, target['mc_35']) * 100), 2)
                },
                "total": {
                    "cum_all": real_all,
                    "pct": round((real_all / max(1, target['mc_total']) * 100), 2)
                }
            })

        return jsonify({"status": "success", "data": daily_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@collection_bp.route('/detail-transaksi', methods=['GET'])
def detail_transaksi():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        tgl = request.args.get('tgl')
        rayon = request.args.get('rayon')
        periode = request.args.get('periode')

        query = """
            SELECT c.nomen, p.nama, c.nominal
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.pay_dt = ? AND p.rayon = ? AND c.periode = ?
            ORDER BY c.nominal DESC
        """
        cursor.execute(query, (tgl, rayon, periode))
        rows = cursor.fetchall()
        return jsonify({"status": "success", "data": [dict(row) for row in rows]})
    finally:
        conn.close()
