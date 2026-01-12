"""
Collection API - Sunter Dashboard Pro (V10.0 Clean Report Edition)
Fokus: Monitoring Realisasi Harian & Ringkasan Nominal Global.
Pembaruan:
1. Streamlined Monitoring: Menghapus fitur Leaderboard dan Daftar Petugas.
2. Smart Daily Sync: Akumulasi Current (Lapangan) vs Undue (Kantor).
3. SQL Standard Sorting: Pengurutan tanggal kronologis yang akurat.
4. Ultra-Fast Index: Optimalisasi query berbasis Nomen & Periode.
"""

from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from datetime import datetime

collection_bp = Blueprint('collection', __name__)

def get_active_period(cursor):
    """Mendeteksi periode aktif terbaru dari database."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

# =========================================================================
# 1. RINGKASAN REALISASI GLOBAL (PUSAT KENDALI)
# =========================================================================

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Menampilkan ringkasan nominal MC, Undue, dan Current."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # Ringkasan Nominal Berdasarkan Status Lunas (Otomatis via Trigger)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(nominal), 0) as total_rp_mc,
                COALESCE(SUM(CASE WHEN status_lunas = 1 THEN nominal ELSE 0 END), 0) as rp_lunas,
                COALESCE(SUM(CASE WHEN status_lunas = 0 THEN nominal ELSE 0 END), 0) as rp_sisa
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        summary_mc = dict(cursor.fetchone())

        # Ambil Nominal Undue (Master Bayar/Kantor)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_bayar WHERE periode = ?", (periode_req,))
        undue_val = cursor.fetchone()[0]
        
        # Hitung Current (Lapangan) secara cerdas
        current_val = summary_mc['rp_lunas'] - undue_val

        return jsonify({
            "status": "success",
            "periode": periode_req,
            "summary": {
                "target_mc": summary_mc['total_rp_mc'],
                "realisasi": {
                    "total": summary_mc['rp_lunas'],
                    "undue_bank": undue_val,
                    "current_lapangan": current_val
                },
                "sisa_tagihan": summary_mc['rp_sisa']
            }
        })
    finally:
        conn.close()

# =========================================================================
# 2. MONITORING HARIAN KRONOLOGIS (DAILY MONITOR)
# =========================================================================

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Laporan laju penagihan harian secara kronologis."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # Ambil Target & Saldo Awal Undue
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_total = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_bayar WHERE periode = ?", (periode_req,))
        undue_total = cursor.fetchone()[0]

        # Ekstraksi Laju Harian Collection dengan Sortir SQL
        cursor.execute("""
            SELECT c.pay_dt as tgl, SUM(c.nominal) as rp_hari
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.nomen = p.nomen AND p.periode = c.periode
            WHERE p.periode = ?
            GROUP BY c.pay_dt 
            ORDER BY substr(c.pay_dt,7,4) ASC, substr(c.pay_dt,4,2) ASC, substr(c.pay_dt,1,2) ASC
        """, (periode_req,))
        rows = cursor.fetchall()

        daily_data = []
        cumulative_val = undue_total
        
        for r in rows:
            cumulative_val += r['rp_hari']
            daily_data.append({
                "tgl": r['tgl'],
                "rp_hari": r['rp_hari'],
                "kumulatif": cumulative_val,
                "pct": round((cumulative_val / target_total * 100), 2) if target_total > 0 else 0
            })

        return jsonify({
            "status": "success",
            "periode": periode_req,
            "data": daily_data,
            "summary": {
                "total_target": target_total,
                "realisasi_akhir": cumulative_val
            }
        })
    finally:
        conn.close()
