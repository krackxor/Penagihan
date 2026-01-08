import os
import sqlite3
from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from datetime import datetime, timedelta

collection_bp = Blueprint('collection', __name__)

@collection_bp.route('/daily-monitor', methods=['GET'])
def daily_monitor():
    """
    Fungsi untuk memonitor koleksi harian (Rayon 34 & 35).
    Logika: (Kumulatif Harian + Saldo Awal MB) / Target MC
    """
    periode_req = request.args.get('periode')  # Format: MM-YYYY
    if not periode_req:
        return jsonify({"status": "error", "message": "Periode harus diisi"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. LOGIKA BULAN SEBELUMNYA (Untuk menghitung VAR)
        # ---------------------------------------------------
        curr_dt = datetime.strptime(f"01-{periode_req}", "%d-%m-%Y")
        prev_dt = curr_dt - timedelta(days=1)
        periode_prev = prev_dt.strftime("%m-%Y")

        # 2. AMBIL TARGET MC (Penyebut) - Menggunakan COALESCE agar tidak NULL
        # ---------------------------------------------------
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN rayon = '34' THEN nominal ELSE 0 END), 0) as target_34,
                COALESCE(SUM(CASE WHEN rayon = '35' THEN nominal ELSE 0 END), 0) as target_35,
                COALESCE(SUM(nominal), 0) as target_total
            FROM master_pelanggan WHERE periode = ?
        """, (periode_req,))
        target_res = cursor.fetchone()
        target = dict(target_res) if target_res else {"target_34": 0, "target_35": 0, "target_total": 0}

        # 3. AMBIL SALDO AWAL MB / UNDUE (Offset Awal)
        # ---------------------------------------------------
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN mb.nominal ELSE 0 END), 0) as undue_34,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN mb.nominal ELSE 0 END), 0) as undue_35,
                COALESCE(SUM(mb.nominal), 0) as undue_total
            FROM master_bayar mb
            JOIN master_pelanggan p ON mb.nomen = p.nomen
            WHERE mb.periode = ?
        """, (periode_req,))
        undue_res = cursor.fetchone()
        undue = dict(undue_res) if undue_res else {"undue_34": 0, "undue_35": 0, "undue_total": 0}

        # 4. AMBIL DATA HISTORIS BULAN LALU (Safe Query untuk VAR)
        # ---------------------------------------------------
        cursor.execute("""
            SELECT 
                (SELECT SUM(nominal) FROM master_pelanggan WHERE periode = ?) as tgt_prev,
                (SELECT SUM(nominal) FROM master_bayar WHERE periode = ?) as und_prev,
                (SELECT SUM(nominal) FROM collection_harian WHERE periode = ?) as curr_prev
        """, (periode_prev, periode_prev, periode_prev))
        prev_row = cursor.fetchone()
        
        tgt_p = prev_row['tgt_prev'] if prev_row and prev_row['tgt_prev'] else 0
        und_p = prev_row['und_prev'] if prev_row and prev_row['und_prev'] else 0
        cur_p = prev_row['curr_prev'] if prev_row and prev_row['curr_prev'] else 0
        pct_prev_total = ((und_p + cur_p) / tgt_p * 100) if tgt_p > 0 else 0

        # 5. AMBIL TRANSAKSI HARIAN (CURRENT)
        # ---------------------------------------------------
        cursor.execute("""
            SELECT 
                pay_dt as tgl,
                COUNT(CASE WHEN p.rayon = '34' THEN c.nomen END) as cust_34,
                COALESCE(SUM(CASE WHEN p.rayon = '34' THEN c.nominal ELSE 0 END), 0) as rp_34,
                COUNT(CASE WHEN p.rayon = '35' THEN c.nomen END) as cust_35,
                COALESCE(SUM(CASE WHEN p.rayon = '35' THEN c.nominal ELSE 0 END), 0) as rp_35
            FROM collection_harian c
            JOIN master_pelanggan p ON c.nomen = p.nomen
            WHERE c.periode = ?
            GROUP BY pay_dt ORDER BY pay_dt ASC
        """, (periode_req,))
        rows = cursor.fetchall()

        # 6. ITERASI PERHITUNGAN KUMULATIF & PERSENTASE
        # ---------------------------------------------------
        results = []
        cum_34_current = 0
        cum_35_current = 0
        
        base_34 = undue['undue_34']
        base_35 = undue['undue_35']
        base_total = undue['undue_total']

        for r in rows:
            cum_34_current += r['rp_34']
            cum_35_current += r['rp_35']
            
            total_harian_rp = r['rp_34'] + r['rp_35']
            total_cum_current = cum_34_current + cum_35_current
            
            # Proteksi Division by Zero: if target > 0
            p_34 = ((cum_34_current + base_34) / target['target_34'] * 100) if target['target_34'] > 0 else 0
            p_35 = ((cum_35_current + base_35) / target['target_35'] * 100) if target['target_35'] > 0 else 0
            p_total = ((total_cum_current + base_total) / target['target_total'] * 100) if target['target_total'] > 0 else 0

            results.append({
                "tgl": r['tgl'],
                "r34": {"cust": r['cust_34'], "rp": r['rp_34'], "pct": round(p_34, 2)},
                "r35": {"cust": r['cust_35'], "rp": r['rp_35'], "pct": round(p_35, 2)},
                "total": {
                    "cust": r['cust_34'] + r['cust_35'],
                    "rp": total_harian_rp,
                    "cum_all": total_cum_current + base_total,
                    "pct": round(p_total, 2)
                }
            })

        # 7. RESPONSE DATA
        # ---------------------------------------------------
        last_pct = results[-1]['total']['pct'] if results else (base_total / target['target_total'] * 100 if target['target_total'] > 0 else 0)
        
        return jsonify({
            "status": "success",
            "summary": {
                "target": target['target_total'],
                "realisasi": (results[-1]['total']['cum_all'] if results else base_total),
                "pct": round(last_pct, 2),
                "prev_pct": round(pct_prev_total, 2),
                "variance": round(last_pct - pct_prev_total, 2)
            },
            "data": results
        })

    except Exception as e:
        # Menampilkan pesan error spesifik jika terjadi kegagalan server
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
