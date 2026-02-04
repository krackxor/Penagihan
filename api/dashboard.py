"""
API Dashboard - Sunter Dashboard Pro (V16.0 Data Integrity Patch)
Update: 2026-02-05
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ DATA INTEGRITY: Perhitungan N/V/M (Nomen, Volume, Money) yang presisi.
2. ✅ FULL BREAKDOWN: Memisahkan Bayar vs Belum untuk MC, Ardebt, dan Prioritas.
3. ✅ CATEGORY ISOLATION: Pemisahan tegas antara Undue (Bank) dan Current (Lapangan).
4. ✅ SMART-JOIN PRESERVATION: Mempertahankan TRIM() pcez dan sistem logs asli.
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
    """Laporan ringkasan eksekutif dengan validasi integritas data (N/V/M)."""
    db = get_db_connection()
    try:
        # [1] PERIODE & ROLE DETECTION
        periode = request.args.get('periode') or get_latest_active_period(db)
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # [2] REKENING TARGET ALIGNMENT (N-1)
        try:
            dt_obj = datetime.strptime(periode, '%m-%Y')
            target_dt = dt_obj - relativedelta(months=1)
            bulan_rek_target = target_dt.strftime('%m%Y')
        except:
            bulan_rek_target = periode.replace('-', '')

        # [3] ROBUST FILTERING (Keamanan Data Petugas)
        p_filter = ""
        p_params = [periode]
        if user_role == 'petugas' and petugas_id:
            p_filter = " AND m.pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            p_params.append(petugas_id)

        # --- 4. DATA INTEGRITY CORE: MAIN COLLECTION (MC) ---
        # Menghitung Total Target vs Pelunasan (Nomen, Volume, Money)
        mc_core = db.execute(f"""
            SELECT 
                COUNT(*) as t_n, SUM(m.kubik) as t_v, SUM(m.nominal) as t_m,
                SUM(CASE WHEN m.status_lunas = 1 THEN 1 ELSE 0 END) as b_n,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.kubik ELSE 0 END) as b_v,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.nominal ELSE 0 END) as b_m
            FROM master_pelanggan m 
            WHERE m.periode = ? AND m.tipe = 'MC' {p_filter}
        """, p_params).fetchone()

        # --- 5. DATA INTEGRITY CORE: UNDUE vs CURRENT ---
        # [A] UNDUE (REALISASI BANK)
        undue_raw = db.execute(f"""
            SELECT 
                COUNT(DISTINCT mb.nomen) as n, SUM(mb.nominal) as m,
                (SELECT SUM(m2.kubik) FROM master_pelanggan m2 
                 WHERE m2.nomen = mb.nomen AND m2.periode = mb.periode) as v
            FROM master_bayar mb 
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
            AND mb.nomen IN (SELECT nomen FROM master_pelanggan m WHERE m.periode = ? {p_filter})
        """, [periode, bulan_rek_target, periode] + (p_params[1:] if len(p_params)>1 else [])).fetchone()

        # [B] CURRENT (REALISASI LAPANGAN/COLLECTION)
        current_raw = db.execute(f"""
            SELECT 
                COUNT(DISTINCT ch.nomen) as n, SUM(ch.nominal) as m, SUM(ch.vol_collect) as v
            FROM collection_harian ch
            WHERE ch.periode = ? AND ch.kategori = 'CURRENT'
            AND ch.nomen IN (SELECT nomen FROM master_pelanggan m WHERE m.periode = ? {p_filter})
        """, [periode, periode] + (p_params[1:] if len(p_params)>1 else [])).fetchone()

        # --- 6. DATA INTEGRITY CORE: ARDEBT (PIUTANG LAMA) ---
        ardebt_tgt = db.execute(f"SELECT COUNT(*) as n, SUM(volume) as v, SUM(jumlah) as m FROM ardebt WHERE periode = ?", (periode,)).fetchone()
        
        # Realisasi Bayar Ardebt (Bank + Lapangan)
        ardebt_paid = db.execute(f"""
            SELECT COUNT(DISTINCT nomen) as n, SUM(nominal) as m, SUM(v_kub) as v
            FROM (
                SELECT nomen, nominal, 0 as v_kub FROM master_bayar WHERE periode = ? AND kategori = 'ARDEBT'
                UNION ALL
                SELECT nomen, nominal, vol_collect as v_kub FROM collection_harian WHERE periode = ? AND kategori = 'ARDEBT'
            ) WHERE nomen IN (SELECT nomen FROM master_pelanggan m WHERE m.periode = ? {p_filter})
        """, [periode, periode, periode] + (p_params[1:] if len(p_params)>1 else [])).fetchone()

        # --- 7. DATA INTEGRITY CORE: PRIORITAS & ANOMALI ---
        prio_raw = db.execute(f"""
            SELECT 
                COUNT(*) as t_n, SUM(m.kubik) as t_v, SUM(m.nominal) as t_m,
                SUM(CASE WHEN m.status_lunas = 1 THEN 1 ELSE 0 END) as b_n,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.kubik ELSE 0 END) as b_v,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.nominal ELSE 0 END) as b_m
            FROM master_pelanggan m 
            WHERE m.periode = ? AND m.is_prioritas = 1 {p_filter}
        """, p_params).fetchone()

        # Anomali: Ekstrem (>500m3) & Drop (<5m3)
        count_eks = db.execute(f"SELECT COUNT(*) FROM master_pelanggan m WHERE m.periode = ? AND m.kubik > 500 {p_filter}", p_params).fetchone()[0]
        count_drp = db.execute(f"SELECT COUNT(*) FROM master_pelanggan m WHERE m.periode = ? AND m.kubik < 5 {p_filter}", p_params).fetchone()[0]

        # --- 8. SMART JOIN ANALYTICS (Preserved Feature) ---
        query_pcez = f"""
            SELECT 
                m.pcez, m.rayon, COALESCE(r.petugas, 'UNMAPPED') as petugas,
                COUNT(m.id) as n_target, SUM(m.nominal) as m_target,
                SUM(m.status_lunas) as n_lunas,
                ROUND((CAST(SUM(m.status_lunas) AS FLOAT) / MAX(1, COUNT(m.id))) * 100, 1) as pct
            FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON TRIM(m.pcez) = TRIM(r.pcez)
            WHERE m.periode = ? AND m.tipe = 'MC' {p_filter}
            GROUP BY m.pcez ORDER BY m.rayon ASC, m.pcez ASC
        """
        res_pcez = db.execute(query_pcez, p_params).fetchall()

        # --- 9. FINAL EXECUTIVE MAPPING ---
        return jsonify({
            "status": "success",
            "target_rekening": bulan_rek_target,
            "summaries": {
                "mc": {
                    "total": {"n": mc_core['t_n'], "v": mc_core['t_v'], "m": mc_core['t_m']},
                    "bayar": {"n": mc_core['b_n'], "v": mc_core['b_v'], "m": mc_core['b_m']},
                    "sisa":  {"n": mc_core['t_n'] - mc_core['b_n'], "v": (mc_core['t_v'] or 0) - (mc_core['b_v'] or 0), "m": (mc_core['t_m'] or 0) - (mc_core['b_m'] or 0)}
                },
                "undue_bank": {
                    "bayar": {"n": undue_raw['n'] or 0, "v": undue_raw['v'] or 0, "m": undue_raw['m'] or 0}
                },
                "current_field": {
                    "bayar": {"n": current_raw['n'] or 0, "v": current_raw['v'] or 0, "m": current_raw['m'] or 0}
                },
                "ardebt": {
                    "total": {"n": ardebt_tgt['n'] or 0, "v": ardebt_tgt['v'] or 0, "m": ardebt_tgt['m'] or 0},
                    "bayar": {"n": ardebt_paid['n'] or 0, "v": ardebt_paid['v'] or 0, "m": ardebt_paid['m'] or 0},
                    "sisa":  {"n": (ardebt_tgt['n'] or 0) - (ardebt_paid['n'] or 0), "v": (ardebt_tgt['v'] or 0) - (ardebt_paid['v'] or 0), "m": (ardebt_tgt['m'] or 0) - (ardebt_paid['m'] or 0)}
                },
                "prioritas": {
                    "total": {"n": prio_raw['t_n'] or 0, "v": prio_raw['t_v'] or 0, "m": prio_raw['t_m'] or 0},
                    "bayar": {"n": prio_raw['b_n'] or 0, "v": prio_raw['b_v'] or 0, "m": prio_raw['b_m'] or 0},
                    "sisa":  {"n": (prio_raw['t_n'] or 0) - (prio_raw['b_n'] or 0), "v": (prio_raw['t_v'] or 0) - (prio_raw['b_v'] or 0), "m": (prio_raw['t_m'] or 0) - (prio_raw['b_m'] or 0)}
                },
                "anomali": {"ekstrem": count_eks, "drop": count_drp}
            },
            "analytics": {
                "pcez_stats": [dict(row) for row in res_pcez],
                "sync_ts": datetime.now().isoformat()
            },
            "logs": [dict(row) for row in db.execute("SELECT nomen, petugas_name, keterangan, created_at FROM kunjungan_petugas WHERE periode = ? ORDER BY created_at DESC LIMIT 5", (periode,)).fetchall()]
        })

    except Exception as e:
        current_app.logger.error(f"Integrity Dashboard Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@dashboard_bp.route('/admin/system-logs', methods=['GET'])
def get_system_logs():
    db = get_db_connection()
    try:
        logs = db.execute("SELECT * FROM system_logs ORDER BY created_at DESC LIMIT 50").fetchall()
        return jsonify({"status": "success", "data": [dict(row) for row in logs]})
    except:
        return jsonify({"status": "error", "message": "Logs table not ready"}), 200
    finally:
        db.close()
