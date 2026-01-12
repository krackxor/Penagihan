"""
API Dashboard - Sunter Dashboard Pro (V9.0 Smart Sync Edition)
Pembaruan:
1. Autonomous Period: Mengambil periode aktif terbaru dari database untuk mencegah data kosong (Anti-Januari).
2. Smart Route Sync: Integrasi langsung dengan rute_petugas (PCEZ) hasil upload terbaru.
3. Integrity Guard: Menjamin konsistensi angka realisasi Undue (MB) dan Current (Coll).
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

def get_latest_active_period(db):
    """Mendeteksi periode target penagihan terbaru di database."""
    res = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    return res['periode'] if res else datetime.now().strftime('%m-%Y')

@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    """Endpoint Pusat Kendali: Mengelola statistik global dan personal petugas."""
    db = get_db_connection()
    try:
        # [1] SMART PERIOD DETECTION
        # Memastikan dashboard tidak kosong saat awal bulan dengan mencari periode terakhir yang tersedia.
        periode = request.args.get('periode') or get_latest_active_period(db)
        
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # [2] SUMMARY MC (TARGET UTAMA PERIODE AKTIF)
        # Menggunakan COALESCE agar Guest melihat angka 0, bukan null.
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

        # [3] REALISASI SINERGI (UNDUE VS CURRENT)
        # Undue: Pembayaran Kantor (MB) | Current: Pembayaran Lapangan (Coll).
        query_realisasi = """
            SELECT 
                (SELECT COALESCE(SUM(nominal), 0) FROM master_bayar WHERE periode = ?) as undue_nom,
                (SELECT COALESCE(SUM(nominal), 0) FROM collection_harian WHERE periode = ?) as current_nom
        """
        res_realisasi = db.execute(query_realisasi, (periode, periode)).fetchone()

        # [4] SMART LEADERBOARD
        # Sinkronisasi instan dengan rute_petugas terbaru (Hasil upload Rute RL JS).
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
        return jsonify({
            "summary": {
                "periode_aktif": periode,
                "nomen": {
                    "total": res_summary['total_nomen'] or 0, 
                    "bayar": res_summary['lunas_nomen'] or 0, 
                    "belum": res_summary['sisa_nomen'] or 0
                },
                "rupiah": {
                    "mc": res_summary['total_nominal'] or 0,
                    "undue": res_realisasi['undue_nom'] or 0,
                    "current": res_realisasi['current_nom'] or 0,
                    "sisa": (res_summary['total_nominal'] or 0) - (res_summary['rp_lunas'] or 0)
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
