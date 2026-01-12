"""
Collection API - Sunter Dashboard Pro (V12.7 Strict MB Filter)
Update: 2026-01-12
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Strict UNDUE Filter: Hanya menarik data MB dengan kategori 'UNDUE' (Bulan Bayar == Bulan Rekening).
2. Data Integrity: Menghitung realisasi dari tabel asli (MB & Collection) bukan status_lunas master.
3. Ardebt Exclusion: Pembayaran ekor/basi (kategori 'ARDEBT') otomatis tidak dihitung di dashboard.
4. Rayon Accuracy: Monitoring kumulatif harian dimulai dari saldo awal Undue yang sah.
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime

collection_bp = Blueprint('collection', __name__)

def get_active_period(cursor):
    """Mendeteksi periode aktif terbaru dari database."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Audit: Memisahkan realisasi berdasarkan sumber data dan filter BULAN_REK."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # 1. TOTAL MC (Target Global dari Master Pelanggan)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_mc = cursor.fetchone()[0]

        # 2. BOX UNDUE (Eksklusif: Master Bayar / MB)
        # Hanya data yang berlabel 'UNDUE' (Bulan Bayar == Bulan Rekening) saat upload
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) 
            FROM master_bayar 
            WHERE periode = ? AND kategori = 'UNDUE'
        """, (periode_req,))
        undue_val = cursor.fetchone()[0]

        # 3. BOX CURRENT (Eksklusif: Collection / Lapangan)
        # Menghitung semua realisasi lapangan kategori 'CURRENT' (N di N+1)
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) 
            FROM collection_harian 
            WHERE periode = ? AND kategori = 'CURRENT'
        """, (periode_req,))
        current_val = cursor.fetchone()[0]

        # Konsolidasi Realisasi Sah
        total_realisasi = undue_val + current_val

        return jsonify({
            "status": "success",
            "periode": periode_req,
            "summary": {
                "total_mc": target_mc,
                "realisasi": {
                    "total": total_realisasi,
                    "undue": undue_val,
                    "current": current_val
                },
                "sisa_tagihan": target_mc - total_realisasi,
                "pct": round((total_realisasi / target_mc * 100), 2) if target_mc > 0 else 0
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Monitoring progres harian gabungan Undue (MB) dan Current (Collection)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # Ambil Target per-Rayon
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # Ambil Saldo Awal Undue yang Sah
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_bayar WHERE periode = ? AND kategori = 'UNDUE'", (periode_req,))
        undue_start = cursor.fetchone()[0]

        # Query Pivot Harian (Hanya data Collection kategori CURRENT)
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END) as rp_34,
                SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END) as rp_35,
                SUM(c.nominal) as rp_total
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE p.periode = ? AND c.kategori = 'CURRENT'
            GROUP BY c.pay_dt 
            ORDER BY substr(c.pay_dt,7,4) ASC, substr(c.pay_dt,4,2) ASC, substr(c.pay_dt,1,2) ASC
        """, (periode_req,))
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
                    "pct": round((cum_34 / targets['target_34'] * 100), 2) if targets['target_34'] > 0 else 0
                },
                "r35": {
                    "rp": r['rp_35'], 
                    "pct": round((cum_35 / targets['target_35'] * 100), 2) if targets['target_35'] > 0 else 0
                },
                "total": {
                    "rp_harian": r['rp_total'],
                    "cum_all": cum_all,
                    "pct": round((cum_all / targets['target_total'] * 100), 2) if targets['target_total'] > 0 else 0
                }
            })

        return jsonify({
            "status": "success",
            "data": daily_data,
            "summary": {
                "target": targets['target_total'],
                "pct": daily_data[-1]['total']['pct'] if daily_data else 0,
                "realisasi": daily_data[-1]['total']['cum_all'] if daily_data else undue_start
            }
        })
    finally:
        conn.close()
