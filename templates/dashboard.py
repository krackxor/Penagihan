"""
API Dashboard - Sunter Dashboard Pro (V8.0 Sinergi Edition)
Fungsi: Sumber data utama untuk templates/index.html
Logika: 
- Nomen & Nominal MC (Target Periode N+1)
- Pembayaran UNDUE (Dari Master Bayar / MB)
- Pembayaran CURRENT (Dari Collection Harian)
- Live Audit Log dari Kunjungan Petugas
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime

# Nama Blueprint disesuaikan menjadi 'dashboard'
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    if not session.get('user_id'):
        return jsonify({"message": "Sesi berakhir, silakan login kembali"}), 401

    # Ambil periode dari request (Format: MM-YYYY dari JavaScript)
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')
    user_role = str(session.get('role', 'guest')).lower()
    petugas_id = session.get('petugas_id')

    db = get_db_connection()
    try:
        # 1. QUERY SUMMARY UTAMA (Target MC)
        # Menghitung Total Nomen dan Nominal dari file MC yang sudah di-upload
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
        
        # Filter khusus jika yang login adalah petugas lapangan
        if user_role == 'petugas':
            query_summary += " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params.append(petugas_id)

        res_summary = db.execute(query_summary, params).fetchone()

        # 2. QUERY REALISASI (Undue vs Current)
        # Menangani sinkronisasi pembayaran kantor (MB) dan lapangan (Collection)
        query_realisasi = """
            SELECT 
                (SELECT SUM(nominal) FROM master_bayar WHERE periode = ?) as undue_nom,
                (SELECT SUM(nominal) FROM collection_harian WHERE periode = ?) as current_nom
        """
        res_realisasi = db.execute(query_realisasi, (periode, periode)).fetchone()

        # 3. QUERY ANALYTICS (Leaderboard Area)
        # Mengelompokkan performa berdasarkan rute petugas
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
            GROUP BY r.petugas
            ORDER BY pct_nomen DESC
        """
        res_leaderboard = db.execute(query_leaderboard, (periode,)).fetchall()

        # 4. QUERY LIVE AUDIT LOG
        # Menampilkan 10 aktivitas terbaru petugas di lapangan
        query_logs = """
            SELECT nomen, petugas_name, keterangan, created_at 
            FROM kunjungan_petugas 
            WHERE periode = ? 
            ORDER BY created_at DESC LIMIT 10
        """
        res_logs = db.execute(query_logs, (periode,)).fetchall()

        # --- SINERGI OUTPUT JSON ---
        # Data ini yang akan dibaca oleh JavaScript di index.html
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
            "analytics": {
                "leaderboard": [dict(row) for row in res_leaderboard]
            },
            "logs": [dict(row) for row in res_logs]
        })

    except Exception as e:
        print(f"❌ Dashboard API Error: {e}")
        return jsonify({"message": "Gagal memuat data dashboard"}), 500
    finally:
        db.close()
