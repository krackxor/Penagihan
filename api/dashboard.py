"""
API Dashboard - Sunter Dashboard Pro (V15.1 Petugas Performance)
Update: 2026-02-05
Fitur:
1. Analisa Performa per PETUGAS (bukan per PCEZ).
2. Laporan Collection (Total Uang Masuk).
3. Laporan Anomali (Ekstrem/Drop).
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

        # ==========================================
        # [A] DEEP DIVE: CURRENT (MC)
        # ==========================================
        q_curr = f"""
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
        curr = db.execute(q_curr, params_mc).fetchone()

        # ==========================================
        # [B] DEEP DIVE: ARDEBT (Tunggakan)
        # ==========================================
        q_ard_target = f"""
            SELECT COUNT(*) as tot_nomen, COALESCE(SUM(jumlah),0) as tot_rp, COALESCE(SUM(volume),0) as tot_m3
            FROM ardebt WHERE periode = ? {rute_filter_ardebt}
        """
        ard_t = db.execute(q_ard_target, params_ardebt).fetchone()

        q_ard_real = f"""
            SELECT COUNT(DISTINCT nomen) as pay_nomen, COALESCE(SUM(nominal),0) as pay_rp
            FROM master_bayar WHERE periode = ? AND kategori = 'HISTORY' {rute_filter_bayar}
        """
        ard_r = db.execute(q_ard_real, params_bayar).fetchone()

        # Hitung Sisa
        ard_owe_rp = max(0, ard_t['tot_rp'] - ard_r['pay_rp'])
        ard_owe_nomen = max(0, ard_t['tot_nomen'] - ard_r['pay_nomen'])

        # ==========================================
        # [C] DEEP DIVE: UNDUE (Bayar Cepat)
        # ==========================================
        q_undue = f"""
            SELECT COUNT(DISTINCT nomen) as pay_nomen, COALESCE(SUM(nominal),0) as pay_rp
            FROM master_bayar WHERE periode = ? AND kategori = 'UNDUE' {rute_filter_bayar}
        """
        undue = db.execute(q_undue, params_bayar).fetchone()

        # ==========================================
        # [D] PETUGAS PERFORMANCE (Aggregated PCEZ)
        # ==========================================
        # Menggabungkan semua PCEZ milik satu petugas dan menghitung % lunasnya
        q_petugas = f"""
            SELECT 
                r.petugas, 
                COUNT(p.id) as load_plg,
                SUM(p.status_lunas) as lunas_plg,
                COALESCE(SUM(p.nominal),0) as target_rp,
                COALESCE(SUM(CASE WHEN p.status_lunas=1 THEN p.nominal ELSE 0 END),0) as realisasi_rp,
                ROUND(CAST(SUM(p.status_lunas) as FLOAT) / MAX(1, COUNT(p.id)) * 100, 1) as pct
            FROM rute_petugas r
            JOIN master_pelanggan p ON r.pcez = p.pcez
            WHERE p.periode = ? {rute_filter_mc}
            GROUP BY r.petugas 
            ORDER BY pct DESC
        """
        rows_petugas = db.execute(q_petugas, params_mc).fetchall()
        
        # Pisahkan Top 5 (Green) dan Bottom 5 (Red)
        ptg_best = [dict(r) for r in rows_petugas[:5]]
        ptg_worst = [dict(r) for r in rows_petugas[-5:]] if len(rows_petugas) > 5 else []

        # ==========================================
        # [E] ANOMALI
        # ==========================================
        count_ekstrem = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik > 500 {rute_filter_mc}", params_mc).fetchone()['c']
        count_drop = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik = 0 {rute_filter_mc}", params_mc).fetchone()['c']
        count_prem = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik > 75 AND status_lunas=0 {rute_filter_mc}", params_mc).fetchone()['c']

        # ==========================================
        # [F] RESPONSE
        # ==========================================
        return jsonify({
            "status": "success",
            "periode": periode,
            "grand_total": {
                "collection": curr['pay_rp'] + ard_r['pay_rp'] + undue['pay_rp'],
                "target_billing": curr['tot_rp'] + ard_t['tot_rp']
            },
            "breakdown": {
                "current": {
                    "target": { "nomen": curr['tot_nomen'], "rp": curr['tot_rp'], "kubik": curr['tot_m3'] },
                    "bayar": { "nomen": curr['pay_nomen'], "rp": curr['pay_rp'], "kubik": curr['pay_m3'] },
                    "belum": { "nomen": curr['owe_nomen'], "rp": curr['owe_rp'], "kubik": curr['owe_m3'] }
                },
                "ardebt": {
                    "target": { "nomen": ard_t['tot_nomen'], "rp": ard_t['tot_rp'], "kubik": ard_t['tot_m3'] },
                    "bayar": { "nomen": ard_r['pay_nomen'], "rp": ard_r['pay_rp'], "kubik": 0 },
                    "belum": { "nomen": ard_owe_nomen, "rp": ard_owe_rp, "kubik": ard_t['tot_m3'] }
                },
                "undue": {
                    "bayar": { "nomen": undue['pay_nomen'], "rp": undue['pay_rp'] }
                }
            },
            "petugas_analytics": {
                "best": ptg_best,
                "worst": ptg_worst
            },
            "anomali": {
                "ekstrem": count_ekstrem,
                "drop": count_drop,
                "premium": count_prem
            },
            "logs": [dict(row) for row in db.execute(f"SELECT nomen, petugas_name, keterangan, created_at FROM kunjungan_petugas WHERE periode=? ORDER BY created_at DESC LIMIT 5", (periode,)).fetchall()]
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
