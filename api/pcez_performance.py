"""
PCEZ Performance API - Sunter Dashboard Pro
Sinergi:
1. Level Akses: Petugas hanya melihat statistik pribadi, Admin melihat Global & Ranking.
2. Validasi Lunas: Sinkronisasi Pintu Ganda untuk status Janji Bayar.
3. Live Feed: Monitoring aktivitas lapangan secara real-time.
"""

from flask import jsonify, request, session
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Strategis: Target vs Realisasi dengan Filter Role."""
        try:
            db = get_db()
            today = datetime.now()
            
            # Integrasi Role & Session
            user_role = session.get('role')
            user_petugas_id = session.get('petugas_id') # Nama di Excel
            
            # --- 1. PERIODE REALISASI ---
            req_periode = request.args.get('periode') 
            target_dt = datetime.strptime(req_periode, '%m-%Y') if req_periode else today
            curr_period_str = target_dt.strftime('%m-%Y') 

            # --- 2. LOGIKA TARGET SMART (N-1) ---
            last_mc_query = db.execute("""
                SELECT periode FROM master_pelanggan 
                WHERE tipe = 'MC' 
                ORDER BY substr(periode,4,4) DESC, substr(periode,1,2) DESC 
                LIMIT 1
            """).fetchone()
            
            target_period = last_mc_query[0] if last_mc_query else (target_dt.replace(day=1) - timedelta(days=1)).strftime('%m-%Y')

            # --- 3. QUERY GLOBAL DASHBOARD ---
            # Jika Petugas, penyebut target disesuaikan dengan wilayah rutenya saja
            target_filter = ""
            target_params = [target_period] * 6
            if user_role == 'petugas':
                target_filter = " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
                target_params = [target_period, user_petugas_id, target_period, user_petugas_id, 
                                 target_period, user_petugas_id, target_period, user_petugas_id,
                                 target_period, user_petugas_id, target_period, user_petugas_id]

            global_query = f"""
                SELECT 
                    COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ? {target_filter}), 0) as total_nomen_mc,
                    COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ? {target_filter}), 0) as total_nominal_mc,
                    COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                     WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                     AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan)
                    ), 0) as nom_undue,
                    COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                     WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                     AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = m.notagihan)
                    ), 0) as nom_current,
                    COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                     WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                     AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan)
                    ), 0) as count_undue,
                    COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                     WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                     AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = m.notagihan)
                    ), 0) as count_current
            """
            
            # --- 4. QUERY RANKING / STATS PETUGAS ---
            officer_ranking_query = """
            SELECT 
                COALESCE(r.petugas, k.petugas_name, 'Petugas Umum') as petugas,
                COUNT(*) as total_dijalan,
                SUM(CASE WHEN k.keterangan LIKE '%Bayar%' AND k.keterangan NOT LIKE '%Janji%' THEN 1 ELSE 0 END) as jml_bayar,
                SUM(CASE WHEN k.keterangan LIKE '%Janji%' THEN 1 ELSE 0 END) as jml_janji,
                SUM(CASE WHEN k.keterangan LIKE '%Kosong%' OR k.keterangan LIKE '%RKS%' THEN 1 ELSE 0 END) as jml_rks,
                SUM(CASE WHEN k.keterangan LIKE '%Bayar%' AND k.keterangan NOT LIKE '%Janji%' THEN 
                    COALESCE(
                        (SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 
                        (SELECT SUM(jumlah) FROM ardebt WHERE nomen = k.nomen), 0
                    ) ELSE 0 END) as total_nominal
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan mp ON k.nomen = mp.nomen
            LEFT JOIN rute_petugas r ON mp.pcez = r.pcez
            WHERE k.periode = ?
            """
            
            if user_role == 'petugas':
                officer_ranking_query += " AND (r.petugas = ? OR k.petugas_name = ?)"
                rank_params = [curr_period_str, user_petugas_id, user_petugas_id]
            else:
                rank_params = [curr_period_str]

            officer_ranking_query += " GROUP BY petugas ORDER BY total_nominal DESC"

            # --- 5. EXECUTE ---
            g_stat = db.execute(global_query, target_params).fetchone()
            o_rank = db.execute(officer_ranking_query, rank_params).fetchall()
            
            # Live Feed (Jika petugas, hanya feed miliknya)
            log_q = "SELECT datetime(k.created_at, '+7 hours') as waktu, k.nomen, mp.nama, k.keterangan, COALESCE(r.petugas, k.petugas_name) as petugas FROM kunjungan_petugas k LEFT JOIN master_pelanggan mp ON k.nomen = mp.nomen LEFT JOIN rute_petugas r ON mp.pcez = r.pcez WHERE k.periode = ?"
            log_params = [curr_period_str]
            if user_role == 'petugas':
                log_q += " AND (r.petugas = ? OR k.petugas_name = ?)"
                log_params.extend([user_petugas_id, user_petugas_id])
            
            l_petugas = db.execute(log_q + " ORDER BY k.created_at DESC LIMIT 50", log_params).fetchall()
            
            res_global = dict(g_stat) if g_stat else {}
            res_global['total_lunas_mc'] = res_global.get('count_undue', 0) + res_global.get('count_current', 0)
            res_global['sisa_nomen'] = res_global.get('total_nomen_mc', 0) - res_global.get('total_lunas_mc', 0)

            return jsonify({
                "global": res_global,
                "officers": [dict(row) for row in o_rank],
                "log_petugas": [dict(row) for row in l_petugas],
                "role": user_role
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/reminders', methods=['GET'])
    def get_reminders():
        """Monitoring Janji Bayar dengan Filter Role"""
        try:
            db = get_db()
            user_role = session.get('role')
            user_petugas_id = session.get('petugas_id')
            
            req_periode = request.args.get('periode')
            date_filter = "strftime('%m-%Y', k.janji_bayar_dt) = ?" if req_periode else "date(k.janji_bayar_dt) = ?"
            param = req_periode if req_periode else datetime.now().strftime('%Y-%m-%d')

            query = f"""
                SELECT 
                    date(k.created_at, '+7 hours') as tanggal_jalan,
                    COALESCE(r.petugas, k.petugas_name) as petugas_name,
                    k.nomen, k.no_hp, k.janji_bayar_dt as tanggal_janji,
                    COALESCE(m.nama, 'Pelanggan') as nama,
                    k.catatan,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan) OR 
                             EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = m.notagihan)
                        THEN 'LUNAS' ELSE 'BELUM BAYAR'
                    END as status_bayar
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan m ON k.nomen = m.nomen
                LEFT JOIN rute_petugas r ON m.pcez = r.pcez
                WHERE {date_filter} AND (k.keterangan LIKE '%Janji%' OR k.catatan LIKE '%Janji%')
            """
            
            params = [param]
            if user_role == 'petugas':
                query += " AND (r.petugas = ? OR k.petugas_name = ?)"
                params.extend([user_petugas_id, user_petugas_id])

            rows = db.execute(query + " ORDER BY k.janji_bayar_dt ASC", params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
