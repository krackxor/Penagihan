"""
PCEZ Performance API - Sunter Dashboard Pro (V8.3 Sinergi Edition)
Sinergi & Smart Update:
1. Autopilot Transition: Deteksi periode otomatis untuk masa transisi data.
2. Database Trigger Sync: Memanfaatkan status_lunas otomatis untuk akurasi 100%.
3. Real-time Undue & Current: Pemisahan pembayaran kantor dan lapangan yang presisi.
4. Access Intelligence: Filter dinamis berdasarkan role (Admin Global vs Petugas Personal).
"""

from flask import jsonify, request, session
from datetime import datetime

def register_pcez_routes(app, get_db):
    
    def get_autopilot_periode(db):
        """Mencari periode terakhir yang tersedia di database."""
        row = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
        return row['periode'] if row else datetime.now().strftime('%m-%Y')

    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Dashboard Intelijen: Statistik target vs realisasi."""
        try:
            db = get_db()
            
            # --- 1. IDENTIFIKASI LOGIN & LEVEL AKSES ---
            user_role = str(session.get('role', 'publik')).lower()
            user_petugas_id = session.get('petugas_id') 
            
            # --- 2. PENGATURAN PERIODE (SMART AUTOPILOT) ---
            req_periode = request.args.get('periode') or get_autopilot_periode(db)

            # --- 3. LOGIKA SMART FILTERING ---
            target_filter = ""
            params_global = [req_periode, req_periode, req_periode]

            if user_role == 'petugas':
                target_filter = " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
                params_global = [req_periode, user_petugas_id, req_periode, user_petugas_id, req_periode, user_petugas_id]

            # --- 4. QUERY GLOBAL DASHBOARD (TRIGGER SYNC V8.3) ---
            # Mengambil data langsung dari kolom status_lunas hasil trigger database
            global_query = f"""
                SELECT 
                    COUNT(*) as total_nomen_mc,
                    SUM(nominal) as total_nominal_mc,
                    SUM(CASE WHEN status_lunas = 1 THEN 1 ELSE 0 END) as total_lunas_mc,
                    SUM(CASE WHEN status_lunas = 1 THEN nominal ELSE 0 END) as nom_terbayar,
                    (SELECT COUNT(*) FROM master_bayar WHERE periode = ? {target_filter}) as count_undue,
                    (SELECT COUNT(*) FROM collection_harian WHERE periode = ? {target_filter}) as count_current
                FROM master_pelanggan 
                WHERE periode = ? {target_filter}
            """
            
            # --- 5. QUERY RANKING & PERFORMA PETUGAS ---
            officer_ranking_query = """
                SELECT 
                    COALESCE(r.petugas, k.petugas_name, 'Umum') as petugas,
                    COUNT(*) as total_dijalan,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN 1 ELSE 0 END) as jml_bayar,
                    SUM(CASE WHEN k.keterangan LIKE '%Janji%' THEN 1 ELSE 0 END) as jml_janji,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) ELSE 0 END) as total_nominal
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan mp ON k.nomen = mp.nomen AND k.periode = mp.periode
                LEFT JOIN rute_petugas r ON mp.pcez = r.pcez
                WHERE k.periode = ?
            """
            
            rank_params = [req_periode]
            if user_role == 'petugas':
                officer_ranking_query += " AND (r.petugas = ? OR k.petugas_name = ?)"
                rank_params.extend([user_petugas_id, user_petugas_id])

            officer_ranking_query += " GROUP BY petugas ORDER BY total_nominal DESC"

            # --- 6. EKSEKUSI DATA ---
            g_stat = db.execute(global_query, params_global).fetchone()
            o_rank = db.execute(officer_ranking_query, rank_params).fetchall()
            
            # --- 7. LOG AKTIVITAS LIVE FEED ---
            log_q = f"""
                SELECT strftime('%H:%M', k.created_at) as waktu, 
                       k.nomen, mp.nama, k.keterangan, 
                       COALESCE(r.petugas, k.petugas_name) as petugas,
                       (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) as nominal
                FROM kunjungan_petugas k 
                LEFT JOIN master_pelanggan mp ON k.nomen = mp.nomen AND k.periode = mp.periode
                LEFT JOIN rute_petugas r ON mp.pcez = r.pcez 
                WHERE k.periode = ?
            """
            log_params = [req_periode]
            if user_role == 'petugas':
                log_q += " AND (r.petugas = ? OR k.petugas_name = ?)"
                log_params.extend([user_petugas_id, user_petugas_id])
            
            l_recent = db.execute(log_q + " ORDER BY k.created_at DESC LIMIT 10", log_params).fetchall()
            
            # --- 8. FINAL DATA MAPPING ---
            res_global = dict(g_stat) if g_stat else {}
            res_global['sisa_nomen'] = max(0, res_global.get('total_nomen_mc', 0) - res_global.get('total_lunas_mc', 0))

            return jsonify({
                "status": "success",
                "active_periode": req_periode,
                "global": res_global,
                "officers": [dict(row) for row in o_rank],
                "log_petugas": [dict(row) for row in l_recent],
                "role": user_role
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/reminders', methods=['GET'])
    def get_reminders():
        """Janji Bayar dengan Status Pelunasan Otomatis."""
        try:
            db = get_db()
            user_role = str(session.get('role', 'publik')).lower()
            user_petugas_id = session.get('petugas_id')
            req_periode = request.args.get('periode') or get_autopilot_periode(db)

            query = """
                SELECT 
                    k.nomen, m.nama, k.no_hp, k.janji_bayar_dt as tanggal_janji,
                    k.catatan, COALESCE(r.petugas, k.petugas_name) as petugas_name,
                    (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) as nominal,
                    CASE WHEN m.status_lunas = 1 THEN 'LUNAS' ELSE 'PENDING' END as status_bayar
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND k.periode = m.periode
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
