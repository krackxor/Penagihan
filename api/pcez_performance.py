from flask import jsonify, request
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Dashboard Utama dengan Logika Periode Dinamis"""
        try:
            db = get_db()
            
            # --- LOGIKA PERIODE DINAMIS ---
            today = datetime.now()
            # Periode berjalan (n) untuk filter Collection: "2026-01"
            curr_month_sql = today.strftime('%Y-%m')
            # Periode rek bulan lalu (n-1) untuk filter MB: "202511"
            last_month_date = today.replace(day=1) - timedelta(days=1)
            period_mb_filter = last_month_date.strftime('%Y%m')

            # Query Global: Menghitung target MC dan realisasi lunas (Undue + Current)
            global_query = f"""
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC'), 0) as total_nomen_mc,
                COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC'), 0) as total_nominal_mc,
                COALESCE((SELECT COUNT(DISTINCT m.nomen) 
                 FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' 
                 AND (
                    -- Kondisi Undue: Ada di MB pada periode n-1
                    EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = m.nomen AND mb.tgl_bayar LIKE '%{period_mb_filter}%')
                    OR 
                    -- Kondisi Current: Ada di Collection pada bulan berjalan
                    EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen AND c.updated_at LIKE '{curr_month_sql}%')
                 )), 0) as total_lunas_mc
            """
            
            # Query Officer: Menghitung kinerja harian (today) dan bulanan (total)
            officer_query = """
            SELECT 
                petugas_name as petugas,
                SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
                COUNT(*) as bulanan
            FROM kunjungan_petugas
            WHERE petugas_name IS NOT NULL
            GROUP BY petugas_name
            ORDER BY bulanan DESC
            """

            # Query History: Detail aktivitas harian dengan breakdown status
            history_query = """
            SELECT 
                date(k.created_at) as tanggal,
                k.petugas_name as petugas,
                COUNT(*) as total,
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) as jml_bayar,
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN 1 ELSE 0 END) as jml_janji,
                SUM(CASE WHEN k.keterangan LIKE 'RKS%' THEN 1 ELSE 0 END) as jml_rks,
                COALESCE(SUM(m.nominal), 0) as nom_bayar
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen
            GROUP BY tanggal, petugas
            ORDER BY tanggal DESC LIMIT 20
            """

            g_stat = db.execute(global_query).fetchone()
            o_stat = db.execute(officer_query).fetchall()
            h_stat = db.execute(history_query).fetchall()
            
            res_global = dict(g_stat) if g_stat else {
                "total_nomen_mc": 0, 
                "total_nominal_mc": 0, 
                "total_lunas_mc": 0
            }
            
            # Perhitungan sisa target (Target MC - Sudah Lunas)
            res_global['sisa_target'] = res_global['total_nomen_mc'] - res_global['total_lunas_mc']

            return jsonify({
                "global": res_global,
                "officers": [dict(row) for row in o_stat],
                "history": [dict(row) for row in h_stat]
            })
        except Exception as e:
            print(f"Error Performance API: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/stats-global', methods=['GET'])
    def get_stats_global():
        """Statistik ringkas untuk halaman Performa Tim"""
        try:
            db = get_db()
            today = datetime.now()
            curr_month_sql = today.strftime('%Y-%m')
            last_month_date = today.replace(day=1) - timedelta(days=1)
            period_mb_filter = last_month_date.strftime('%Y%m')

            query = f"""
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC'), 0) as total_pelanggan,
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND (
                    EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = m.nomen AND mb.tgl_bayar LIKE '%{period_mb_filter}%') OR 
                    EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen AND c.updated_at LIKE '{curr_month_sql}%')
                 )), 0) as bayar_bulan_ini
            """
            return jsonify(dict(db.execute(query).fetchone()))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        """Leaderboard persentase kesuksesan penagihan per petugas"""
        try:
            db = get_db()
            query = """
            SELECT 
                petugas_name as petugas,
                COUNT(*) as total_dikunjungi,
                ROUND(CAST(SUM(CASE WHEN keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) as performa
            FROM kunjungan_petugas
            WHERE petugas_name IS NOT NULL
            GROUP BY petugas_name
            ORDER BY performa DESC
            """
            return jsonify([dict(row) for row in db.execute(query).fetchall()])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
