"""
Collection API - Sunter Dashboard Pro (V11.5 Smart Audit & Rayon Logic)
Update: 2026-01-12
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Smart Audit Logic: Memisahkan Current Petugas (Ada Kunjungan) vs Current Mandiri.
2. Rayon Split Analysis: Detail harian Rp & % untuk Rayon 34 & 35.
3. Integrated Pivot: Sinkronisasi data Master, MB, Collection, dan Kunjungan.
4. Temporal Integrity: Pengurutan kronologis SQL standar untuk monitoring harian.
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
    """Summary Audit: Memisahkan realisasi berdasarkan bukti kerja lapangan."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # 1. Target MC & Total Lunas
        cursor.execute("""
            SELECT 
                COALESCE(SUM(nominal), 0) as target_mc,
                COALESCE(SUM(CASE WHEN status_lunas = 1 THEN nominal ELSE 0 END), 0) as rp_lunas,
                COALESCE(SUM(CASE WHEN status_lunas = 0 THEN nominal ELSE 0 END), 0) as rp_sisa
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        master = dict(cursor.fetchone())

        # 2. Logika UNDUE (Bank/Mandiri Pre-Period)
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) FROM (
                SELECT nominal FROM master_bayar WHERE periode = ? AND kategori = 'UNDUE'
                UNION ALL
                SELECT nominal FROM collection_harian WHERE periode = ? AND kategori = 'UNDUE'
            )
        """, (periode_req, periode_req))
        undue_val = cursor.fetchone()[0]

        # 3. Logika CURRENT PETUGAS (Bayar + Ada Bukti Kunjungan)
        cursor.execute("""
            SELECT COALESCE(SUM(p.nominal), 0) FROM (
                SELECT nomen, nominal FROM master_bayar WHERE periode = ? AND kategori = 'CURRENT'
                UNION ALL
                SELECT nomen, nominal FROM collection_harian WHERE periode = ? AND kategori = 'CURRENT'
            ) p
            WHERE EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = p.nomen AND k.periode = ?
            )
        """, (periode_req, periode_req))
        current_petugas = cursor.fetchone()[0]

        # 4. Logika CURRENT MANDIRI (Bayar + Tanpa Kunjungan)
        current_mandiri = master['rp_lunas'] - undue_val - current_petugas

        return jsonify({
            "status": "success",
            "periode": periode_req,
            "summary": {
                "target_mc": master['target_mc'],
                "realisasi": {
                    "total": master['rp_lunas'],
                    "undue": undue_val,
                    "current_petugas": current_petugas,
                    "current_mandiri": current_mandiri
                },
                "sisa_tagihan": master['rp_sisa']
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Monitoring harian dengan rincian Rayon 34 & 35."""
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

        # Ambil Saldo Awal Undue
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) FROM (
                SELECT nominal FROM master_bayar WHERE periode = ? AND kategori = 'UNDUE'
                UNION ALL
                SELECT nominal FROM collection_harian WHERE periode = ? AND kategori = 'UNDUE'
            )
        """, (periode_req, periode_req))
        undue_start = cursor.fetchone()[0]

        # Query Pivot Harian
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
            "periode": periode_req,
            "data": daily_data,
            "summary": {
                "target": targets['target_total'],
                "pct": (cum_all / targets['target_total'] * 100) if rows and targets['target_total'] > 0 else 0,
                "realisasi": cum_all if rows else undue_start
            }
        })
    finally:
        conn.close()
