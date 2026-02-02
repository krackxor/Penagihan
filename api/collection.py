"""
Collection API - Sunter Dashboard Pro (V12.52 Sync N-1 Logic)
Update: 2026-02-02
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX UNDUE SYNC: Menggunakan logika N-1 (Bulan Sebelumnya) untuk filter 
   bulan_rek, menyamakan logika dengan Dashboard Utama (Efektivitas Penagihan).
   (Contoh: Periode 02-2026 -> Target Rekening 012026).
2. Fix Realisasi Gelembung: Tetap memfilter 'bulan_rek' agar tunggakan lama tidak masuk.
3. Fix Rayon Distribution: Undue dipecah per rayon untuk grafik harian yang akurat.
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime
from dateutil.relativedelta import relativedelta # ✅ Wajib import ini

collection_bp = Blueprint('collection', __name__)

def get_active_period(cursor):
    """Mendeteksi periode dashboard aktif terbaru."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

def get_target_bulan_rek(periode_str):
    """
    Logika N-1: Mengonversi Periode Dashboard ke Bulan Rekening Tagihan.
    Contoh: Periode '02-2026' -> Sasaran Rekening '012026' (Januari).
    Sama persis dengan logika di api/dashboard.py.
    """
    try:
        dt_obj = datetime.strptime(periode_str, '%m-%Y')
        target_dt = dt_obj - relativedelta(months=1)
        return target_dt.strftime('%m%Y')
    except:
        return periode_str.replace('-', '')

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Dashboard: Konsolidasi Realisasi Bank & Lapangan per Periode."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        
        # ✅ FIX: Gunakan Logika N-1 agar Undue Bank terbaca
        bulan_rek_target = get_target_bulan_rek(periode_req)

        # 1. TOTAL TARGET MC
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_mc = cursor.fetchone()[0]

        # 2. BOX UNDUE (BANK)
        # Filter 'bulan_rek' memastikan hanya tagihan bulan N-1 yang masuk (bukan tunggakan)
        cursor.execute("""
            SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
            WHERE mb.periode = ? 
            AND mb.kategori = 'UNDUE'
            AND mb.bulan_rek = ? 
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
    """Tren Kumulatif Harian per Rayon dengan Distribusi Undue."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        
        # ✅ FIX: Gunakan Logika N-1
        bulan_rek_target = get_target_bulan_rek(periode_req)
        
        try:
            p_month, p_year = periode_req.split('-')
        except:
            p_month, p_year = datetime.now().strftime('%m'), datetime.now().strftime('%Y')

        # 1. AMBIL TARGET RAYON
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # 2. SALDO AWAL UNDUE (BANK) PER RAYON
        # Menggunakan bulan_rek_target (N-1) agar data bank masuk
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND p.periode = mb.periode
            WHERE mb.periode = ? 
            AND mb.kategori = 'UNDUE'
            AND mb.bulan_rek = ?
        """, (periode_req, bulan_rek_target))
        
        undue_res = cursor.fetchone()
        undue_34 = undue_res['undue_34']
        undue_35 = undue_res['undue_35']

        # 3. QUERY HARIAN (COLLECTION)
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
        # ✅ Inisialisasi kumulatif dengan Saldo Bank (Undue)
        cum_34 = undue_34
        cum_35 = undue_35
        
        for r in rows:
            if not r['tgl']: continue 
            
            # Strict Date Filter
            tgl_str = str(r['tgl'])
            is_valid_date = False
            if tgl_str.startswith(f"{p_year}-{p_month}"): is_valid_date = True
            elif tgl_str.endswith(f"{p_month}-{p_year}"): is_valid_date = True
            if not is_valid_date: continue 
            
            # Akumulasi berjalan (Undue Awal + Harian Berjalan)
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            cum_all = cum_34 + cum_35 # Total Kumulatif Gabungan
            
            daily_data.append({
                "tgl": r['tgl'],
                "r34": { 
                    "rp": r['rp_34'], 
                    "cum": cum_34, 
                    "pct": round((cum_34 / max(1, targets['target_34']) * 100), 2) 
                },
                "r35": { 
                    "rp": r['rp_35'], 
                    "cum": cum_35, 
                    "pct": round((cum_35 / max(1, targets['target_35']) * 100), 2) 
                },
                "total": { 
                    "rp_harian": r['rp_total'], 
                    "cum_all": cum_all, 
                    "pct": round((cum_all / max(1, targets['target_total']) * 100), 2) 
                }
            })

        return jsonify({"status": "success", "data": daily_data})
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
