"""
Collection API - Sunter Dashboard Pro (V13.10 - Excel Serial Date & Strict Logic)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ SERIAL DATE CONVERTER: Mengonversi angka Excel (46023.0) menjadi (01/01/2026).
2. ✅ STRICT DATE FILTER: Membuang data Desember yang menyelinap di file Januari.
3. ✅ DYNAMIC BREK: Filter bulan_rek H-1 tetap otomatis (02-2026 -> 012026).
4. ✅ SORTING FIX: Menjamin baris pertama dimulai dari Tanggal 1 Januari 2026.
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

collection_bp = Blueprint('collection', __name__)

def excel_date_to_str(serial_val):
    """Mengonversi serial number Excel (misal 46023.0) ke string DD/MM/YYYY."""
    try:
        # Jika nilai adalah angka (float/int), konversi dari serial Excel
        if isinstance(serial_val, (float, int)) or (isinstance(serial_val, str) and serial_val.replace('.','',1).isdigit()):
            serial = float(serial_val)
            dt = datetime(1899, 12, 30) + timedelta(days=serial)
            return dt.strftime('%d/%m/%Y')
        # Jika sudah string, kembalikan apa adanya setelah dibersihkan
        return str(serial_val).strip().replace('-', '/')
    except:
        return str(serial_val)

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
    """Summary Dashboard: Fix NaN dan Sinkronisasi Total Realisasi."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)
        month_ref, year_ref = periode_req.split('-')
        
        # 1. NOMINAL TARGET MC
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as mc_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as mc_35,
                COALESCE(SUM(nominal), 0) as mc_total
            FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'
        """, (periode_req,))
        target_res = dict(cursor.fetchone())

        # 2. NOMINAL UNDUE (BANK)
        cursor.execute("""
            SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        undue_val = cursor.fetchone()[0] or 0

        # 3. REALISASI LAPANGAN (Dengan Filter Tanggal Ketat)
        cursor.execute("SELECT pay_dt, nominal FROM collection_harian WHERE periode = ?", (periode_req,))
        field_rows = cursor.fetchall()
        
        total_field = 0
        pattern = f"/{month_ref}/{year_ref}"
        for r in field_rows:
            tgl_fix = excel_date_to_str(r['pay_dt'])
            if pattern in tgl_fix:
                total_field += (r['nominal'] or 0)
        
        total_realisasi = undue_val + total_field
        target_total = target_res['mc_total']

        return jsonify({
            "status": "success",
            "summary": {
                "periode": periode_req,
                "target_mc": target_total,
                "mc_34": target_res['mc_34'],
                "mc_35": target_res['mc_35'],
                "realisasi": { "total": total_realisasi },
                "sisa_tagihan": max(0, target_total - total_realisasi),
                "pct": round((total_realisasi / max(1, target_total) * 100), 2)
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Tren harian dengan konversi Serial Excel dan Sorting Kronologis."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)
        month_p, year_p = periode_req.split('-')

        # 1. Target & Undue per Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon='34' THEN nominal ELSE 0 END), 0) as mc34,
                COALESCE(SUM(CASE WHEN rayon='35' THEN nominal ELSE 0 END), 0) as mc35,
                COALESCE(SUM(nominal), 0) as mc_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        target = dict(cursor.fetchone())

        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon='34' THEN mb.nominal ELSE 0 END), 0) as u34,
                COALESCE(SUM(CASE WHEN p.rayon='35' THEN mb.nominal ELSE 0 END), 0) as u35
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        undue = dict(cursor.fetchone())

        # 2. Lapangan Harian
        cursor.execute("""
            SELECT c.pay_dt,
                SUM(CASE WHEN p.rayon='34' THEN c.nominal ELSE 0 END) as f34,
                SUM(CASE WHEN p.rayon='35' THEN c.nominal ELSE 0 END) as f35
            FROM collection_harian c
            JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.periode = ?
            GROUP BY c.pay_dt
        """, (periode_req,))
        rows = cursor.fetchall()

        # Proses Konversi & Filter di level Python
        processed_list = []
        pattern = f"/{month_p}/{year_p}"
        for r in rows:
            tgl_fix = excel_date_to_str(r['pay_dt'])
            if pattern in tgl_fix:
                processed_list.append({
                    "tgl": tgl_fix,
                    "f34": r['f34'],
                    "f35": r['f35'],
                    "sort_key": datetime.strptime(tgl_fix, '%d/%m/%Y')
                })

        # Urutkan secara kronologis (Bukan berdasarkan string)
        processed_list.sort(key=lambda x: x['sort_key'])

        daily_data = []
        cum34, cum35 = 0, 0
        for p in processed_list:
            cum34 += p['f34']
            cum35 += p['f35']
            
            real34 = cum34 + undue['u34']
            real35 = cum35 + undue['u35']
            real_all = real34 + real35

            daily_data.append({
                "tgl": p['tgl'],
                "r34": {
                    "rp": p['f34'], "cum": real34,
                    "pct": round((real34 / max(1, target['mc34']) * 100), 2)
                },
                "r35": {
                    "rp": p['f35'], "cum": real35,
                    "pct": round((real35 / max(1, target['mc35']) * 100), 2)
                },
                "total": {
                    "rp_harian": p['f34'] + p['f35'],
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
