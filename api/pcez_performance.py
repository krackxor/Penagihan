"""
PCEZ Performance API - Sunter Dashboard Pro
Sinergi & Smart Update:
1. Smart Casting: Normalisasi otomatis tipe data NOMEN (Text/Numeric) saat JOIN.
2. Dual-Path Validation: Verifikasi pelunasan via Master Bayar (MB) DAN Collection Harian.
3. Geo-Performance Mapping: Filter dinamis rute petugas yang diselaraskan dengan session.
"""

from flask import jsonify, request, session
from datetime import datetime

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Dashboard Intelijen: Statistik Global & Personal dengan Smart Casting."""
        try:
            db = get_db()
            today = datetime.now()
            
            # Identifikasi Sinergi Login & Role
            user_role = str(session.get('role', 'publik')).lower()
            user_petugas_id = session.get('petugas_id') 
            
            # --- 1. SETTING PERIODE ---
            req_periode = request.args.get('periode')
            if not req_periode:
                req_periode = today.strftime('%m-%Y')

            # --- 2. QUERY GLOBAL DASHBOARD (SMART SYNC) ---
            target_filter = ""
            params_global = []

            # SMART LOGIC: Petugas dikunci ke rute mereka, Admin/Guest melihat totalitas
            if user_role == 'petugas':
                target_filter = " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
                # Terdapat 5 sub-query, masing-masing membutuhkan (periode, user_petugas_id)
                for _ in range(5):
                    params_global.extend([req_periode, user_petugas_id])
            else:
                params_global = [req_periode] * 5

            # Menggunakan CAST(nomen AS TEXT) untuk menjamin sinergi jika Excel berubah jadi format ilmiah
            global_query = f"""
                SELECT 
                    COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ? {target_filter}), 0) as total_nomen_mc,
                    COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ? {target_filter}), 0) as total_nominal_mc,
                    COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                        WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                        AND (
                            EXISTS (SELECT 1 FROM master_bayar mb WHERE CAST(mb.nomen AS TEXT) = CAST(m.nomen AS TEXT))
                            OR EXISTS (SELECT 1 FROM collection_harian c WHERE CAST(c.notag AS TEXT) = CAST(m.notagihan AS TEXT))
                        )
                    ), 0) as nom_terbayar,
                    COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                        WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                        AND EXISTS (SELECT 1 FROM master_bayar mb WHERE CAST(mb.nomen AS TEXT) = CAST(m.nomen AS TEXT))
                    ), 0) as count_undue,
                    COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                        WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                        AND EXISTS (SELECT 1 FROM collection_harian c WHERE CAST(c.notag AS TEXT) = CAST(m.notagihan AS TEXT))
                    ), 0) as count_current
            """
            
            # --- 3. QUERY RANKING & GEO-EFFICIENCY ---
            officer_ranking_query = """
                SELECT 
                    COALESCE(r.petugas, k.petugas_name, 'Petugas Umum') as petugas,
                    COUNT(*) as total_dijalan,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN 1 ELSE 0 END) as jml_bayar,
                    SUM(CASE WHEN k.keterangan LIKE '%Janji%' THEN 1 ELSE 0 END) as jml_janji,
                    SUM(CASE WHEN k.keterangan LIKE '%Kosong%' THEN 1 ELSE 0 END) as jml_rks,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) ELSE 0 END) as total_nominal
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan mp ON CAST(k.nomen AS TEXT) = CAST(mp.nomen AS TEXT)
                LEFT JOIN rute_petugas r ON mp.pcez = r.pcez
                WHERE k.periode = ?
            """
            
            rank_params = [req_periode]
            if user_role == 'petugas':
                officer_ranking_query += " AND (r.petugas = ? OR k.petugas_name = ?)"
                rank_params.extend([user_petugas_id, user_petugas_id])

            officer_ranking_query += " GROUP BY petugas ORDER BY total_nominal DESC"

            # --- 4. EXECUTION & LOG DATA ---
            g_stat = db.execute(global_query, params_global).fetchone()
            o_rank = db.execute(officer_ranking_query, rank_params).fetchall()
            
            log_q = """
                SELECT strftime('%H:%M', k.created_at, '+7 hours') as waktu, 
                       k.nomen, mp.nama, k.keterangan, 
                       COALESCE(r.petugas, k.petugas_name) as petugas,
                       (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) as nominal
                FROM kunjungan_petugas k 
                LEFT JOIN master_pelanggan mp ON CAST(k.nomen AS TEXT) = CAST(mp.nomen AS TEXT)
                LEFT JOIN rute_petugas r ON mp.pcez = r.pcez 
                WHERE k.periode = ?
            """
            log_params = [req_periode]
            if user_role == 'petugas':
                log_q += " AND (r.petugas = ? OR k.petugas_name = ?)"
                log_params.extend([user_petugas_id, user_petugas_id])
            
            l_recent = db.execute(log_q + " ORDER BY k.created_at DESC LIMIT 10", log_params).fetchall()
            
            # --- 5. SMART DATA CALCULATION ---
            res_global = dict(g_stat) if g_stat else {}
            # Sinergi Total Lunas: Gabungan Pintu MB dan Pintu Collection
            res_global['total_lunas_mc'] = res_global.get('count_undue', 0) + res_global.get('count_current', 0)
            res_global['sisa_nomen'] = max(0, res_global.get('total_nomen_mc', 0) - res_global.get('total_lunas_mc', 0))

            return jsonify({
                "status": "success",
                "global": res_global,
                "officers": [dict(row) for row in o_rank],
                "log_petugas": [dict(row) for row in l_recent],
                "role": user_role
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/reminders', methods=['GET'])
    def get_reminders():
        """Janji Bayar dengan Smart Verification terhadap status pelunasan real-time."""
        try:
            db = get_db()
            user_role = str(session.get('role', 'publik')).lower()
            user_petugas_id = session.get('petugas_id')
            req_periode = request.args.get('periode')

            query = """
                SELECT 
                    k.nomen, m.nama, k.no_hp, k.janji_bayar_dt as tanggal_janji,
                    k.catatan, COALESCE(r.petugas, k.petugas_name) as petugas_name,
                    (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) as nominal,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM master_bayar mb WHERE CAST(mb.nomen AS TEXT) = CAST(m.nomen AS TEXT)) OR 
                             EXISTS (SELECT 1 FROM collection_harian c WHERE CAST(c.notag AS TEXT) = CAST(m.notagihan AS TEXT))
                        THEN 'LUNAS' ELSE 'PENDING'
                    END as status_bayar
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan m ON CAST(k.nomen AS TEXT) = CAST(m.nomen AS TEXT)
                LEFT JOIN rute_petugas r ON m.pcez = r.pcez
                WHERE k.periode = ? AND k.keterangan LIKE '%Janji%'
            """
            
            params = [req_periode]
            if user_role == 'petugas':
                query += " AND (r.petugas = ? OR k.petugas_name = ?)"
                params.extend([user_petugas_id, user_petugas_id])

            rows = db.execute(query + " ORDER BY k.janji_bayar_dt ASC", params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
