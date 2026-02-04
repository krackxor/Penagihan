"""
API Dashboard - Sunter Dashboard Pro (V16.0 PCEZ & MC Report)
Update: 2026-02-05
Fitur:
1. Laporan MC (Current Target) yang jelas.
2. Distribusi PCEZ (Performa Area).
3. Distribusi Petugas (Performa Orang).
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

        # [A] LAPORAN MC (CURRENT TARGET)
        # Ini menjawab "Mana Laporan MC?". Ini adalah data Master Target bulan ini.
        q_mc = f"""
            SELECT 
                COUNT(*) as tot_nomen, 
                COALESCE(SUM(nominal),0) as tot_rp, 
                COALESCE(SUM(kubik),0) as tot_m3,
                
                -- Realisasi (Data dari Collection yang match dengan MC)
                COALESCE(SUM(CASE WHEN status_lunas=1 THEN 1 ELSE 0 END),0) as pay_nomen,
                COALESCE(SUM(CASE WHEN status_lunas=1 THEN nominal ELSE 0 END),0) as pay_rp,
                COALESCE(SUM(CASE WHEN status_lunas=1 THEN kubik ELSE 0 END),0) as pay_m3,

                -- Sisa (Belum Bayar)
                COALESCE(SUM(CASE WHEN status_lunas=0 THEN 1 ELSE 0 END),0) as owe_nomen,
                COALESCE(SUM(CASE WHEN status_lunas=0 THEN nominal ELSE 0 END),0) as owe_rp,
                COALESCE(SUM(CASE WHEN status_lunas=0 THEN kubik ELSE 0 END),0) as owe_m3
            FROM master_pelanggan WHERE periode = ? {rute_filter_mc}
        """
        mc = db.execute(q_mc, params_mc).fetchone()

        # [B] LAPORAN ARDEBT
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
        
        # Hitung Sisa Ardebt
        ard_owe_rp = max(0, ard_t['tot_rp'] - ard_r['pay_rp'])
        ard_owe_nomen = max(0, ard_t['tot_nomen'] - ard_r['pay_nomen'])

        # [C] UNDUE (Bayar Cepat)
        q_undue = f"""
            SELECT COUNT(DISTINCT nomen) as pay_nomen, COALESCE(SUM(nominal),0) as pay_rp
            FROM master_bayar WHERE periode = ? AND kategori = 'UNDUE' {rute_filter_bayar}
        """
        undue = db.execute(q_undue, params_bayar).fetchone()

        # [D] DISTRIBUSI PERFORMA (PCEZ & PETUGAS)
        
        # 1. Analisa PCEZ (Area) - INI YANG ANDA MINTA
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
        # Limit 10 terbawah (Area paling bermasalah ditampilkan duluan)
        rows_pcez = db.execute(q_pcez, params_mc).fetchall()

        # 2. Analisa Petugas (SDM)
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
        count_ekstrem = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik > 500 {rute_filter_mc}", params_mc).fetchone()['c']
        count_drop = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik = 0 {rute_filter_mc}", params_mc).fetchone()['c']
        count_prem = db.execute(f"SELECT COUNT(*) as c FROM master_pelanggan WHERE periode=? AND kubik > 75 AND status_lunas=0 {rute_filter_mc}", params_mc).fetchone()['c']

        # [F] RESPONSE
        return jsonify({
            "status": "success",
            "periode": periode,
            "grand_total": {
                "collection": mc['pay_rp'] + ard_r['pay_rp'] + undue['pay_rp'], # Realisasi Uang Masuk
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
                "pcez": [dict(r) for r in rows_pcez],       # Data PCEZ
                "petugas": [dict(r) for r in rows_petugas]  # Data Petugas
            },
            "anomali": { "ekstrem": count_ekstrem, "drop": count_drop, "premium": count_prem },
            "logs": [dict(row) for row in db.execute(f"SELECT nomen, petugas_name, keterangan, created_at FROM kunjungan_petugas WHERE periode=? ORDER BY created_at DESC LIMIT 5", (periode,)).fetchall()]
        })

    except Exception as e:
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
