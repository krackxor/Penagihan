"""
Collection API - Sunter Dashboard Pro (V12.50 Rayon-Specific Undue Alignment)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Rayon-Specific Realization: Memisahkan nominal UNDUE (Bank) per Rayon 34 & 35.
2. Accurate Cumulative Formula: (Cum Harian + Undue Rayon) / Target Rayon.
3. ✅ FIX: 171% Prevention - Menghitung realisasi gabungan tanpa double count.
4. Year-Guard Integration: Mengabaikan data tanggal yang tidak valid (format tahun).
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime

collection_bp = Blueprint('collection', __name__)

def get_active_period(cursor):
    """Mendeteksi periode dashboard aktif terbaru."""
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@collection_bp.route('/pusat-kendali', methods=['GET'])
def pusat_kendali():
    """Summary Dashboard: Konsolidasi Realisasi Tanpa Double Counting."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)
        
        # 1. TOTAL TARGET MC (Master Customer)
        cursor.execute("SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan WHERE periode = ?", (periode_req,))
        target_mc = cursor.fetchone()[0] or 0

        # 2. BOX UNDUE (BANK) 
        cursor.execute("""
            SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE'
            AND mb.nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ?)
        """, (periode_req, periode_req))
        undue_val = cursor.fetchone()[0] or 0

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

        # ✅ PERBAIKAN LOGIKA: Hitung Realisasi Berdasarkan Nomen yang Lunas di Master
        cursor.execute("""
            SELECT COALESCE(SUM(nominal), 0) 
            FROM master_pelanggan 
            WHERE periode = ? AND status_lunas = 1
        """, (periode_req,))
        realisasi_valid = cursor.fetchone()[0] or 0

        total_raw = undue_val + current_petugas + current_mandiri
        total_realisasi = min(target_mc, realisasi_valid if realisasi_valid > 0 else total_raw)

        pct_mentah = (total_realisasi / max(1, target_mc) * 100)

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
                "pct": round(min(100, pct_mentah), 2)
            }
        })
    finally:
        conn.close()

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Tren Kumulatif Harian per Rayon dengan Filter Periode Ketat & Rumus Khusus."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode_req = request.args.get('periode') or get_active_period(cursor)

        # 1. AMBIL TARGET MC PER RAYON
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as mc_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as mc_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'
        """, (periode_req,))
        targets = dict(cursor.fetchone())

        # 2. AMBIL REALISASI BANK (UNDUE) PER RAYON
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35,
                COALESCE(SUM(mb.nominal), 0) as undue_total
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen AND mb.periode = p.periode
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE'
        """, (periode_req, periode_req))
        undue = dict(cursor.fetchone())

        # 3. QUERY REALISASI LAPANGAN HARIAN
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
        cum_field_34, cum_field_35 = 0, 0
        
        for r in rows:
            # Proteksi jika tanggal hanya berisi tahun (misal: "2026")
            if not r['tgl'] or len(str(r['tgl'])) <= 4: continue 
            
            # Kumulatif Lapangan saja
            cum_field_34 += r['rp_34']
            cum_field_35 += r['rp_35']
            
            # RUMUS: (Kumulatif Lapangan + Total Bank Rayon)
            cum_total_34 = cum_field_34 + undue['undue_34']
            cum_total_35 = cum_field_35 + undue['undue_35']
            cum_all = cum_total_34 + cum_total_35
            
            daily_data.append({
                "tgl": r['tgl'],
                "r34": { 
                    "rp": r['rp_34'], 
                    "cum": cum_total_34, 
                    "pct": round(min(100, (cum_total_34 / max(1, targets['mc_34']) * 100)), 2) 
                },
                "r35": { 
                    "rp": r['rp_35'], 
                    "cum": cum_total_35, 
                    "pct": round(min(100, (cum_total_35 / max(1, targets['mc_35']) * 100)), 2) 
                },
                "total": { 
                    "rp_harian": r['rp_total'], 
                    "cum_all": cum_all, 
                    "pct": round(min(100, (cum_all / max(1, targets['target_total']) * 100)), 2) 
                }
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
