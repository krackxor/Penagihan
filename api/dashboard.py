"""
API Dashboard - Sunter Dashboard Pro (V12.99.2 Ultra Stability & Area Sync)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX RpNaN (Final): Memaksa semua output database menjadi float/int untuk 
   menghindari error kalkulasi JavaScript di frontend.
2. ✅ Stability Fix: Menjamin variabel 'undue_rek_target' selalu terdefinisi.
3. ✅ Audit Digital Area: Pemisahan realisasi ke kategori 34 & 35 secara otomatis.
4. ✅ Anti-Overflow: Filter ketat bulan_rek (N-1 untuk Undue, N untuk Current).
"""

from flask import Blueprint, jsonify, request, session, current_app
from core.database import get_db_connection
from datetime import datetime
from dateutil.relativedelta import relativedelta # Dibutuhkan untuk logika N-1 & N

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

        # ✅ [2] STRICT PERIODE LOGIC (N-1 & N Alignment) - FIX NAMEERROR & RpNaN
        try:
            dt_obj = datetime.strptime(periode, '%m-%Y')
            # Undue Target (Tagihan bulan lalu): e.g., Jan 2026 -> 122025
            undue_rek_target = (dt_obj - relativedelta(months=1)).strftime('%m%Y')
            # Current Target (Tagihan bulan berjalan): e.g., Jan 2026 -> 012026
            current_rek_target = dt_obj.strftime('%m%Y')
            bulan_rek_target = undue_rek_target
        except:
            undue_rek_target = periode.replace('-', '')
            current_rek_target = periode.replace('-', '')
            bulan_rek_target = undue_rek_target

        # [3] DYNAMIC SCHEMA CHECK
        cursor = db.execute("PRAGMA table_info(master_pelanggan)")
        cols = [row['name'] for row in cursor.fetchall()]
        tipe_filter = "AND tipe = 'MC'" if 'tipe' in cols else ""
        
        # Pengecekan kolom collection secara dinamis
        cursor_ch = db.execute("PRAGMA table_info(collection_harian)")
        ch_cols = [row['name'] for row in cursor_ch.fetchall()]
        ch_filter_col = "bulan_rek" if "bulan_rek" in ch_cols else "bill_period"

        # [4] SUMMARY MC & STATUS LUNAS (TOTAL)
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

        # ✅ [5] SPLIT AUDIT QUERY (34 & 35) - Mencegah Progress > 100%
        query_audit = f"""
            SELECT 
                -- AREA 34
                (SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan 
                 WHERE periode = ? AND pcez LIKE '34%' {tipe_filter}) as target_34,
                (SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
                 JOIN master_pelanggan mp ON mb.nomen = mp.nomen AND mp.periode = ?
                 WHERE mb.periode = ? AND mb.kategori = 'UNDUE' 
                 AND mb.bulan_rek = ? AND mp.pcez LIKE '34%') as undue_34,
                (SELECT COALESCE(SUM(ch.nominal), 0) FROM collection_harian ch
                 JOIN master_pelanggan mp ON ch.nomen = mp.nomen AND mp.periode = ?
                 WHERE ch.periode = ? AND ch.kategori = 'CURRENT' 
                 AND ch.{ch_filter_col} = ? AND mp.pcez LIKE '34%') as current_34,

                -- AREA 35
                (SELECT COALESCE(SUM(nominal), 0) FROM master_pelanggan 
                 WHERE periode = ? AND pcez LIKE '35%' {tipe_filter}) as target_35,
                (SELECT COALESCE(SUM(mb.nominal), 0) FROM master_bayar mb
                 JOIN master_pelanggan mp ON mb.nomen = mp.nomen AND mp.periode = ?
                 WHERE mb.periode = ? AND mb.kategori = 'UNDUE' 
                 AND mb.bulan_rek = ? AND mp.pcez LIKE '35%') as undue_35,
                (SELECT COALESCE(SUM(ch.nominal), 0) FROM collection_harian ch
                 JOIN master_pelanggan mp ON ch.nomen = mp.nomen AND mp.periode = ?
                 WHERE ch.periode = ? AND ch.kategori = 'CURRENT' 
                 AND ch.{ch_filter_col} = ? AND mp.pcez LIKE '35%') as current_35,
                 
                -- GLOBAL PIUTANG LAMA
                (SELECT COALESCE(SUM(jumlah), 0) FROM ardebt WHERE periode = ?) as total_piutang_lama
        """
        
        audit = db.execute(query_audit, (
            periode, periode, periode, undue_rek_target, periode, periode, current_rek_target, # Area 34
            periode, periode, periode, undue_rek_target, periode, periode, current_rek_target, # Area 35
            periode # Ardebt
        )).fetchone()

        # [6] LEADERBOARD (Fungsi Asli)
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

        # ✅ [7] FINAL CASTING & CALCULATION - MENCEGAH RpNaN
        # Memaksa semua data menjadi float untuk kalkulasi JavaScript yang aman
        total_mc = float(res_summary['total_nominal'] or 0)
        
        # Area 34
        t34 = float(audit['target_34'] or 0)
        u34 = float(audit['undue_34'] or 0)
        c34 = float(audit['current_34'] or 0)
        sum34 = u34 + c34
        
        # Area 35
        t35 = float(audit['target_35'] or 0)
        u35 = float(audit['undue_35'] or 0)
        c35 = float(audit['current_35'] or 0)
        sum35 = u35 + c35
        
        undue_total = u34 + u35
        current_total = c34 + c35
        realisasi_gabungan = undue_total + current_total

        return jsonify({
            "status": "success",
            "summary": {
                "periode_aktif": periode,
                "target_rekening": bulan_rek_target,
                "nomen": {
                    "total": int(res_summary['total_nomen'] or 0), 
                    "bayar": int(res_summary['lunas_nomen'] or 0), 
                    "belum": int(res_summary['sisa_nomen'] or 0)
                },
                "rupiah": {
                    "mc": total_mc,
                    "undue_total": undue_total,
                    "current_total": current_total,
                    "piutang_lama": float(audit['total_piutang_lama'] or 0),
                    "total_realisasi": realisasi_gabungan,
                    "pct": round((realisasi_gabungan / max(1.0, total_mc) * 100), 2)
                }
            },
            "audit_digital": {
                "area_34": {
                    "target": t34,
                    "undue": u34,
                    "current": c34,
                    "total": sum34,
                    "percent": round((sum34 / max(1.0, t34) * 100), 2)
                },
                "area_35": {
                    "target": t35,
                    "undue": u35,
                    "current": c35,
                    "total": sum35,
                    "percent": round((sum35 / max(1.0, t35) * 100), 2)
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
