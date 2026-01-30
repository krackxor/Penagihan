"""
API Dashboard - Sunter Dashboard Pro (V12.79 Period Logic Fix)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Robust Column Shield: Menambahkan pengecekan keberadaan kolom 'tipe' secara 
   dinamis untuk mencegah Error 500 (no such column).
2. Target Lock Mechanism: Mengunci perhitungan TOTAL NOMEN dan TARGET NOMINAL 
   hanya pada data MC (jika kolom tersedia).
3. ✅ FIX: Period Alignment - Hapus logika N-1, langsung pakai periode untuk UNDUE
4. Strict Nomen Matching: Anti-Over Progress protection.
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

def get_latest_active_period(db):
    """Mendeteksi periode target penagihan terbaru."""
    try:
        res = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
        return res['periode'] if res else datetime.now().strftime('%m-%Y')
    except:
        return datetime.now().strftime('%m-%Y')

@dashboard_bp.route('/pusat-kendali', methods=['GET'])
def get_pusat_kendali():
    """Statistik global hasil Audit Digital untuk Dashboard Utama."""
    db = get_db_connection()
    try:
        # [1] PERIODE DETECTION
        periode = request.args.get('periode') or get_latest_active_period(db)
        user_role = str(session.get('role', 'guest')).lower()
        petugas_id = session.get('petugas_id')

        # ✅ [2] FIX PERIODE LOGIC: Hapus logika N-1
        # Karena MB bulan 11 sudah di-shift jadi periode 12-2025 saat upload,
        # kita langsung pakai periode tanpa mundur 1 bulan
        bulan_rek_target = periode.replace('-', '')  # 12-2025 → 122025

        # [3] DYNAMIC SCHEMA CHECK (Mencegah Error 'no such column: tipe')
        cursor = db.execute("PRAGMA table_info(master_pelanggan)")
        cols = [row['name'] for row in cursor.fetchall()]
        tipe_filter = "AND tipe = 'MC'" if 'tipe' in cols else ""

        # [4] SUMMARY MC & STATUS LUNAS
        query_summary = f"""
            SELECT 
                COUNT(*) as total_nomen,
                COALESCE(SUM(nominal), 0) as total_nominal,
                COALESCE(SUM(CASE WHEN status_lunas = 1 THEN 1 ELSE 0 END), 0) as lunas_nomen,
                COALESCE(SUM(CASE WHEN status_lunas = 0 THEN 1 ELSE 0 END), 0) as sisa_nomen
            FROM master_pelanggan 
            WHERE periode = ? {tipe_filter}
        """
        params_summary = [periode]
        if user_role == 'petugas' and petugas_id:
            query_summary += " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
            params_summary.append(petugas_id)

        res_summary = db.execute(query_summary, params_summary).fetchone()

        # ✅ [5] FIX REALISASI NOMINAL: Langsung filter pakai periode
        query_realisasi = f"""
            SELECT 
                (SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
                 WHERE mb.periode = ? AND mb.kategori = 'UNDUE'
                 AND mb.nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ? {tipe_filter})) as undue_nom,
                 
                (SELECT COALESCE(SUM(ch.nominal), 0) FROM collection_harian ch
                 WHERE ch.periode = ? AND ch.kategori = 'CURRENT'
                 AND ch.nomen IN (SELECT nomen FROM master_pelanggan WHERE periode = ? {tipe_filter})) as current_nom,
                 
                (SELECT COALESCE(SUM(jumlah), 0) FROM ardebt WHERE periode = ?) as total_piutang_lama
        """
        res_realisasi = db.execute(query_realisasi, (periode, periode, periode, periode, periode)).fetchone()

        # [6] LEADERBOARD
        query_leaderboard = f"""
            SELECT 
                r.petugas,
                COUNT(p.id) as target_nomen,
                SUM(p.status_lunas) as lunas_nomen,
                ROUND((CAST(SUM(p.status_lunas) AS FLOAT) / MAX(1, COUNT(p.id))) * 100, 1) as pct_nomen
            FROM rute_petugas r
            JOIN master_pelanggan p ON r.pcez = p.pcez
            WHERE p.periode = ? {tipe_filter}
            GROUP BY r.petugas 
            ORDER BY pct_nomen DESC, lunas_nomen DESC LIMIT 5
        """
        res_leaderboard = db.execute(query_leaderboard, (periode,)).fetchall()

        # [7] FINAL MAPPING
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
