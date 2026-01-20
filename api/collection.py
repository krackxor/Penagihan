"""
Collection API - Sunter Dashboard Pro (V12.46 Precision Month Fix)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Fix Month Overlap: Filter harian kini menggunakan MM-YYYY penuh agar data bulan berbeda tidak tercampur.
2. Smart Undue Alignment: Sinkronisasi nominal bank menggunakan filter 'bulan_rek'.
3. N+1 Precision: Memastikan perbandingan target MC vs Realisasi sinkron per periode.
4. Auto-Baseline: Saldo UNDUE terintegrasi otomatis dalam grafik kumulatif harian.
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
        
        # Logika N+1 Smart: Ambil bulan rekening tagihan (Januari menagih Desember)
        dt_obj = datetime.strptime(periode_req, '%m-%Y')
        last_month = dt_obj.replace(day=1) - timedelta(days=1)
        bulan_rek_target = last_month.strftime('%m%Y')

        # 1. TOTAL TARGET MC (Master Customer)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_mc = cursor.fetchone()[0]

        # 2. BOX UNDUE (BANK) - Berdasarkan Bulan Rekening
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
            WHERE bulan_rek = ? AND kategori = 'UNDUE'
            AND nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ?)
        """, (bulan_rek_target, periode_req))
        undue_val = cursor.fetchone()[0]

        # 3. BOX FIELD (PETUGAS) - Realisasi dari kunjungan fisik
        cursor.execute("""
            SELECT COALESCE(SUM(c.nominal), 0) FROM collection_harian c
            WHERE c.periode = ? AND c.kategori = 'CURRENT'
            AND EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = c.nomen AND k.periode = c.periode)
        """, (periode_req,))
        current_petugas = cursor.fetchone()[0]

        # 4. BOX MANDIRI - Data Upload Excel (Tanpa Log Kunjungan)
        cursor.execute("""
            SELECT COALESCE(SUM(c.nominal), 0) FROM collection_harian c
            WHERE c.periode = ? AND c.kategori = 'CURRENT'
            AND NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = c.nomen AND k.periode = c.periode)
        """, (periode_req,))
        current_mandiri = cursor.fetchone()[0]

        total_realisasi = undue_val + current_petugas + current_mandiri

        return jsonify({
            "status": "success",
            "summary": {
                "periode": periode_req,
                "target_rekening": bulan_rek_target,
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
    """Tren Kumulatif Harian per Rayon (34 & 35) + Baseline Bank."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # Logika N+1 untuk Bank Baseline
        dt_obj = datetime.strptime(periode_req, '%m-%Y')
        last_month = dt_obj.replace(day=1) - timedelta(days=1)
        bulan_rek_target = last_month.strftime('%m%Y')

        # Target Detail per Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # Saldo Awal Realisasi Bank (Baseline UNDUE)
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
            WHERE bulan_rek = ? AND kategori = 'UNDUE'
            AND nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ?)
        """, (bulan_rek_target, periode_req))
        undue_start = cursor.fetchone()[0]

        # Query Harian: Filter ketat agar hanya data di MM-YYYY yang sama yang muncul
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END) as rp_34,
                SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END) as rp_35,
                SUM(c.nominal) as rp_total
            FROM collection_harian c
            LEFT JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.periode = ? 
            AND substr(c.pay_dt, 4, 7) = ? 
            GROUP BY c.pay_dt 
            ORDER BY substr(c.pay_dt,7,4) ASC, substr(c.pay_dt,4,2) ASC, substr(c.pay_dt,1,2) ASC
        """, (periode_req, periode_req))
        rows = cursor.fetchall()

        daily_data = []
        cum_34, cum_35 = 0, 0
        
        for r in rows:
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            cum_all = cum_34 + cum_35 + undue_start
            
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
    """Drill-down: Rincian pelanggan per rayon/tanggal."""
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
