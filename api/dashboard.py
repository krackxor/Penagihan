"""
API Dashboard - Sunter Dashboard Pro (V12.30 Shift Logic Edition)
Update: 2026-01-19
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Shift Logic Support: Dashboard Januari (N+1) secara otomatis memetakan realisasi 
   pembayaran dari bulan Desember (N).
2. Strict UNDUE Filter: Box Bank (Undue) hanya menampilkan nominal dari Master Bayar 
   yang kategorinya murni 'UNDUE' (hasil filter BULAN_REK di upload engine).
3. Analytics Sync: Menambahkan timestamp sinkronisasi (sync_ts) untuk validasi real-time.
4. Multi-Tenant Petugas: Filter otomatis jika user yang login adalah petugas lapangan.
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

def get_latest_active_period(db):
    """Mendeteksi periode target penagihan terbaru di database (Hasil N+1 Upload)."""
    # Mencari periode terbaru berdasarkan data Master Pelanggan yang terakhir diunggah
    res = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    # Fallback ke bulan berjalan jika database kosong
    return res['periode'] if res else datetime.now().strftime('%m-%Y')

@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    """Endpoint Pusat Kendali: Statistik global dan audit realisasi digital."""
    db = get_db_connection()
    try:
        # [1] SMART PERIOD DETECTION
        # Mengunci periode agar sinkron dengan hasil deteksi otomatis saat upload.
        # Jika Anda memilih periode 01-2026, maka seluruh realisasi bank Desember masuk ke sini.
        periode = request.args.get('periode') or get_latest_active_period(db)
        
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # [2] SUMMARY MC (TARGET UTAMA PERIODE AKTIF)
        # Menghitung target nominal murni dari Master Pelanggan periode terpilih.
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

        if user_role == 'petugas' and petugas_id:
            query_summary += " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params.append(petugas_id)

        res_summary = db.execute(query_summary, params).fetchone()

        # [3] REALISASI SINERGI (AUDIT CATEGORY INTEGRATION)
        # UNDUE: Menampilkan nominal dari MB bulan N yang membayar Rekening bulan N.
        # CURRENT: Menampilkan nominal dari Collection harian bulan N+1.
        # HISTORY: Pemulihan piutang lama (Recovery).
        query_realisasi = """
            SELECT 
                (SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
                 WHERE periode = ? AND kategori = 'UNDUE') as undue_nom,
                (SELECT COALESCE(SUM(nominal), 0) FROM collection_harian 
                 WHERE periode = ? AND kategori = 'CURRENT') as current_nom,
                (SELECT COALESCE(SUM(nominal), 0) FROM master_bayar 
                 WHERE periode = ? AND kategori = 'HISTORY') as history_mb,
                (SELECT COALESCE(SUM(nominal), 0) FROM collection_harian 
                 WHERE periode = ? AND kategori = 'HISTORY') as history_coll
        """
        res_realisasi = db.execute(query_realisasi, (periode, periode, periode, periode)).fetchone()

        # [4] SMART LEADERBOARD (KPI PETUGAS)
        # Mengukur progres petugas berdasarkan area (PCEZ) yang dikelola.
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

        # [5] FINAL SYNC OUTPUT
        total_mc = res_summary['total_nominal'] or 0
        total_undue = res_realisasi['undue_nom'] or 0
        total_current = res_realisasi['current_nom'] or 0
        total_history = res_realisasi['history_mb'] + res_realisasi['history_coll']
        
        # Realisasi gabungan: Hasil kerja bank dan lapangan periode dashboard
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
                    "recovery": total_history,
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
        return jsonify({"status": "error", "message": f"Gagal memuat dashboard: {str(e)}"}), 500
    finally:
        db.close()
