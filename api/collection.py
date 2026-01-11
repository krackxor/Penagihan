"""
Collection API - Sunter Dashboard Pro (V7.0 Sinergi Intelligence)
Sinergi & Smart Update:
1. Cross-Period Sync: Menghubungkan realisasi harian dengan target periode yang sesuai.
2. NOMEN Integrity: Menggunakan CAST(nomen AS TEXT) untuk akurasi join lintas tabel.
3. Multi-Rayon Analytics: Breakdown performa otomatis untuk Rayon 34 & 35.
4. Variance Tracking: Menghitung lonjakan performa harian secara real-time.
"""

import os
import sqlite3
from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime

collection_bp = Blueprint('collection', __name__)

def get_latest_period(cursor):
    """FUNGSI AUTOPILOT: Mendapatkan periode terakhir yang tersedia di database."""
    # Mengambil periode terbaru dari Master Pelanggan sebagai acuan target aktif
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Fungsi monitoring harian cerdas. Menghitung laju progres vs target bulanan."""
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # --- 1. LOGIKA AUTOPILOT PERIODE ---
        # Mengambil periode dari request atau otomatis ke periode master terbaru
        periode_req = request.args.get('periode')
        if not periode_req:
            periode_req = get_latest_period(cursor)

        # --- 2. AMBIL TARGET MC (Penyebut Utama) ---
        # Menghitung total rupiah per Rayon sebagai dasar kalkulasi persentase (%)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        target = dict(cursor.fetchone())

        # --- 3. AMBIL REALISASI MB (LUNAS KANTOR) ---
        # Mengambil saldo undue dari Master Bayar yang periodenya cocok dengan Master Pelanggan
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35,
                COALESCE(SUM(mb.nominal), 0) as undue_total
            FROM master_bayar mb
            INNER JOIN master_pelanggan p ON CAST(mb.nomen AS TEXT) = CAST(p.nomen AS TEXT) 
                                         AND CAST(mb.notagihan AS TEXT) = CAST(p.notagihan AS TEXT)
            WHERE p.periode = ? AND mb.periode = ?
        """, (periode_req, periode_req))
        undue = dict(cursor.fetchone())

        # --- 4. AMBIL REALISASI COLLECTION (SETORAN HARIAN) ---
        # Mengelompokkan setoran berdasarkan tanggal untuk grafik progress
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END), 0) as rp_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END), 0) as rp_35
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON CAST(c.nomen AS TEXT) = CAST(p.nomen AS TEXT)
                                         AND CAST(c.notag AS TEXT) = CAST(p.notagihan AS TEXT)
            WHERE p.periode = ? AND c.periode = ?
            GROUP BY c.pay_dt ORDER BY substr(c.pay_dt,7,4), substr(c.pay_dt,4,2), substr(c.pay_dt,1,2) ASC
        """, (periode_req, periode_req))
        rows = cursor.fetchall()

        # --- 5. KALKULASI KUMULATIF & VARIANCE ---
        results = []
        cum_34 = 0; cum_35 = 0
        base_34 = undue['undue_34']; base_35 = undue['undue_35']; base_total = undue['undue_total']
        
        # Persentase dasar dari realisasi kantor (MB)
        prev_pct = (base_total / target['target_total'] * 100) if target['target_total'] > 0 else 0

        for r in rows:
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            
            # Persentase Gabungan per Rayon (MB + Collection Harian)
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
                    "variance": round(p_total - prev_pct, 2)
                }
            })
            prev_pct = p_total

        # Summary untuk Card Atas
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
    """Rincian audit: List nasabah yang melakukan pembayaran pada tanggal tertentu."""
    if 'role' not in session:
        return jsonify({"status": "error", "message": "Akses Ditolak"}), 403

    tgl = request.args.get('tgl') 
    periode = request.args.get('periode') 
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Menggunakan join ganda (Nomen & Notagihan) untuk akurasi data snapshot
        cursor.execute("""
            SELECT 
                CAST(c.nomen AS TEXT) as nomen, p.nama, p.pcez, p.rayon, c.nominal
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON CAST(c.nomen AS TEXT) = CAST(p.nomen AS TEXT)
                                         AND CAST(c.notag AS TEXT) = CAST(p.notagihan AS TEXT)
            WHERE c.pay_dt = ? AND p.periode = ? AND c.periode = ?
            ORDER BY c.nominal DESC
        """, (tgl, periode, periode))
        
        return jsonify({"status": "success", "data": [dict(row) for row in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
