"""
API Dashboard - Sunter Dashboard Pro (V8.1 Open Access Edition)
Fungsi: Menyuplai data ke index.html baik saat login maupun guest.
Logika: Guest/Admin = Global Data, Petugas = Personal Area Data.
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    # --- FIX 1: Izinkan Guest melihat data tanpa 401 Unauthorized ---
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')
    
    # Deteksi role secara aman
    user_role = str(session.get('role', 'guest')).lower()
    petugas_id = session.get('petugas_id')

    db = get_db_connection()
    try:
        # 1. Summary MC (Master Catat)
        # --- FIX 2: Default Query Global ---
        query_summary = """
            SELECT 
                COUNT(*) as total_nomen,
                SUM(nominal) as total_nominal,
                SUM(CASE WHEN status_lunas = 1 THEN 1 ELSE 0 END) as lunas_nomen,
                SUM(CASE WHEN status_lunas = 0 THEN 1 ELSE 0 END) as sisa_nomen
            FROM master_pelanggan 
            WHERE periode = ?
        """
        params = [periode]

        # Filter area HANYA jika yang login adalah petugas
        if user_role == 'petugas' and petugas_id:
            query_summary += " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params.append(petugas_id)

        res_summary = db.execute(query_summary, params).fetchone()

        # 2. Realisasi Undue & Current
        # Logika: Undue (Kantor/MB) & Current (Lapangan/Collection)
        # Data realisasi untuk dashboard utama sebaiknya selalu global jika guest/admin
        query_realisasi = """
            SELECT 
                (SELECT SUM(nominal) FROM master_bayar WHERE periode = ?) as undue_nom,
                (SELECT SUM(nominal) FROM collection_harian WHERE periode = ?) as current_nom
        """
        res_realisasi = db.execute(query_realisasi, (periode, periode)).fetchone()

        # 3. Leaderboard (Performa Petugas)
        query_leaderboard = """
            SELECT 
                r.petugas,
                COUNT(p.id) as target_nomen,
                SUM(p.status_lunas) as lunas_nomen,
                CASE 
                    WHEN COUNT(p.id) > 0 THEN ROUND((CAST(SUM(p.status_lunas) AS FLOAT) / COUNT(p.id)) * 100, 1) 
                    ELSE 0 
                END as pct_nomen
            FROM rute_petugas r
            JOIN master_pelanggan p ON r.pcez = p.pcez
            WHERE p.periode = ?
            GROUP BY r.petugas ORDER BY pct_nomen DESC
        """
        res_leaderboard = db.execute(query_leaderboard, (periode,)).fetchall()

        # 4. Logs (Aktivitas Lapangan Terbaru)
        query_logs = """
            SELECT nomen, petugas_name, keterangan, created_at 
            FROM kunjungan_petugas WHERE periode = ? 
            ORDER BY created_at DESC LIMIT 10
        """
        res_logs = db.execute(query_logs, (periode,)).fetchall()

        # Sinkronisasi JSON Output
        return jsonify({
            "summary": {
                "nomen": {
                    "total": res_summary['total_nomen'] or 0, 
                    "bayar": res_summary['lunas_nomen'] or 0, 
                    "belum": res_summary['sisa_nomen'] or 0
                },
                "rupiah": {
                    "mc": res_summary['total_nominal'] or 0,
                    "undue": res_realisasi['undue_nom'] or 0,
                    "current": res_realisasi['current_nom'] or 0,
                    "sisa": (res_summary['total_nominal'] or 0) - 
                            ((res_realisasi['undue_nom'] or 0) + (res_realisasi['current_nom'] or 0))
                }
            },
            "analytics": {"leaderboard": [dict(row) for row in res_leaderboard]},
            "logs": [dict(row) for row in res_logs]
        })

    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        db.close()
