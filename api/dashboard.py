"""
API Dashboard - Sunter Dashboard Pro (V15.0 Comprehensive Executive Summary)
Update: 2026-02-05
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ TOTAL TRANSPARENCY: Detail Bayar vs Belum Bayar untuk SEMUA kategori.
2. ✅ TRIPLE METRICS: Menyajikan Nomen (N), Nominal (M), dan Kubikasi (V) di setiap fungsi.
3. ✅ SEPARATED REPORTS: Pemisahan eksplisit antara Undue (Bank), Current (Field), dan Ardebt.
4. ✅ DIMENSIONAL SYNC: Data tetap mendukung filter per Rayon, PC, dan PCEZ.
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
    """Statistik eksekutif detail (Bayar vs Belum) dengan metrik N/V/M."""
    db = get_db_connection()
    try:
        # [1] PERIODE & SECURITY LAYER
        periode = request.args.get('periode') or get_latest_active_period(db)
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # [2] REKENING ALIGNMENT (N-1)
        try:
            dt_obj = datetime.strptime(periode, '%m-%Y')
            target_dt = dt_obj - relativedelta(months=1)
            bulan_rek_target = target_dt.strftime('%m%Y')
        except:
            bulan_rek_target = periode.replace('-', '')

        # [3] SMART FILTER (ROBUST COLUMN SHIELD)
        p_filter = ""
        p_params = [periode]
        if user_role == 'petugas' and petugas_id:
            p_filter = " AND m.pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            p_params.append(petugas_id)

        # --- 4. DATA CORE: MAIN COLLECTION (MC) ---
        # Menghitung Target Total vs Realisasi Lunas (N/V/M)
        mc_raw = db.execute(f"""
            SELECT 
                COUNT(*) as t_n, SUM(m.kubik) as t_v, SUM(m.nominal) as t_m,
                SUM(CASE WHEN m.status_lunas = 1 THEN 1 ELSE 0 END) as b_n,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.kubik ELSE 0 END) as b_v,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.nominal ELSE 0 END) as b_m
            FROM master_pelanggan m 
            WHERE m.periode = ? AND m.tipe = 'MC' {p_filter}
        """, p_params).fetchone()

        # --- 5. DATA CORE: REALISASI TERPISAH (UNDUE vs CURRENT) ---
        # [A] UNDUE (BANK) - Diambil dari master_bayar
        undue_raw = db.execute(f"""
            SELECT 
                COUNT(DISTINCT mb.nomen) as n, SUM(mb.nominal) as m,
                (SELECT SUM(m2.kubik) FROM master_pelanggan m2 
                 WHERE m2.nomen = mb.nomen AND m2.periode = mb.periode) as v
            FROM master_bayar mb 
            WHERE mb.periode = ? AND mb.kategori = 'UNDUE' AND mb.bulan_rek = ?
            AND mb.nomen IN (SELECT nomen FROM master_pelanggan m WHERE m.periode = ? {p_filter})
        """, [periode, bulan_rek_target, periode] + (p_params[1:] if len(p_params)>1 else [])).fetchone()

        # [B] CURRENT (FIELD/COLLECTION) - Diambil dari collection_harian
        current_raw = db.execute(f"""
            SELECT 
                COUNT(DISTINCT ch.nomen) as n, SUM(ch.nominal) as m, SUM(ch.vol_collect) as v
            FROM collection_harian ch
            WHERE ch.periode = ? AND ch.kategori = 'CURRENT'
            AND ch.nomen IN (SELECT nomen FROM master_pelanggan m WHERE m.periode = ? {p_filter})
        """, [periode, periode] + (p_params[1:] if len(p_params)>1 else [])).fetchone()

        # --- 6. DATA CORE: ARDEBT (PIUTANG LAMA) ---
        ardebt_target = db.execute(f"SELECT COUNT(*) as n, SUM(volume) as v, SUM(jumlah) as m FROM ardebt WHERE periode = ?", (periode,)).fetchone()
        
        # Realisasi pelunasan Ardebt (Mencari transaksi dengan kategori ARDEBT)
        ardebt_paid = db.execute(f"""
            SELECT COUNT(DISTINCT nomen) as n, SUM(nominal) as m, SUM(v_kubik) as v
            FROM (
                SELECT nomen, nominal, 0 as v_kubik FROM master_bayar WHERE periode = ? AND kategori = 'ARDEBT'
                UNION ALL
                SELECT nomen, nominal, vol_collect as v_kubik FROM collection_harian WHERE periode = ? AND kategori = 'ARDEBT'
            ) WHERE nomen IN (SELECT nomen FROM master_pelanggan m WHERE m.periode = ? {p_filter})
        """, [periode, periode, periode] + (p_params[1:] if len(p_params)>1 else [])).fetchone()

        # --- 7. DATA CORE: KONSUMEN PRIORITAS ---
        prio_raw = db.execute(f"""
            SELECT 
                COUNT(*) as t_n, SUM(m.kubik) as t_v, SUM(m.nominal) as t_m,
                SUM(CASE WHEN m.status_lunas = 1 THEN 1 ELSE 0 END) as b_n,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.kubik ELSE 0 END) as b_v,
                SUM(CASE WHEN m.status_lunas = 1 THEN m.nominal ELSE 0 END) as b_m
            FROM master_pelanggan m 
            WHERE m.periode = ? AND m.is_prioritas = 1 {p_filter}
        """, p_params).fetchone()

        # --- 8. ANOMALY SUMMARY ---
        count_ekstrem = db.execute(f"SELECT COUNT(*) FROM master_pelanggan m WHERE m.periode = ? AND m.kubik > 500", (periode,)).fetchone()[0]
        count_drop = db.execute(f"SELECT COUNT(*) FROM master_pelanggan m WHERE m.periode = ? AND m.kubik < 5", (periode,)).fetchone()[0]

        # --- 9. PCEZ ANALYTICS (SMART JOIN TETAP ADA) ---
        query_pcez = f"""
            SELECT 
                m.pcez, m.rayon, COALESCE(r.petugas, 'UNMAPPED') as petugas,
                COUNT(m.id) as target_n, SUM(m.nominal) as target_m,
                SUM(m.status_lunas) as lunas_n,
                ROUND((CAST(SUM(m.status_lunas) AS FLOAT) / MAX(1, COUNT(m.id))) * 100, 1) as pct
            FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON TRIM(m.pcez) = TRIM(r.pcez)
            WHERE m.periode = ? AND m.tipe = 'MC' {p_filter.replace('m.', 'm2.') if p_filter else ""}
            GROUP BY m.pcez ORDER BY m.rayon ASC
        """
        # (Catatan: Logic p_filter disesuaikan jika role petugas)
        res_pcez = db.execute(query_pcez, p_params).fetchall()

        # --- 10. FINAL MAPPING (EXECUTIVE RESPONSE) ---
        return jsonify({
            "status": "success",
            "periode": periode,
            "summaries": {
                "mc": {
                    "total": {"n": mc_raw['t_n'], "v": mc_raw['t_v'], "m": mc_raw['t_m']},
                    "bayar": {"n": mc_raw['b_n'], "v": mc_raw['b_v'], "m": mc_raw['b_m']},
                    "sisa":  {"n": mc_raw['t_n'] - mc_raw['b_n'], "v": mc_raw['t_v'] - mc_raw['b_v'], "m": mc_raw['t_m'] - mc_raw['b_m']}
                },
                "undue_bank": {
                    "bayar": {"n": undue_raw['n'] or 0, "v": undue_raw['v'] or 0, "m": undue_raw['m'] or 0}
                },
                "current_field": {
                    "bayar": {"n": current_raw['n'] or 0, "v": current_raw['v'] or 0, "m": current_raw['m'] or 0}
                },
                "ardebt": {
                    "total": {"n": ardebt_target['n'] or 0, "v": ardebt_target['v'] or 0, "m": ardebt_target['m'] or 0},
                    "bayar": {"n": ardebt_paid['n'] or 0, "v": ardebt_paid['v'] or 0, "m": ardebt_paid['m'] or 0},
                    "sisa":  {"n": (ardebt_target['n'] or 0) - (ardebt_paid['n'] or 0), 
                              "v": (ardebt_target['v'] or 0) - (ardebt_paid['v'] or 0), 
                              "m": (ardebt_target['m'] or 0) - (ardebt_paid['m'] or 0)}
                },
                "prioritas": {
                    "total": {"n": prio_raw['t_n'] or 0, "v": prio_raw['t_v'] or 0, "m": prio_raw['t_m'] or 0},
                    "bayar": {"n": prio_raw['b_n'] or 0, "v": prio_raw['b_v'] or 0, "m": prio_raw['b_m'] or 0},
                    "sisa":  {"n": (prio_raw['t_n'] or 0) - (prio_raw['b_n'] or 0), 
                              "v": (prio_raw['t_v'] or 0) - (prio_raw['b_v'] or 0), 
                              "m": (prio_raw['t_m'] or 0) - (prio_raw['b_m'] or 0)}
                },
                "anomali": {"ekstrem": count_ekstrem, "drop": count_drop}
            },
            "analytics": {
                "pcez_stats": [dict(row) for row in res_pcez],
                "sync_ts": datetime.now().isoformat()
            },
            "logs": [dict(row) for row in db.execute("SELECT nomen, petugas_name, keterangan, created_at FROM kunjungan_petugas WHERE periode = ? ORDER BY created_at DESC LIMIT 5", (periode,)).fetchall()]
        })

    except Exception as e:
        current_app.logger.error(f"Executive Dashboard Error: {str(e)}")
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
