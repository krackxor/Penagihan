"""
Collection API - Sunter Dashboard Pro (V13.20 - Ultimate Serial Date Fix)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ SERIAL TO DATE: Mengubah angka 46023.0 (dari file Anda) menjadi 01/01/2026.
2. ✅ STRICT MONTH VALIDATION: Memvalidasi objek tanggal agar benar-benar berada 
   di bulan & tahun yang dipilih (membuang data sisa bulan lalu).
3. ✅ KRONOLOGIS SORTING: Menjamin baris pertama tabel dimulai dari Tanggal 1.
4. ✅ STABLE TARGET: Fix NaN dengan memastikan target_mc dikirim sebagai angka murni.
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

collection_bp = Blueprint('collection', __name__)

def excel_date_to_dt(serial_val):
    """Konversi serial number Excel atau string ke objek datetime Python."""
    try:
        # Cek jika data berupa angka serial (seperti 46023.0)
        if isinstance(serial_val, (float, int)) or (isinstance(serial_val, str) and serial_val.replace('.','',1).isdigit()):
            serial = float(serial_val)
            # Excel offset: 30 Des 1899
            return datetime(1899, 12, 30) + timedelta(days=serial)
        
        # Jika data berupa string tanggal (seperti 01/01/2026 atau 01-01-2026)
        clean_str = str(serial_val).strip().replace('-', '/')
        return datetime.strptime(clean_str, '%d/%m/%Y')
    except:
        return None

def get_active_period(cursor):
    """Mendeteksi periode dashboard aktif terbaru."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

def get_dynamic_bulan_rek(periode_str):
    """Mencari bulan rekening H-1 (Bulan sebelumnya)."""
    try:
        dt = datetime.strptime(periode_str, '%m-%Y')
        target_dt = dt - relativedelta(months=1)
        return target_dt.strftime('%m%Y')
    except:
        return "122025"

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Dashboard: Menghitung realisasi dengan validasi tanggal objek."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)
        target_m, target_y = map(int, periode_req.split('-'))
        
        # 1. Target Nominal
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_total = cursor.fetchone()[0] or 0

        # 2. Realisasi Bank (UNDUE)
        cursor.execute("""
            SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        undue_val = cursor.fetchone()[0] or 0

        # 3. Realisasi Lapangan (Validasi Objek Tanggal)
        cursor.execute("SELECT pay_dt, nominal FROM collection_harian WHERE periode = ?", (periode_req,))
        field_rows = cursor.fetchall()
        
        total_field = 0
        for r in field_rows:
            dt = excel_date_to_dt(r['pay_dt'])
            # Hanya hitung jika bulan dan tahun cocok dengan periode dashboard
            if dt and dt.month == target_m and dt.year == target_y:
                total_field += (r['nominal'] or 0)
        
        total_realisasi = undue_val + total_field

        return jsonify({
            "status": "success",
            "summary": {
                "periode": periode_req,
                "target_mc": target_total,
                "realisasi": { "total": total_realisasi },
                "sisa_tagihan": max(0, target_total - total_realisasi),
                "pct": round((total_realisasi / max(1, target_total) * 100), 2)
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Tren harian: Konversi serial, filter bulan ketat, dan urutan kronologis."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        brek_req = get_dynamic_bulan_rek(periode_req)
        target_m, target_y = map(int, periode_req.split('-'))

        # 1. Target & Undue Nominal per Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon='34' THEN nominal ELSE 0 END), 0) as mc34,
                COALESCE(SUM(CASE WHEN rayon='35' THEN nominal ELSE 0 END), 0) as mc35
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        res_target = cursor.fetchone()
        target = {"mc34": res_target[0], "mc35": res_target[1], "total": res_target[0] + res_target[1]}

        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon='34' THEN mb.nominal ELSE 0 END), 0) as u34,
                COALESCE(SUM(CASE WHEN p.rayon='35' THEN mb.nominal ELSE 0 END), 0) as u35
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.bulan_rek = ?
        """, (periode_req, brek_req))
        res_undue = cursor.fetchone()
        undue = {"u34": res_undue[0], "u35": res_undue[1]}

        # 2. Data Lapangan
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

        # Konversi, Filter, dan Sorting
        temp_list = []
        for r in rows:
            dt = excel_date_to_dt(r['pay_dt'])
            if dt and dt.month == target_m and dt.year == target_y:
                temp_list.append({
                    "dt_obj": dt,
                    "tgl_str": dt.strftime('%d/%m/%Y'),
                    "f34": r['f34'],
                    "f35": r['f35']
                })
        
        # Urutkan berdasarkan waktu (Kronologis)
        temp_list.sort(key=lambda x: x['dt_obj'])

        daily_data = []
        cum34, cum35 = 0, 0
        for item in temp_list:
            cum34 += item['f34']
            cum35 += item['f35']
            
            real34 = cum34 + undue['u34']
            real35 = cum35 + undue['u35']
            real_all = real34 + real35

            daily_data.append({
                "tgl": item['tgl_str'],
                "r34": {
                    "rp": item['f34'], "cum": real34,
                    "pct": round((real34 / max(1, target['mc34']) * 100), 2)
                },
                "r35": {
                    "rp": item['f35'], "cum": real35,
                    "pct": round((real35 / max(1, target['mc35']) * 100), 2)
                },
                "total": {
                    "rp_harian": item['f34'] + item['f35'],
                    "cum_all": real_all,
                    "pct": round((real_all / max(1, target['total']) * 100), 2)
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
