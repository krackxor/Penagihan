"""
API Dashboard - Sunter Dashboard Pro (V14.1 Complete Data)
Update: 2026-02-05
---------------------------------------------------------------------------
Fitur:
1. Executive Summary (Angka Total).
2. ✅ DETAIL DATA LIST: Menyertakan Array [Nomen, Kubik, Nominal] untuk:
   - Current (Tagihan Bulan Ini)
   - Ardebt (Tunggakan)
   - Undue (Pembayaran Dini)
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime
from dateutil.relativedelta import relativedelta

dashboard_bp = Blueprint('dashboard', __name__)

def get_latest_active_period(db):
    try:
        res = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
        return res['periode'] if res else datetime.now().strftime('%m-%Y')
    except:
        return datetime.now().strftime('%m-%Y')

@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    db = get_db_connection()
    try:
        # [1] SETUP
        periode = request.args.get('periode') or get_latest_active_period(db)
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # Logic Filter Rute (Jika Petugas)
        rute_filter_mc = ""
        rute_filter_ardebt = ""
        rute_filter_bayar = ""
        params_mc = [periode]
        params_ardebt = [periode]
        params_bayar = [periode]

        if user_role == 'petugas' and petugas_id:
            # MC
            rute_filter_mc = "AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params_mc.append(petugas_id)
            # Ardebt & Bayar (Subquery Check)
            subquery_rute = "AND nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ? AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?))"
            
            rute_filter_ardebt = subquery_rute
            params_ardebt.append(periode)
            params_ardebt.append(petugas_id)
            
            rute_filter_bayar = subquery_rute
            params_bayar.append(periode)
            params_bayar.append(petugas_id)

        # ==========================================
        # [A] DATA MENTAH / DETAIL (LIST)
        # ==========================================
        
        # 1. LIST CURRENT (Master Pelanggan)
        # Ambil Nomen, Kubik, Nominal
        q_list_curr = f"""
            SELECT nomen, nama, kubik, nominal, status_lunas 
            FROM master_pelanggan 
            WHERE periode = ? {rute_filter_mc}
            ORDER BY nominal DESC LIMIT 1000
        """
        rows_curr = db.execute(q_list_curr, params_mc).fetchall()

        # 2. LIST ARDEBT (Tunggakan)
        # Ambil Nomen, Kubik (Volume), Nominal (Jumlah)
        q_list_ard = f"""
            SELECT nomen, volume as kubik, jumlah as nominal, periode_bill
            FROM ardebt 
            WHERE periode = ? {rute_filter_ardebt}
            ORDER BY jumlah DESC LIMIT 1000
        """
        rows_ard = db.execute(q_list_ard, params_ardebt).fetchall()

        # 3. LIST UNDUE (Realisasi Pembayaran Dini)
        # Ambil Nomen, Nominal (Kubik biasanya 0/null di tabel bayar)
        q_list_undue = f"""
            SELECT nomen, nominal, tgl_bayar 
            FROM master_bayar 
            WHERE periode = ? AND kategori = 'UNDUE' {rute_filter_bayar}
            ORDER BY tgl_bayar DESC LIMIT 1000
        """
        rows_undue = db.execute(q_list_undue, params_bayar).fetchall()

        # ==========================================
        # [B] AGREGAT / SUMMARY (ANGKA TOTAL)
        # ==========================================
        
        # Hitung Total dari List diatas (Biar sinkron)
        total_curr_target = sum(r['nominal'] for r in rows_curr)
        total_curr_real = sum(r['nominal'] for r in rows_curr if r['status_lunas'] == 1)
        
        total_ard_target = sum(r['nominal'] for r in rows_ard)
        
        # Realisasi Ardebt (Ambil dari Master Bayar kategori HISTORY)
        q_ard_real = f"SELECT COALESCE(SUM(nominal), 0) as total FROM master_bayar WHERE periode = ? AND kategori = 'HISTORY' {rute_filter_bayar}"
        total_ard_real = db.execute(q_ard_real, params_bayar).fetchone()['total']

        # Total Masuk (Cash In)
        total_money_in = total_curr_real + total_ard_real + sum(r['nominal'] for r in rows_undue)

        # ==========================================
        # [C] ANOMALI COUNTER
        # ==========================================
        # Ekstrem (>500m3 atau Naik 2x)
        count_ekstrem = 0
        for r in rows_curr:
            # Logika sederhana di python agar cepat
            if r['kubik'] > 500: count_ekstrem += 1
        
        # Drop (0 m3)
        count_drop = 0
        for r in rows_curr:
            if r['kubik'] == 0: count_drop += 1

        # Premium Nunggak (>75m3 & Belum Lunas)
        count_premium = 0
        for r in rows_curr:
            if r['kubik'] > 75 and r['status_lunas'] == 0: count_premium += 1

        # ==========================================
        # [D] RESPONSE
        # ==========================================
        return jsonify({
            "status": "success",
            "periode": periode,
            # 1. DATA RINGKASAN (Untuk Kartu Atas)
            "summary": {
                "keuangan": {
                    "total_masuk": total_money_in,
                    "current": { "target": total_curr_target, "realisasi": total_curr_real },
                    "ardebt": { "target": total_ard_target, "realisasi": total_ard_real },
                    "undue": { "realisasi": sum(r['nominal'] for r in rows_undue) }
                },
                "anomali": {
                    "ekstrem": count_ekstrem,
                    "drop": count_drop,
                    "premium_nunggak": count_premium
                }
            },
            # 2. DATA DETAIL (Untuk Tabel/List - Sesuai Request)
            "details": {
                "current": [dict(row) for row in rows_curr], # Berisi: nomen, nama, kubik, nominal
                "ardebt": [dict(row) for row in rows_ard],   # Berisi: nomen, kubik, nominal
                "undue": [dict(row) for row in rows_undue]   # Berisi: nomen, nominal
            }
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

# Logs System
@dashboard_bp.route('/admin/system-logs', methods=['GET'])
def get_system_logs():
    db = get_db_connection()
    try:
        logs = db.execute("SELECT * FROM system_logs ORDER BY created_at DESC LIMIT 50").fetchall()
        return jsonify({"status": "success", "data": [dict(row) for row in logs]})
    finally:
        db.close()
