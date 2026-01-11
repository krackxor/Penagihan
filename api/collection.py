"""
Collection API - Sunter Dashboard Pro (V8.2 Sinergi Intelligence)
Sinergi & Smart Update:
1. Pusat Kendali ⚡: Monitoring Nomen & Nominal (MC, Undue, Current, Belum Bayar).
2. Daily Monitor: Grafik laju progres harian kumulatif (Realisasi vs Target).
3. Leaderboard: Peringkat produktivitas petugas berdasarkan % Realisasi Nomen.
4. Ultra-Fast Join: Menghapus CAST() untuk akses instan via Database INDEX.
"""

import os
import sqlite3
from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime

collection_bp = Blueprint('collection', __name__)

def get_latest_period(cursor):
    """FUNGSI AUTOPILOT: Mendapatkan periode terakhir yang tersedia di database."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

# =========================================================================
# 1. PUSAT KENDALI AREA SERVICE (INTELLIGENCE & ANALYTICS)
# =========================================================================

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """
    ENDPOINT UTAMA: Memantau Jumlah Nomen & Nominal MC.
    Breakdown by Rayon, PCEZ, dan Petugas untuk Grafik Dinamis.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_latest_period(cursor)

        # A. RINGKASAN DATA (NOMEN VS NOMINAL)
        cursor.execute("""
            SELECT 
                COUNT(nomen) as total_nomen,
                SUM(nominal) as total_rp_mc,
                SUM(CASE WHEN status_lunas = 1 THEN 1 ELSE 0 END) as qty_bayar,
                SUM(CASE WHEN status_lunas = 0 THEN 1 ELSE 0 END) as qty_belum,
                SUM(CASE WHEN status_lunas = 1 THEN nominal ELSE 0 END) as rp_lunas,
                SUM(CASE WHEN status_lunas = 0 THEN nominal ELSE 0 END) as rp_sisa
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        summary = dict(cursor.fetchone())

        # B. ANALISIS REALISASI (UNDUE VS CURRENT)
        # Undue: Dari Master Bayar | Current: Dari Collection Harian
        cursor.execute("SELECT SUM(nominal) FROM master_bayar WHERE periode = ?", (periode_req,))
        undue_val = cursor.fetchone()[0] or 0
        current_val = (summary['rp_lunas'] or 0) - undue_val

        # C. DATA BY AREA & PETUGAS (UNTUK GRAFIK DINAMIS)
        cursor.execute("""
            SELECT p.rayon, p.pcez, r.petugas,
                COUNT(p.nomen) as qty,
                SUM(p.nominal) as target,
                SUM(CASE WHEN p.status_lunas = 1 THEN p.nominal ELSE 0 END) as realisasi
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            GROUP BY p.pcez, r.petugas
        """, (periode_req,))
        analytics = [dict(row) for row in cursor.fetchall()]

        # D. PERINGKAT PRODUKTIVITAS (LEADERBOARD)
        cursor.execute("""
            SELECT r.petugas, 
                COUNT(p.nomen) as target_nomen,
                SUM(CASE WHEN p.status_lunas = 1 THEN 1 ELSE 0 END) as lunas_nomen,
                ROUND(SUM(CASE WHEN p.status_lunas = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(p.nomen), 2) as pct
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            GROUP BY r.petugas ORDER BY pct DESC
        """, (periode_req,))
        leaderboard = [dict(row) for row in cursor.fetchall()]

        # E. LOG AKTIVITAS TERAKHIR
        cursor.execute("""
            SELECT petugas_name, nomen, keterangan, created_at 
            FROM kunjungan_petugas WHERE periode = ? 
            ORDER BY created_at DESC LIMIT 10
        """, (periode_req,))
        logs = [dict(row) for row in cursor.fetchall()]

        return jsonify({
            "status": "success",
            "periode": periode_req,
            "summary": {
                "nomen": { "total": summary['total_nomen'], "lunas": summary['qty_bayar'], "sisa": summary['qty_belum'] },
                "nominal": { "mc": summary['total_rp_mc'], "undue": undue_val, "current": current_val, "sisa": summary['rp_sisa'] }
            },
            "analytics": analytics,
            "leaderboard": leaderboard,
            "logs": logs
        })
    finally:
        conn.close()

# =========================================================================
# 2. MONITORING REALISASI HARIAN (DAILY MONITOR)
# =========================================================================

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Fungsi monitoring harian cerdas. Menghitung laju progres (Current) vs saldo awal (Undue)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_latest_period(cursor)

        # AMBIL TARGET TOTAL
        cursor.execute("SELECT SUM(nominal) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_total = cursor.fetchone()[0] or 0

        # AMBIL REALISASI AWAL (UNDUE)
        cursor.execute("SELECT SUM(nominal) FROM master_bayar WHERE periode = ?", (periode_req,))
        undue_total = cursor.fetchone()[0] or 0

        # AMBIL LAJU HARIAN (COLLECTION)
        cursor.execute("""
            SELECT c.pay_dt as tgl, SUM(c.nominal) as rp_hari
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.nomen = p.nomen AND c.notag = p.notagihan
            WHERE p.periode = ? AND c.periode = ?
            GROUP BY c.pay_dt 
            ORDER BY substr(c.pay_dt,7,4), substr(c.pay_dt,4,2), substr(c.pay_dt,1,2) ASC
        """, (periode_req, periode_req))
        rows = cursor.fetchall()

        results = []
        running_total = undue_total
        for r in rows:
            running_total += r['rp_hari']
            pct = (running_total / target_total * 100) if target_total > 0 else 0
            results.append({
                "tgl": r['tgl'],
                "rp_hari": r['rp_hari'],
                "kumulatif": running_total,
                "pct": round(pct, 2)
            })

        return jsonify({
            "status": "success",
            "periode": periode_req,
            "data": results,
            "summary": {
                "target": target_total,
                "undue": undue_total,
                "current": running_total - undue_total,
                "total_realisasi": running_total
            }
        })
    finally:
        conn.close()
