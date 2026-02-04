"""
API Dashboard - Sunter Dashboard Pro (V16.5 Safe Mode & Debug)
Update: 2026-02-05
Fitur:
1. ✅ DEBUG LOGS: Menampilkan proses di Terminal agar ketahuan macet dimana.
2. ✅ ANTI-CRASH: Menangani nilai NULL/None dengan ketat.
3. ✅ ZERO DIVISION FIX: Mencegah error pembagian nol.
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
    print("--- [DEBUG] Memulai Request Dashboard ---") # DEBUG
    db = get_db_connection()
    try:
        # [1] SETUP
        periode = request.args.get('periode') or get_latest_active_period(db)
        print(f"--- [DEBUG] Periode Aktif: {periode}") # DEBUG
        
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # Filter Rute
        rute_filter_mc = ""
        rute_filter_ardebt = ""
        rute_filter_bayar = ""
        params_mc = [periode]
        params_ardebt = [periode]
        params_bayar = [periode]

        if user_role == 'petugas' and petugas_id:
            rute_filter_mc = "AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params_mc.append(petugas_id)
            subquery = "AND nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ? AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?))"
            rute_filter_ardebt = subquery
            params_ardebt.append(periode)
            params_ardebt.append(petugas_id)
            rute_filter_bayar = subquery
            params_bayar.append(periode)
            params_bayar.append(petugas_id)

        # [A] LAPORAN MC
        print("--- [DEBUG] Query MC...") # DEBUG
        q_mc = f"""
            SELECT 
                COUNT(*) as tot_nomen, 
                COALESCE(SUM(nominal),0) as tot_rp, 
                COALESCE(SUM(kubik),0) as tot_m3,
                COALESCE(SUM(CASE WHEN status_lunas=1 THEN 1 ELSE 0 END),0) as pay_nomen,
                COALESCE(SUM(CASE WHEN status_lunas=1 THEN nominal ELSE 0 END),0) as pay_rp,
                COALESCE(SUM(CASE WHEN status_lunas=1 THEN kubik ELSE 0 END),0) as pay_m3,
                COALESCE(SUM(CASE WHEN status_lunas=0 THEN 1 ELSE 0 END),0) as owe_nomen,
                COALESCE(SUM(CASE WHEN status_lunas=0 THEN nominal ELSE 0 END),0) as owe_rp,
                COALESCE(SUM(CASE WHEN status_lunas=0 THEN kubik ELSE 0 END),0) as owe_m3
            FROM master_pelanggan WHERE periode = ? {rute_filter_mc}
        """
        mc = db.execute(q_mc, params_mc).fetchone()
        # Safe Dictionary Convert (Jika result None)
        mc = dict(mc) if mc else {'tot_nomen':0, 'tot_rp':0, 'tot_m3':0, 'pay_nomen':0, 'pay_rp':0, 'pay_m3':0, 'owe_nomen':0, 'owe_rp':0, 'owe_m3':0}

        # [B] LAPORAN ARDEBT
        print("--- [DEBUG] Query Ardebt...") # DEBUG
        # Pastikan tabel ardebt ada, jika error sql akan ditangkap except
        q_ard_target = f"""
            SELECT COUNT(*) as tot_nomen, COALESCE(SUM(jumlah),0) as tot_rp, COALESCE(SUM(volume),0) as tot_m3
            FROM ardebt WHERE periode = ? {rute_filter_ardebt}
        """
        ard_t = db.execute(q_ard_target, params_ardebt).fetchone()
        ard_t = dict(ard_t) if ard_t else {'tot_nomen':0, 'tot_rp':0, 'tot_m3':0}

        q_ard_real = f"""
            SELECT COUNT(DISTINCT nomen) as pay_nomen, COALESCE(SUM(nominal),0) as pay_rp
            FROM master_bayar WHERE periode = ? AND kategori = 'HISTORY' {rute_filter_bayar}
        """
        ard_r = db.execute(q_ard_real, params_bayar).fetchone()
        ard_r = dict(ard_r) if ard_r else {'pay_nomen':0, 'pay_rp':0}
        
        ard_owe_rp = max(0, ard_t['tot_rp'] - ard_r['pay_rp'])
        ard_owe_nomen = max(0, ard_t['tot_nomen'] - ard_r['pay_nomen'])

        # [C] UNDUE
        print("--- [DEBUG] Query Undue...") # DEBUG
        q_undue = f"""
            SELECT COUNT(DISTINCT nomen) as pay_nomen, COALESCE(SUM(nominal),0) as pay_rp
            FROM master_bayar WHERE periode = ? AND kategori = 'UNDUE' {rute_filter_bayar}
        """
        undue = db.execute(q_undue, params_bayar).fetchone()
        undue = dict(undue) if undue else {'pay_nomen':0, 'pay_rp':0}

        # [D] DISTRIBUSI
        print("--- [DEBUG] Query Distribusi...") # DEBUG
        q_pcez = f"""
            SELECT 
                pcez,
                COUNT(*) as beban,
                SUM(status_lunas) as lunas,
                ROUND(CAST(SUM(status_lunas) as FLOAT) / MAX(1, COUNT(*)) * 100, 1) as pct,
                COALESCE(SUM(CASE WHEN status_lunas=0 THEN nominal ELSE 0 END),0) as sisa_rp
            FROM master_pelanggan 
            WHERE periode = ? {rute_filter_mc}
            GROUP BY pcez 
            ORDER BY pct ASC LIMIT 10 
        """
        rows_pcez = db.execute(q_pcez, params_mc).fetchall()

        q_petugas = f"""
            SELECT 
                r.petugas, 
                COUNT(p.id) as beban,
                SUM(p.status_lunas) as lunas,
                ROUND(CAST(SUM(p.status_lunas) as FLOAT) / MAX(1, COUNT(p.id)) * 100, 1) as pct
            FROM rute_petugas r
            JOIN master_pelanggan p ON r.pcez = p.pcez
            WHERE p.periode = ? {rute_filter_mc}
            GROUP BY r.petugas 
            ORDER BY pct DESC LIMIT 5
        """
        rows_petugas = db.execute(q_petugas, params_mc).fetchall()

        # [E] ANOMALI
        print("--- [DEBUG] Query Anomali...") # DEBUG
        # Gunakan try-except per query anomali untuk keamanan jika kolom kubik error
        try:
            count_ekstrem = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik > 500 {rute_filter_mc}", params_mc).fetchone()['c']
            count_drop = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik = 0 {rute_filter_mc}", params_mc).fetchone()['c']
            count_prem = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik > 75 AND status_lunas=0 {rute_filter_mc}", params_mc).fetchone()['c']
        except Exception as ex_anom:
            print(f"--- [DEBUG] Error Anomali: {ex_anom}")
            count_ekstrem = 0
            count_drop = 0
            count_prem = 0

        # [F] RESPONSE
        print("--- [DEBUG] Building Response...") # DEBUG
        response_data = {
            "status": "success",
            "periode": periode,
            "grand_total": {
                "collection": mc['pay_rp'] + ard_r['pay_rp'] + undue['pay_rp'],
                "target_mc": mc['tot_rp'],
                "target_ardebt": ard_t['tot_rp']
            },
            "laporan_mc": {
                "target": { "nomen": mc['tot_nomen'], "rp": mc['tot_rp'], "kubik": mc['tot_m3'] },
                "lunas": { "nomen": mc['pay_nomen'], "rp": mc['pay_rp'], "kubik": mc['pay_m3'] },
                "sisa": { "nomen": mc['owe_nomen'], "rp": mc['owe_rp'], "kubik": mc['owe_m3'] }
            },
            "laporan_ardebt": {
                "target": { "nomen": ard_t['tot_nomen'], "rp": ard_t['tot_rp'], "kubik": ard_t['tot_m3'] },
                "lunas": { "nomen": ard_r['pay_nomen'], "rp": ard_r['pay_rp'] },
                "sisa": { "nomen": ard_owe_nomen, "rp": ard_owe_rp }
            },
            "undue": undue['pay_rp'],
            "distribusi": {
                "pcez": [dict(r) for r in rows_pcez],
                "petugas": [dict(r) for r in rows_petugas]
            },
            "anomali": { "ekstrem": count_ekstrem, "drop": count_drop, "premium": count_prem },
            "logs": []
        }
        
        print("--- [DEBUG] Success! Sending Data. ---") # DEBUG
        return jsonify(response_data)

    except Exception as e:
        print(f"!!! CRITICAL ERROR API DASHBOARD: {str(e)}") # PRINT KE TERMINAL
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@dashboard_bp.route('/admin/system-logs', methods=['GET'])
def get_system_logs():
    db = get_db_connection()
    try:
        logs = db.execute("SELECT * FROM system_logs ORDER BY created_at DESC LIMIT 50").fetchall()
        return jsonify({"status": "success", "data": [dict(row) for row in logs]})
    finally:
        db.close()
