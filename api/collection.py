"""
Collection API - Sunter Dashboard Pro (V12.95 - NaN Fix & Sync Frontend)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX NaN: Mengembalikan 'target_mc' sebagai angka tunggal di level utama JSON.
2. ✅ SYNC FRONTEND: Menggunakan key 'rp' dan 'cum' agar tabel monitoring terisi.
3. ✅ DYNAMIC BREK: Otomatis mencari bulan_rek H-1 (02-2026 -> 012026).
4. ✅ NOMINAL: Menyertakan rincian MC 34/35 dan UNDUE 34/35 di objek summary.
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
    """Mengubah periode 'MM-YYYY' menjadi 'MMYYYY' H-1."""
    try:
        dt = datetime.strptime(periode_str, '%m-%Y')
        target_dt = dt - relativedelta(months=1)
        return target_dt.strftime('%m%Y')
    except:
        return "122025"

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Dashboard: Fix NaN dengan mengembalikan target_mc ke format angka."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)
        
        # 1. NOMINAL TARGET MC (Total & Per Rayon)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as mc_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as mc_35,
                COALESCE(SUM(nominal), 0) as mc_total
            FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'
        """, (periode_req,))
        target_res = dict(cursor.fetchone())

        # 2. NOMINAL UNDUE (BANK) - Filter Dinamis
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as u34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as u35,
                COALESCE(SUM(mb.nominal), 0) as u_total
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        undue_res = dict(cursor.fetchone())

        # 3. REALISASI LAPANGAN
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) FROM collection_harian 
            WHERE periode = ? AND kategori = 'CURRENT'
        """, (periode_req,))
        field_val = cursor.fetchone()[0] or 0
        
        total_realisasi = undue_res['u_total'] + field_val
        target_total = target_res['mc_total']

        return jsonify({
            "status": "success",
            "summary": {
                "periode": periode_req,
                "bulan_rek_filter": brek_req,
                "target_mc": target_total,           # Angka tunggal untuk fix NaN
                "mc_34": target_res['mc_34'],        # Rincian tambahan
                "mc_35": target_res['mc_35'],
                "undue_34": undue_res['u34'],
                "undue_35": undue_res['u35'],
                "realisasi": { "total": total_realisasi },
                "sisa_tagihan": max(0, target_total - total_realisasi),
                "pct": round((total_realisasi / max(1, target_total) * 100), 2)
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Tren harian: Sinkronisasi key 'rp' dan 'cum' dengan frontend."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)

        # 1. Target per Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as mc_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as mc_35,
                COALESCE(SUM(nominal), 0) as mc_total
            FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'
        """, (periode_req,))
        target = dict(cursor.fetchone())

        # 2. UNDUE per Rayon (Dinamis)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as u34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as u35
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        undue = dict(cursor.fetchone())

        # 3. Lapangan Harian
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
            
            # Rumus: (Kumulatif Lapangan + Total UNDUE)
            real_34 = cum_f34 + undue['u34']
            real_35 = cum_f35 + undue['u35']
            real_all = real_34 + real_35

            daily_data.append({
                "tgl": tgl_str,
                "r34": {
                    "rp": r['f34'],         # Key 'rp' untuk nominal harian
                    "cum": real_34,        # Key 'cum' untuk kumulatif
                    "pct": round((real_34 / max(1, target['mc_34']) * 100), 2)
                },
                "r35": {
                    "rp": r['f35'],
                    "cum": real_35,
                    "pct": round((real_35 / max(1, target['mc_35']) * 100), 2)
                },
                "total": {
                    "rp_harian": r['f34'] + r['f35'],
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
