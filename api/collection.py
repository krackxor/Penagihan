import os
import sqlite3
from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime, timedelta

collection_bp = Blueprint('collection', __name__)

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    periode_req = request.args.get('periode') # MM-YYYY
    if not periode_req:
        return jsonify({"status": "error", "message": "Periode harus diisi"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. HITUNG TARGET MC (Penyebut Tetap)
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        target = dict(cursor.fetchone())

        # 2. HITUNG SALDO AWAL MB (Match by NOTAGIHAN)
        # Logika: Hanya hitung MB yang nomor tagihannya terdaftar di MC bulan ini
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

        # 3. HITUNG REALISASI HARIAN (Match by NOTAG)
        # KRUSIAL: Gunakan INNER JOIN pada NOTAG agar Ardebt tidak ikut terhitung di sini
        cursor.execute("""
            SELECT 
                c.pay_dt as tgl,
                COUNT(CASE WHEN p.rayon = '34' THEN c.nomen END) as cust_34,
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END), 0) as rp_34,
                COUNT(CASE WHEN p.rayon = '35' THEN c.nomen END) as cust_35,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END), 0) as rp_35
            FROM collection_harian c
            INNER JOIN master_pelanggan p ON c.notag = p.notagihan 
            WHERE p.periode = ? AND c.periode = ?
            GROUP BY c.pay_dt ORDER BY c.pay_dt ASC
        """, (periode_req, periode_req))
        rows = cursor.fetchall()

        # 4. ITERASI KUMULATIF (Running Total)
        results = []
        cum_34 = 0
        cum_35 = 0
        
        base_34 = undue['undue_34']
        base_35 = undue['undue_35']
        base_total = undue['undue_total']

        for r in rows:
            cum_34 += r['rp_34']
            cum_35 += r['rp_35']
            
            # % COLL = (Kumulatif + MB Undue) / Target MC
            p_34 = ((cum_34 + base_34) / target['target_34'] * 100) if target['target_34'] > 0 else 0
            p_35 = ((cum_35 + base_35) / target['target_35'] * 100) if target['target_35'] > 0 else 0
            p_total = ((cum_34 + cum_35 + base_total) / target['target_total'] * 100) if target['target_total'] > 0 else 0

            results.append({
                "tgl": r['tgl'],
                "r34": {"cust": r['cust_34'], "rp": r['rp_34'], "pct": round(p_34, 2)},
                "r35": {"cust": r['cust_35'], "rp": r['rp_35'], "pct": round(p_35, 2)},
                "total": {
                    "rp": r['rp_34'] + r['rp_35'],
                    "cum_all": cum_34 + cum_35 + base_total,
                    "pct": round(p_total, 2)
                }
            })

        return jsonify({"status": "success", "data": results, "summary": {"pct": results[-1]['total']['pct'] if results else 0}})
    finally:
        conn.close()
