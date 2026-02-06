"""
PCEZ Performance API - Sunter Dashboard Pro (V9.0 Full Intelligence)
Updates:
1. Breakdown Ardebt vs Current (MC) untuk analisis kualitas bayar.
2. Deteksi Anomali (Ekstrem & Drop) untuk mitigasi risiko.
3. Ranking Wilayah (PCEZ) untuk strategi teritorial.
4. Fitur Lama (Log Aktivitas & Reminders) TETAP ADA.
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
        """Dashboard Intelijen: Statistik target vs realisasi lengkap."""
        try:
            db = get_db()
            
            # --- 1. IDENTIFIKASI LOGIN & LEVEL AKSES ---
            user_role = str(session.get('role', 'publik')).lower()
            user_petugas_id = session.get('petugas_id') 
            
            # --- 2. PENGATURAN PERIODE (SMART AUTOPILOT) ---
            req_periode = request.args.get('periode') or get_autopilot_periode(db)

            # --- 3. LOGIKA SMART FILTERING ---
            # Kita siapkan filter SQL dasar
            filter_sql = ""
            params_base = [req_periode]
            
            if user_role == 'petugas':
                filter_sql = " AND p.pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
                # Jika query join ke master_pelanggan p
                params_base.append(user_petugas_id)

            # --- 4. QUERY GLOBAL DASHBOARD (DIGABUNGKAN) ---
            
            # A. Target & Anomali (Dari Master Pelanggan)
            # Kita pakai alias 'p' agar konsisten dengan filter
            query_global_target = f"""
                SELECT 
                    COUNT(*) as total_nomen,
                    SUM(nominal) as target_total,
                    SUM(CASE WHEN kubik > 500 THEN 1 ELSE 0 END) as cnt_ekstrem,
                    SUM(CASE WHEN kubik = 0 THEN 1 ELSE 0 END) as cnt_drop
                FROM master_pelanggan p
                WHERE p.periode = ? {filter_sql}
            """
            
            # B. Realisasi Pembayaran (Dari Kunjungan - Breakdown MC vs Ardebt)
            # Filter user role harus disesuaikan karena tabel utamanya kunjungan_petugas k
            # Kita JOIN ke master_pelanggan p untuk filter pcez/rute
            query_realisasi = f"""
                SELECT 
                    SUM(COALESCE(k.mc, 0)) as realisasi_mc,
                    SUM(COALESCE(k.ardebt, 0)) as realisasi_ardebt,
                    COUNT(*) as total_transaksi
                FROM kunjungan_petugas k
                JOIN master_pelanggan p ON k.nomen = p.nomen AND k.periode = p.periode
                WHERE k.periode = ? AND k.keterangan LIKE '%Sudah%' {filter_sql}
            """
            
            # --- 5. QUERY RANKING & PERFORMA PETUGAS (DIPERLENGKAP) ---
            officer_ranking_query = f"""
                SELECT 
                    COALESCE(r.petugas, k.petugas_name, 'Umum') as petugas,
                    COUNT(k.id) as total_visit,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN 1 ELSE 0 END) as jml_bayar,
                    SUM(CASE WHEN k.keterangan LIKE '%Janji%' THEN 1 ELSE 0 END) as jml_janji,
                    -- Breakdown Nominal
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN COALESCE(k.mc, 0) ELSE 0 END) as total_mc,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN COALESCE(k.ardebt, 0) ELSE 0 END) as total_ardebt,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) ELSE 0 END) as total_nominal
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan p ON k.nomen = p.nomen AND k.periode = p.periode
                LEFT JOIN rute_petugas r ON p.pcez = r.pcez
                WHERE k.periode = ? {filter_sql}
                GROUP BY petugas 
                ORDER BY total_nominal DESC
            """
            
            # --- 6. STATISTIK WILAYAH (PCEZ) - FITUR BARU ---
            query_pcez = f"""
                SELECT 
                    p.pcez,
                    COUNT(p.nomen) as pop_nomen,
                    SUM(p.nominal) as target_area,
                    SUM(CASE WHEN p.status_lunas=1 THEN p.nominal ELSE 0 END) as realisasi_area
                FROM master_pelanggan p
                WHERE p.periode = ? {filter_sql}
                GROUP BY p.pcez
                ORDER BY realisasi_area DESC
            """

            # --- 7. LOG AKTIVITAS (TETAP ADA) ---
            log_q = f"""
                SELECT strftime('%H:%M', k.created_at) as waktu, 
                       k.nomen, p.nama, k.keterangan, 
                       COALESCE(r.petugas, k.petugas_name) as petugas,
                       (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) as nominal
                FROM kunjungan_petugas k 
                LEFT JOIN master_pelanggan p ON k.nomen = p.nomen AND k.periode = p.periode
                LEFT JOIN rute_petugas r ON p.pcez = r.pcez 
                WHERE k.periode = ? {filter_sql}
                ORDER BY k.created_at DESC LIMIT 10
            """

            # --- EKSEKUSI DATA ---
            # Kita gunakan params_base yang sudah disiapkan di awal
            g_target = db.execute(query_global_target, params_base).fetchone()
            g_real = db.execute(query_realisasi, params_base).fetchone()
            officers = db.execute(officer_ranking_query, params_base).fetchall()
            pcez_stats = db.execute(query_pcez, params_base).fetchall()
            l_recent = db.execute(log_q, params_base).fetchall()

            # --- GABUNG DATA GLOBAL ---
            # Menggabungkan hasil query target dan realisasi
            res_global = {
                "total_nomen": g_target['total_nomen'] or 0,
                "target_total": g_target['target_total'] or 0,
                "cnt_ekstrem": g_target['cnt_ekstrem'] or 0,
                "cnt_drop": g_target['cnt_drop'] or 0,
                "real_mc": g_real['realisasi_mc'] or 0,
                "real_ardebt": g_real['realisasi_ardebt'] or 0,
                "total_bayar": (g_real['realisasi_mc'] or 0) + (g_real['realisasi_ardebt'] or 0)
            }

            return jsonify({
                "status": "success",
                "active_periode": req_periode,
                "global": res_global,
                "officers": [dict(row) for row in officers],
                "pcez_rank": [dict(row) for row in pcez_stats], # Baru
                "log_petugas": [dict(row) for row in l_recent], # Tetap Ada
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
