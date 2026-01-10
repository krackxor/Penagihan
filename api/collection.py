"""
Collection API - Sunter Dashboard Pro
Sinergi & Smart Update:
1. Autopilot Periode: Otomatis mendeteksi bulan aktif terbaru jika request kosong.
2. Smart Sync: Menggunakan CAST(nomen AS TEXT) untuk menjamin koneksi data meskipun format Excel berubah-ubah.
3. Dual-Path Monitoring: Menggabungkan realisasi MB (Kantor) & Collection (Harian Petugas).
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

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Fungsi monitoring harian cerdas. Menghitung laju progres vs target bulanan secara real-time."""
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # --- 1. LOGIKA AUTOPILOT PERIODE ---
        # Jika user tidak memilih periode, sistem otomatis mengambil periode terakhir yang diupload
        periode_req = request.args.get('periode')
        if not periode_req:
            periode_req = get_latest_period(cursor)

        # --- 2. AMBIL TARGET MC (Penyebut Utama) ---
        # Menghitung target rupiah per Rayon untuk dasar persentase (%)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        target = dict(cursor.fetchone())

        # --- 3. AMBIL SALDO MB (UNDUE) - PINTU KANTOR ---
        # Menggunakan CAST agar link data tetap terjaga meskipun format Nomen di Excel berubah
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35,
                COALESCE(SUM(mb.nominal), 0) as undue_total
            FROM master_bayar mb
            INNER JOIN master_pelanggan p ON CAST(mb.notagihan AS TEXT) = CAST(p.notagihan AS TEXT)
            WHERE p.periode = ? AND mb.periode = ?
        """, (periode_req, periode_req))
        undue = dict(cursor.fetchone())

        # --- 4. AMBIL REALISASI COLLECTION (PINTU HARIAN PETUGAS) ---
        # Data laju harian untuk grafik progress bar
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END), 0) as rp_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END), 0) as rp_35
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON CAST(c.notag AS TEXT) = CAST(p.notagihan AS TEXT)
            WHERE p.periode = ? AND c.periode = ?
            GROUP BY c.pay_dt ORDER BY c.pay_dt ASC
        """, (periode_req, periode_req))
        rows = cursor.fetchall()

        # --- 5. ITERASI KUMULATIF & VARIANCE (LOGIKA SINERGI) ---
        results = []
        cum_34 = 0; cum_35 = 0
        base_34 = undue['undue_34']; base_35 = undue['undue_35']; base_total = undue['undue_total']
        
        # Persentase awal didasarkan pada data lunas kantor (MB)
        prev_pct = (base_total / target['target_total'] * 100) if target['target_total'] > 0 else 0

        for r in rows:
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            
            # Kalkulasi Persentase Gabungan (MB + Kumulatif Harian Petugas)
            p_34 = ((cum_34 + base_34) / target['target_34'] * 100) if target['target_34'] > 0 else 0
            p_35 = ((cum_35 + base_35) / target['target_35'] * 100) if target['target_35'] > 0 else 0
            
            total_current_rp = cum_34 + cum_35 + base_total
            p_total = (total_current_rp / target['target_total'] * 100) if target['target_total'] > 0 else 0

            results.append({
                "tgl": r['tgl'],
                "r34": {"rp": r['rp_34'], "pct": round(p_34, 2)},
                "r35": {"rp": r['rp_35'], "pct": round(p_35, 2)},
                "total": {
                    "rp_harian": r['rp_34'] + r['rp_35'],
                    "cum_all": total_current_rp,
                    "pct": round(p_total, 2),
                    "variance": round(p_total - prev_pct, 2) # Lonjakan performa dibanding hari sebelumnya
                }
            })
            prev_pct = p_total

        # Ringkasan Akhir untuk Card Atas Dashboard
        last_cum = results[-1]['total']['cum_all'] if results else base_total
        last_pct = results[-1]['total']['pct'] if results else round(prev_pct, 2)

        return jsonify({
            "status": "success", 
            "periode_aktif": periode_req,
            "data": results, 
            "summary": {
                "target": target['target_total'],
                "realisasi": last_cum,
                "pct": last_pct,
                "undue_mb": base_total
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@collection_bp.route('/daily-detail', methods=['GET'])
def daily_detail():
    """Rincian audit: Menampilkan list siapa saja nasabah yang membayar pada hari tertentu."""
    # Keamanan Internal: Guest (Publik) tidak bisa melihat detail nama nasabah
    if 'role' not in session:
        return jsonify({"status": "error", "message": "Akses detail hanya untuk Petugas/Admin"}), 403

    tgl = request.args.get('tgl') 
    periode = request.args.get('periode') 
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Query Sinergi: Menampilkan data pelanggan + PCEZ (Rute) untuk memudahkan pengecekan area
        cursor.execute("""
            SELECT 
                CAST(c.nomen AS TEXT) as nomen, p.nama, p.pcez, p.rayon, c.nominal
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON CAST(c.notag AS TEXT) = CAST(p.notagihan AS TEXT)
            WHERE c.pay_dt = ? AND p.periode = ? AND c.periode = ?
            ORDER BY c.nominal DESC
        """, (tgl, periode, periode))
        
        return jsonify({"status": "success", "data": [dict(row) for row in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
