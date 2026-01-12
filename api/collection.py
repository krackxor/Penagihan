"""
Collection API - Sunter Dashboard Pro (V10.1 Integrated Rayon Logic)
Update: 2026-01-12
---------------------------------------------------------------------------
Pembaruan:
1. Rayon Split Logic: Mengembalikan perhitungan Rp & % per-Rayon (34 & 35).
2. Advanced Daily Monitor: Sinkronisasi akumulasi harian dengan saldo awal Undue.
3. SQL Standard Sorting: Pengurutan tanggal kronologis (YYYY-MM-DD) via Substr.
4. Smart Pivot: Mengelompokkan data harian secara efisien dalam satu query.
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
    """Summary global untuk widget dashboard atas."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        cursor.execute("""
            SELECT 
                COALESCE(SUM(nominal), 0) as total_rp_mc,
                COALESCE(SUM(CASE WHEN status_lunas = 1 THEN nominal ELSE 0 END), 0) as rp_lunas,
                COALESCE(SUM(CASE WHEN status_lunas = 0 THEN nominal ELSE 0 END), 0) as rp_sisa
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        summary_mc = dict(cursor.fetchone())

        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_bayar WHERE periode = ?", (periode_req,))
        undue_val = cursor.fetchone()[0]
        
        return jsonify({
            "status": "success",
            "periode": periode_req,
            "summary": {
                "target_mc": summary_mc['total_rp_mc'],
                "realisasi": {
                    "total": summary_mc['rp_lunas'],
                    "undue_bank": undue_val,
                    "current_lapangan": summary_mc['rp_lunas'] - undue_val
                },
                "sisa_tagihan": summary_mc['rp_sisa']
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Monitoring harian dengan rincian Rayon 34 & 35 (Sesuai Logika Awal)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # 1. Hitung Target per-Rayon untuk dasar persentase
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # 2. Ambil Saldo Awal Undue (Bank)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_bayar WHERE periode = ?", (periode_req,))
        undue_total = cursor.fetchone()[0]

        # 3. Query Pivot Harian (Pemisahan Rayon 34 & 35)
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END) as rp_34,
                SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END) as rp_35,
                SUM(c.nominal) as rp_total
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE p.periode = ?
            GROUP BY c.pay_dt 
            ORDER BY substr(c.pay_dt,7,4) ASC, substr(c.pay_dt,4,2) ASC, substr(c.pay_dt,1,2) ASC
        """, (periode_req,))
        rows = cursor.fetchall()

        daily_data = []
        cum_34 = 0
        cum_35 = 0
        
        for r in rows:
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            # Kumulatif gabungan (Undue + Hasil Lapangan)
            cum_all = cum_34 + cum_35 + undue_total
            
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
            "periode": periode_req,
            "data": daily_data,
            "summary": {
                "target": targets['target_total'],
                "pct": (cum_all / targets['target_total'] * 100) if rows and targets['target_total'] > 0 else 0,
                "realisasi": cum_all if rows else undue_total
            }
        })
    finally:
        conn.close()
