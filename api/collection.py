"""
Collection API - Sunter Dashboard Pro
Logic: 
1. Daily Monitoring (Level 1 - Publik): Menampilkan grafik realisasi harian global.
2. Daily Detail (Level 2/3 - Internal): Menampilkan rincian bayar per nama pelanggan.
3. Sinergi: Kalkulasi Variance & Akumulasi Kumulatif Pintu Ganda (MC + MB + Coll).
"""

import os
import sqlite3
from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime, timedelta

collection_bp = Blueprint('collection', __name__)

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """Fungsi monitoring harian. Menghitung laju progres harian vs target bulanan."""
    periode_req = request.args.get('periode') # Format: MM-YYYY
    if not periode_req:
        return jsonify({"status": "error", "message": "Periode harus diisi"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. AMBIL TARGET MC (Penyebut Utama)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        target = dict(cursor.fetchone())

        # 2. AMBIL SALDO MB (UNDUE) - Pelanggan yang sudah lunas sebelum harian berjalan
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35,
                COALESCE(SUM(mb.nominal), 0) as undue_total
            FROM master_bayar mb
            INNER JOIN master_pelanggan p ON mb.notagihan = p.notagihan 
            WHERE p.periode = ? AND mb.periode = ?
        """, (periode_req, periode_req))
        undue = dict(cursor.fetchone())

        # 3. AMBIL REALISASI COLLECTION HARIAN
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END), 0) as rp_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END), 0) as rp_35
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.notag = p.notagihan 
            WHERE p.periode = ? AND c.periode = ?
            GROUP BY c.pay_dt ORDER BY c.pay_dt ASC
        """, (periode_req, periode_req))
        rows = cursor.fetchall()

        # 4. ITERASI KUMULATIF & VARIANCE
        results = []
        cum_34 = 0; cum_35 = 0
        base_34 = undue['undue_34']; base_35 = undue['undue_35']; base_total = undue['undue_total']
        
        prev_pct = (base_total / target['target_total'] * 100) if target['target_total'] > 0 else 0

        for r in rows:
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            
            # Kalkulasi Persentase (Base Undue + Kumulatif Harian)
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

        # Final Summary untuk Card Dashboard
        last_cum = results[-1]['total']['cum_all'] if results else base_total
        last_pct = results[-1]['total']['pct'] if results else round(prev_pct, 2)
        total_variance = results[-1]['total']['variance'] if results else 0

        return jsonify({
            "status": "success", 
            "data": results, 
            "summary": {
                "target": target['target_total'],
                "realisasi": last_cum,
                "pct": last_pct,
                "variance": total_variance 
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@collection_bp.route('/daily-detail', methods=['GET'])
def daily_detail():
    """Rincian drill-down: Siapa saja yang bayar pada tanggal tertentu."""
    if 'role' not in session:
        return jsonify({"status": "error", "message": "Akses terbatas untuk internal"}), 403

    tgl = request.args.get('tgl') 
    periode = request.args.get('periode') 
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Query Sinergi: Menampilkan data pelanggan + PCEZ (Rute) agar Admin bisa audit rute petugas
        cursor.execute("""
            SELECT 
                c.nomen, p.nama, p.pcez, p.rayon, c.nominal
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.notag = p.notagihan
            WHERE c.pay_dt = ? AND p.periode = ? AND c.periode = ?
            ORDER BY c.nominal DESC
        """, (tgl, periode, periode))
        
        return jsonify({"status": "success", "data": [dict(row) for row in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
