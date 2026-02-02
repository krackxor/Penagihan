"""
Collection API - Sunter Dashboard Pro (V12.50 Fix Realisasi Gelembung)
Update: 2026-02-02
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX REALISASI 171%: Menambahkan filter 'bulan_rek' pada query UNDUE.
   Hanya menghitung pembayaran yang BULAN REKENINGNYA sama dengan PERIODE DASHBOARD.
   (Pembayaran tunggakan otomatis terabaikan).
2. Strict Date Filter: Memastikan tanggal harian sesuai bulan periode (Sudah ada).
3. Zero-Record Shield: Mengabaikan baris tanggal kosong (Sudah ada).
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime, timedelta

collection_bp = Blueprint('collection', __name__)

def get_active_period(cursor):
    """Mendeteksi periode dashboard aktif terbaru (Hasil Shift N+1)."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Dashboard: Konsolidasi Realisasi Bank & Lapangan per Periode."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        
        # ✅ Konversi Periode (misal: 02-2026) menjadi Bulan Rekening (022026)
        # Ini kunci untuk membedakan pembayaran current vs tunggakan
        bulan_rek_target = periode_req.replace('-', '') 

        # 1. TOTAL TARGET MC (Master Customer)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_mc = cursor.fetchone()[0]

        # 2. BOX UNDUE (BANK)
        # ✅ UPDATE: Ditambahkan filter 'AND mb.bulan_rek = ?'
        cursor.execute("""
            SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
            WHERE mb.periode = ? 
            AND mb.kategori = 'UNDUE'
            AND mb.bulan_rek = ?  -- Filter ini membuang data tunggakan
            AND mb.nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ?)
        """, (periode_req, bulan_rek_target, periode_req))
        undue_val = cursor.fetchone()[0]

        # 3. BOX FIELD (PETUGAS) & BOX MANDIRI
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = c.nomen AND k.periode = c.periode) 
                    THEN c.nominal ELSE 0 END) as rp_petugas,
                SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = c.nomen AND k.periode = c.periode) 
                    THEN c.nominal ELSE 0 END) as rp_mandiri
            FROM collection_harian c
            WHERE c.periode = ? AND c.kategori = 'CURRENT'
        """, (periode_req,))
        res_field = cursor.fetchone()
        current_petugas = res_field[0] or 0
        current_mandiri = res_field[1] or 0

        total_realisasi = undue_val + current_petugas + current_mandiri

        return jsonify({
            "status": "success",
            "summary": {
                "periode": periode_req,
                "target_mc": target_mc,
                "realisasi": {
                    "total": total_realisasi, 
                    "undue": undue_val,
                    "current_petugas": current_petugas,
                    "current_mandiri": current_mandiri
                },
                "sisa_tagihan": max(0, target_mc - total_realisasi),
                "pct": round((total_realisasi / max(1, target_mc) * 100), 2)
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Tren Kumulatif Harian per Rayon dengan Filter Tanggal Ketat."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        
        # ✅ Konversi Periode untuk Filter Saldo Awal
        bulan_rek_target = periode_req.replace('-', '') 

        # Parsing target bulan dan tahun dari request (Format: MM-YYYY)
        try:
            p_month, p_year = periode_req.split('-')
        except:
            p_month, p_year = datetime.now().strftime('%m'), datetime.now().strftime('%Y')

        # Ambil Target Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # Saldo Awal Bank (UNDUE)
        # ✅ UPDATE: Ditambahkan filter 'AND bulan_rek = ?'
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
            WHERE periode = ? 
            AND kategori = 'UNDUE'
            AND bulan_rek = ? -- Filter ini membuang data tunggakan
            AND nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ?)
        """, (periode_req, bulan_rek_target, periode_req))
        undue_start = cursor.fetchone()[0]

        # Query Data Harian (Ambil semua di periode ini, nanti difilter di Python)
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END) as rp_34,
                SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END) as rp_35,
                SUM(c.nominal) as rp_total
            FROM collection_harian c
            LEFT JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.periode = ?
            GROUP BY c.pay_dt 
            ORDER BY c.pay_dt ASC
        """, (periode_req,))
        rows = cursor.fetchall()

        daily_data = []
        cum_34, cum_35 = 0, 0
        
        for r in rows:
            if not r['tgl']: continue # Skip tanggal kosong
            
            # --- ✅ LOGIKA FILTER KETAT (STRICT FILTER) ---
            tgl_str = str(r['tgl'])
            is_valid_date = False
            
            if tgl_str.startswith(f"{p_year}-{p_month}"):
                is_valid_date = True
            elif tgl_str.endswith(f"{p_month}-{p_year}"):
                is_valid_date = True
            
            if not is_valid_date:
                continue # ⛔ SKIP data bocor
            # ----------------------------------------------
            
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            cum_all = cum_34 + cum_35 + undue_start
            
            daily_data.append({
                "tgl": r['tgl'],
                "r34": { "rp": r['rp_34'], "cum": cum_34, "pct": round((cum_34 / max(1, targets['target_34']) * 100), 2) },
                "r35": { "rp": r['rp_35'], "cum": cum_35, "pct": round((cum_35 / max(1, targets['target_35']) * 100), 2) },
                "total": { "rp_harian": r['rp_total'], "cum_all": cum_all, "pct": round((cum_all / max(1, targets['target_total']) * 100), 2) }
            })

        return jsonify({"status": "success", "data": daily_data})
    finally:
        conn.close()

@collection_bp.route('/detail-transaksi', methods=['GET'])
def detail_transaksi():
    """Drill-down: Rincian pelanggan per rayon/tanggal/periode."""
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
