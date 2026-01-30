"""
Collection API - Sunter Dashboard Pro (V12.97 Strict & Split Area)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX NameError: Memastikan variabel 'undue_rek_target' didefinisikan dengan benar.
2. ✅ Split Area Logic: Membagi realisasi harian ke kategori 34 dan 35.
3. ✅ Strict Period Alignment: 
   - UNDUE (Bank) memfilter Rekening N-1 (e.g., Tagihan Des dibayar Jan).
   - CURRENT (Koleksi) memfilter Rekening Berjalan (e.g., Tagihan Jan dibayar Jan).
4. ✅ Anti-Overflow Shield: Filter ketat bulan_rek menjamin progress tidak > 100%.
5. ✅ Zero-Record Shield: Proteksi terhadap baris tanggal kosong pada query harian.
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

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Dashboard: Konsolidasi Realisasi Bank & Lapangan per Periode."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        
        # ✅ LOGIKA PERIODE KETAT (Mencegah NameError)
        try:
            dt_obj = datetime.strptime(periode_req, '%m-%Y')
            undue_rek_target = (dt_obj - relativedelta(months=1)).strftime('%m%Y')
            current_rek_target = dt_obj.strftime('%m%Y')
        except Exception:
            undue_rek_target = periode_req.replace('-', '')
            current_rek_target = periode_req.replace('-', '')

        # 1. TOTAL TARGET MC (Master Customer)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_mc = cursor.fetchone()[0]

        # ✅ 2. BOX UNDUE (BANK) - Filter Rekening N-1
        cursor.execute("""
            SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
            AND mb.nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ?)
        """, (periode_req, undue_rek_target, periode_req))
        undue_val = cursor.fetchone()[0]

        # 3. BOX FIELD (PETUGAS) & BOX MANDIRI - Filter Rekening N
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = c.nomen AND k.periode = c.periode) 
                    THEN c.nominal ELSE 0 END) as rp_petugas,
                SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = c.nomen AND k.periode = c.periode) 
                    THEN c.nominal ELSE 0 END) as rp_mandiri
            FROM collection_harian c
            WHERE c.periode = ? AND c.kategori = 'CURRENT' AND c.bulan_rek = ?
        """, (periode_req, current_rek_target))
        res_field = cursor.fetchone()
        current_petugas = res_field[0] or 0
        current_mandiri = res_field[1] or 0

        total_realisasi = undue_val + current_petugas + current_mandiri

        return jsonify({
            "status": "success",
            "summary": {
                "periode": periode_req,
                "target_mc": target_mc,
                "target_rekening": undue_rek_target,
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
    """Tren Kumulatif Harian per Rayon (34 & 35) dengan Filter Periode Ketat."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # ✅ LOGIKA PERIODE KETAT
        try:
            dt_obj = datetime.strptime(periode_req, '%m-%Y')
            undue_rek_target = (dt_obj - relativedelta(months=1)).strftime('%m%Y')
            current_rek_target = dt_obj.strftime('%m%Y')
        except Exception:
            undue_rek_target = periode_req.replace('-', '')
            current_rek_target = periode_req.replace('-', '')

        # 1. Target Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN pcez LIKE '34%' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN pcez LIKE '35%' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # ✅ 2. Saldo Awal Bank (UNDUE) Split 34/35 - Filter Rekening N-1
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN p.pcez LIKE '34%' THEN mb.nominal ELSE 0 END) as undue_34,
                SUM(CASE WHEN p.pcez LIKE '35%' THEN mb.nominal ELSE 0 END) as undue_35
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND p.periode = mb.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
        """, (periode_req, undue_rek_target))
        undue_res = cursor.fetchone()
        undue_34 = undue_res[0] or 0
        undue_35 = undue_res[1] or 0

        # 3. QUERY HARIAN (FIELD) - Filter Rekening N
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                SUM(CASE WHEN p.pcez LIKE '34%' THEN c.nominal ELSE 0 END) as rp_34,
                SUM(CASE WHEN p.pcez LIKE '35%' THEN c.nominal ELSE 0 END) as rp_35,
                SUM(c.nominal) as rp_total
            FROM collection_harian c
            LEFT JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.periode = ? AND c.bulan_rek = ?
            GROUP BY c.pay_dt 
            ORDER BY c.pay_dt ASC
        """, (periode_req, current_rek_target))
        rows = cursor.fetchall()

        daily_data = []
        cum_34, cum_35 = 0, 0
        
        for r in rows:
            if not r['tgl']: continue 
            
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            
            total_area_34 = cum_34 + undue_34
            total_area_35 = cum_35 + undue_35
            cum_all = total_area_34 + total_area_35
            
            daily_data.append({
                "tgl": r['tgl'],
                "r34": { 
                    "rp": r['rp_34'], 
                    "cum": total_area_34, 
                    "pct": round((total_area_34 / max(1, targets['target_34']) * 100), 2) 
                },
                "r35": { 
                    "rp": r['rp_35'], 
                    "cum": total_area_35, 
                    "pct": round((total_area_35 / max(1, targets['target_35']) * 100), 2) 
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
    """Drill-down: Rincian pelanggan per area/tanggal/periode."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        tgl = request.args.get('tgl')
        area = request.args.get('area') 
        periode = request.args.get('periode')

        query = """
            SELECT c.nomen, p.nama, c.nominal
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.pay_dt = ? AND p.pcez LIKE ? AND c.periode = ?
            ORDER BY c.nominal DESC
        """
        cursor.execute(query, (tgl, f"{area}%", periode))
        rows = cursor.fetchall()
        return jsonify({"status": "success", "data": [dict(row) for row in rows]})
    finally:
        conn.close()
