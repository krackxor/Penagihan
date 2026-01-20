"""
API Dashboard - Sunter Dashboard Pro (V12.45 N+1 Smart Recovery)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. N+1 Smart Logic: Dashboard otomatis mencari 'bulan_rek' satu bulan sebelumnya.
2. Real-Time Efficiency: Menghitung efektivitas berdasarkan 'nomen' secara live.
3. System Log Audit: Endpoint /admin/system-logs untuk monitoring jejak upload.
4. Precision Recovery: Penggabungan live data Bank (UNDUE) & Lapangan (CURRENT).
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime, timedelta

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

        # [2] LOGIKA N+1 SMART RECOVERY
        # Konversi periode dashboard (01-2026) menjadi objek tanggal
        dt_obj = datetime.strptime(periode, '%m-%Y')
        # Mundur 1 bulan otomatis untuk mencari bulan_rek tagihan (Hasil: 122025)
        last_month = dt_obj.replace(day=1) - timedelta(days=1)
        bulan_rek_target = last_month.strftime('%m%Y')

        # [3] SUMMARY MC & STATUS LUNAS
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

        # [4] REALISASI NOMINAL (Bank vs Lapangan)
        # Undue ditarik berdasarkan bulan_rek target (N+1), Current berdasarkan periode aktif
        query_realisasi = """
            SELECT 
                (SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
                 WHERE bulan_rek = ? AND kategori = 'UNDUE') as undue_nom,
                (SELECT COALESCE(SUM(nominal), 0) FROM collection_harian 
                 WHERE periode = ? AND kategori = 'CURRENT') as current_nom,
                (SELECT COALESCE(SUM(jumlah), 0) FROM ardebt) as total_piutang_lama
        """
        res_realisasi = db.execute(query_realisasi, (bulan_rek_target, periode)).fetchone()

        # [5] SMART LEADERBOARD (KPI PETUGAS)
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

        # [6] FINAL CALCULATION
        total_mc = res_summary['total_nominal'] or 0
        total_undue = res_realisasi['undue_nom'] or 0
        total_current = res_realisasi['current_nom'] or 0
        piutang_lama = res_realisasi['total_piutang_lama'] or 0
        
        realisasi_gabungan = total_undue + total_current

        return jsonify({
            "status": "success",
            "summary": {
                "periode_aktif": periode,
                "target_rekening": bulan_rek_target,
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
        return jsonify({"status": "error", "message": f"Gagal Sinkronisasi Dashboard: {str(e)}"}), 500
    finally:
        db.close()

# ==========================================
# 2. ENDPOINT SYSTEM LOGS (AUDIT TRAIL)
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
