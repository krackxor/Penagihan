"""
API Dashboard - Sunter Dashboard Pro (V12.33 Robust Sync)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ARDEBT Integration: Audit piutang lama secara global.
2. System Log Route: Perbaikan Error 404 dengan menyediakan endpoint audit log.
3. N+1 Shift Alignment: Auto-detect periode terbaru dari Master Pelanggan.
4. Precision Sync: COALESCE pada SUM nominal untuk mencegah nilai null.
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

def get_latest_active_period(db):
    """Mendeteksi periode target penagihan terbaru (Hasil N+1 Upload)."""
    res = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    return res['periode'] if res else datetime.now().strftime('%m-%Y')

# ==========================================
# 1. ENDPOINT PUSAT KENDALI (STATISTIK)
# ==========================================
@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    """Statistik global hasil Audit Digital untuk Dashboard Utama."""
    db = get_db_connection()
    try:
        # [1] PERIODE DETECTION
        periode = request.args.get('periode') or get_latest_active_period(db)
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # [2] SUMMARY MC (TARGET BULAN BERJALAN)
        query_summary = """
            SELECT 
                COUNT(*) as total_nomen,
                COALESCE(SUM(nominal), 0) as total_nominal,
                COALESCE(SUM(CASE WHEN status_lunas = 1 THEN 1 ELSE 0 END), 0) as lunas_nomen,
                COALESCE(SUM(CASE WHEN status_lunas = 0 THEN 1 ELSE 0 END), 0) as sisa_nomen
            FROM master_pelanggan 
            WHERE periode = ?
        """
        params = [periode]
        if user_role == 'petugas' and petugas_id:
            query_summary += " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params.append(petugas_id)

        res_summary = db.execute(query_summary, params).fetchone()

        # [3] REALISASI & ARDEBT (RECOVERY)
        query_realisasi = """
            SELECT 
                (SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
                 WHERE periode = ? AND kategori IN ('UNDUE', 'HISTORY')) as undue_nom,
                (SELECT COALESCE(SUM(nominal), 0) FROM collection_harian 
                 WHERE periode = ? AND kategori IN ('CURRENT', 'HISTORY')) as current_nom,
                (SELECT COALESCE(SUM(jumlah), 0) FROM ardebt) as total_piutang_lama
        """
        res_realisasi = db.execute(query_realisasi, (periode, periode)).fetchone()

        # [4] SMART LEADERBOARD (KPI PETUGAS)
        query_leaderboard = """
            SELECT 
                r.petugas,
                COUNT(p.id) as target_nomen,
                SUM(p.status_lunas) as lunas_nomen,
                ROUND((CAST(SUM(p.status_lunas) AS FLOAT) / MAX(1, COUNT(p.id))) * 100, 1) as pct_nomen
            FROM rute_petugas r
            JOIN master_pelanggan p ON r.pcez = p.pcez
            WHERE p.periode = ?
            GROUP BY r.petugas 
            ORDER BY pct_nomen DESC, lunas_nomen DESC LIMIT 5
        """
        res_leaderboard = db.execute(query_leaderboard, (periode,)).fetchall()

        # [5] FINAL CALCULATION
        total_mc = res_summary['total_nominal'] or 0
        total_undue = res_realisasi['undue_nom'] or 0
        total_current = res_realisasi['current_nom'] or 0
        piutang_lama = res_realisasi['total_piutang_lama'] or 0
        
        realisasi_gabungan = total_undue + total_current

        return jsonify({
            "status": "success",
            "summary": {
                "periode_aktif": periode,
                "nomen": {
                    "total": res_summary['total_nomen'] or 0, 
                    "bayar": res_summary['lunas_nomen'] or 0, 
                    "belum": res_summary['sisa_nomen'] or 0
                },
                "rupiah": {
                    "mc": total_mc,
                    "undue": total_undue,
                    "current": total_current,
                    "piutang_lama": piutang_lama,
                    "total_realisasi": realisasi_gabungan,
                    "sisa": max(0, total_mc - realisasi_gabungan),
                    "pct": round((realisasi_gabungan / max(1, total_mc) * 100), 2)
                }
            },
            "analytics": {
                "leaderboard": [dict(row) for row in res_leaderboard],
                "sync_ts": datetime.now().isoformat()
            },
            "logs": [dict(row) for row in db.execute("""
                SELECT nomen, petugas_name, keterangan, created_at 
                FROM kunjungan_petugas WHERE periode = ? 
                ORDER BY created_at DESC LIMIT 10
            """, (periode,)).fetchall()]
        })

    except Exception as e:
        current_app.logger.error(f"Dashboard Sync Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

# ==========================================
# 2. ENDPOINT SYSTEM LOGS (FIX 404)
# ==========================================
@dashboard_bp.route('/admin/system-logs', methods=['GET'])
def get_system_logs():
    """Audit Trail: Melihat jejak digital aktivitas Admin/Upload."""
    db = get_db_connection()
    try:
        logs = db.execute("""
            SELECT user_id, action, module, details, ip_address, created_at 
            FROM system_logs 
            ORDER BY created_at DESC LIMIT 50
        """).fetchall()
        
        return jsonify({
            "status": "success",
            "data": [dict(row) for row in logs]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()
