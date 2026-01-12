"""
API Dashboard - Sunter Dashboard Pro (V12.16 Strict Audit Edition)
Update: 2026-01-13
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Audit Alignment: Filter kategori UNDUE, CURRENT, dan HISTORY secara spesifik.
2. N+1 Logic Sync: Mendukung pemetaan periode dashboard hasil upload cerdas.
3. Anti-Zero Recovery: Menghitung nominal HISTORY agar Box Bank tidak Rp 0.
4. Smart Route Sync: Konsistensi data petugas berdasarkan pemetaan PCEZ terbaru.
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

def get_latest_active_period(db):
    """Mendeteksi periode target penagihan terbaru di database (N+1)."""
    res = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    return res['periode'] if res else datetime.now().strftime('%m-%Y')

@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    """Endpoint Pusat Kendali: Mengelola statistik global dan audit realisasi."""
    db = get_db_connection()
    try:
        # [1] SMART PERIOD DETECTION
        # Mengunci periode dashboard agar sinkron dengan hasil deteksi N+1 di upload.
        periode = request.args.get('periode') or get_latest_active_period(db)
        
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # [2] SUMMARY MC (TARGET UTAMA PERIODE AKTIF)
        query_summary = """
            SELECT 
                COUNT(*) as total_nomen,
                COALESCE(SUM(nominal), 0) as total_nominal,
                COALESCE(SUM(CASE WHEN status_lunas = 1 THEN 1 ELSE 0 END), 0) as lunas_nomen,
                COALESCE(SUM(CASE WHEN status_lunas = 0 THEN 1 ELSE 0 END), 0) as sisa_nomen,
                COALESCE(SUM(CASE WHEN status_lunas = 1 THEN nominal ELSE 0 END), 0) as rp_lunas
            FROM master_pelanggan 
            WHERE periode = ?
        """
        params = [periode]

        # Filter area jika yang login adalah petugas.
        if user_role == 'petugas' and petugas_id:
            query_summary += " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params.append(petugas_id)

        res_summary = db.execute(query_summary, params).fetchone()

        # [3] REALISASI SINERGI (AUDIT CATEGORY)
        # Menarik data UNDUE & HISTORY untuk Bank, dan CURRENT & HISTORY untuk Lapangan.
        query_realisasi = """
            SELECT 
                (SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
                 WHERE periode = ? AND kategori IN ('UNDUE', 'HISTORY', 'ARDEBT')) as undue_nom,
                (SELECT COALESCE(SUM(nominal), 0) FROM collection_harian 
                 WHERE periode = ? AND kategori IN ('CURRENT', 'HISTORY', 'ARDEBT')) as current_nom
        """
        res_realisasi = db.execute(query_realisasi, (periode, periode)).fetchone()

        # [4] SMART LEADERBOARD (KINERJA LAPANGAN)
        query_leaderboard = """
            SELECT 
                r.petugas,
                COUNT(p.id) as target_nomen,
                SUM(p.status_lunas) as lunas_nomen,
                ROUND((CAST(SUM(p.status_lunas) AS FLOAT) / COUNT(p.id)) * 100, 1) as pct_nomen
            FROM rute_petugas r
            JOIN master_pelanggan p ON r.pcez = p.pcez
            WHERE p.periode = ?
            GROUP BY r.petugas 
            ORDER BY pct_nomen DESC LIMIT 5
        """
        res_leaderboard = db.execute(query_leaderboard, (periode,)).fetchall()

        # [5] SYNC OUTPUT UNTUK DASHBOARD UI
        total_mc = res_summary['total_nominal'] or 0
        total_undue = res_realisasi['undue_nom'] or 0
        total_current = res_realisasi['current_nom'] or 0
        
        # Kalkulasi sisa berdasarkan audit realisasi gabungan
        realisasi_gabungan = total_undue + total_current

        return jsonify({
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
                    "total_realisasi": realisasi_gabungan,
                    "sisa": max(0, total_mc - realisasi_gabungan),
                    "pct": round((realisasi_gabungan / (total_mc or 1) * 100), 2)
                }
            },
            "analytics": {"leaderboard": [dict(row) for row in res_leaderboard]},
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
