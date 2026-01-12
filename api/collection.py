"""
Collection API - Sunter Dashboard Pro (V12.15 Data Recovery Mode)
Update: 2026-01-13
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Data Recovery: Menambahkan kategori 'HISTORY' ke dalam semua query realisasi.
2. Dashboard Fix: Memastikan Box UNDUE tidak Rp 0 jika data terdeteksi sebagai History.
3. Daily Resilience: Tren harian kini mencakup seluruh kategori bayar (UNDUE+HISTORY).
4. Atomic Total: Konsistensi penjumlahan kumulatif antara box summary dan chart harian.
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime

collection_bp = Blueprint('collection', __name__)

def get_active_period(cursor):
    """Mendeteksi periode aktif terbaru dari database untuk default view."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Audit: Konsolidasi Realisasi Bank & Lapangan (Termasuk Recovery Data History)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # 1. TOTAL TARGET (MC)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_mc = cursor.fetchone()[0]

        # 2. BOX UNDUE (BANK) - Menarik UNDUE, HISTORY, dan ARDEBT agar angka muncul
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) 
            FROM master_bayar 
            WHERE periode = ? AND kategori IN ('UNDUE', 'HISTORY', 'ARDEBT')
        """, (periode_req,))
        undue_val = cursor.fetchone()[0]

        # 3. BOX FIELD (PETUGAS) - Realisasi yang tervalidasi kunjungan
        cursor.execute("""
            SELECT COALESCE(SUM(c.nominal), 0) 
            FROM collection_harian c
            WHERE c.periode = ? AND c.kategori IN ('CURRENT', 'HISTORY', 'ARDEBT')
            AND EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = c.nomen AND k.periode = c.periode
            )
        """, (periode_req,))
        current_petugas = cursor.fetchone()[0]

        # 4. BOX MANDIRI - Realisasi tanpa record kunjungan
        cursor.execute("""
            SELECT COALESCE(SUM(c.nominal), 0) 
            FROM collection_harian c
            WHERE c.periode = ? AND c.kategori IN ('CURRENT', 'HISTORY', 'ARDEBT')
            AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = c.nomen AND k.periode = c.periode
            )
        """, (periode_req,))
        current_mandiri = cursor.fetchone()[0]

        total_realisasi = undue_val + current_petugas + current_mandiri

        return jsonify({
            "status": "success",
            "periode": periode_req,
            "summary": {
                "target_mc": target_mc,
                "realisasi": {
                    "total": total_realisasi, 
                    "undue": undue_val,
                    "current_petugas": current_petugas,
                    "current_mandiri": current_mandiri
                },
                "sisa_tagihan": max(0, target_mc - total_realisasi),
                "pct": round((total_realisasi / (target_mc or 1) * 100), 2)
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Tren Kumulatif Harian: Mendukung pemulihan data dari kategori HISTORY."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # Saldo Awal Bank (Mencakup data recovery)
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) 
            FROM master_bayar 
            WHERE periode = ? AND kategori IN ('UNDUE', 'HISTORY', 'ARDEBT')
        """, (periode_req,))
        undue_start = cursor.fetchone()[0]

        # Query Harian (Inklusi HISTORY)
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END) as rp_34,
                SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END) as rp_35,
                SUM(c.nominal) as rp_total
            FROM collection_harian c
            LEFT JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE c.periode = ? AND c.kategori IN ('CURRENT', 'HISTORY', 'ARDEBT')
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
                    "pct": round((cum_34 / (targets['target_34'] or 1) * 100), 2)
                },
                "r35": {
                    "rp": r['rp_35'], 
                    "pct": round((cum_35 / (targets['target_35'] or 1) * 100), 2)
                },
                "total": {
                    "rp_harian": r['rp_total'],
                    "cum_all": cum_all,
                    "pct": round((cum_all / (targets['target_total'] or 1) * 100), 2)
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
