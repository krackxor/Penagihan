from flask import jsonify, request
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Dashboard Utama dengan Logika Multi-Periode Dinamis"""
        try:
            db = get_db()
            
            # --- LOGIKA PERIODE DINAMIS ---
            # Mengambil parameter periode dari request (Format: MM-YYYY), default bulan berjalan
            req_periode = request.args.get('periode')
            today = datetime.now()
            
            if req_periode:
                try:
                    target_dt = datetime.strptime(req_periode, '%m-%Y')
                except:
                    target_dt = today
            else:
                target_dt = today

            # Periode n (Current): "2026-01"
            curr_month_sql = target_dt.strftime('%Y-%m')
            # Periode n-1 (Undue): "202511"
            last_month_dt = target_dt.replace(day=1) - timedelta(days=1)
            period_mb_filter = last_month_dt.strftime('%Y%m')
            # Periode MC yang dicari: "12-2025" (n-1 sesuai SOP)
            target_mc_periode = last_month_dt.strftime('%m-%Y')

            # Query Global: Target MC (n-1) vs Realisasi (Undue n-1 + Current n)
            global_query = f"""
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{target_mc_periode}'), 0) as total_nomen_mc,
                COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{target_mc_periode}'), 0) as total_nominal_mc,
                COALESCE((SELECT COUNT(DISTINCT m.nomen) 
                 FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{target_mc_periode}'
                 AND (
                    -- Kondisi Undue: Ada di MB pada periode rek n-1
                    EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = m.nomen AND mb.periode = '{period_mb_filter}')
                    OR 
                    -- Kondisi Current: Ada di Collection pada bulan berjalan n
                    EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen AND c.periode = '{curr_month_sql}')
                 )), 0) as total_lunas_mc
            """
            
            # Query Officer: Berdasarkan periode kunjungan yang dipilih
            officer_query = f"""
            SELECT 
                petugas_name as petugas,
                SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
                COUNT(*) as bulanan
            FROM kunjungan_petugas
            WHERE petugas_name IS NOT NULL AND periode = '{target_dt.strftime('%m-%Y')}'
            GROUP BY petugas_name
            ORDER BY bulanan DESC
            """

            # Query History: Menampilkan riwayat kunjungan pada periode tersebut
            history_query = f"""
            SELECT 
                date(k.created_at) as tanggal,
                k.petugas_name as petugas,
                COUNT(*) as total,
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) as jml_bayar,
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN 1 ELSE 0 END) as jml_janji,
                SUM(CASE WHEN k.keterangan LIKE 'RKS%' THEN 1 ELSE 0 END) as jml_rks,
                COALESCE(SUM(m.nominal), 0) as nom_bayar
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.periode = '{target_mc_periode}'
            WHERE k.periode = '{target_dt.strftime('%m-%Y')}'
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
            
            res_global['sisa_target'] = res_global['total_nomen_mc'] - res_global['total_lunas_mc']

            return jsonify({
                "global": res_global,
                "officers": [dict(row) for row in o_stat],
                "history": [dict(row) for row in h_stat],
                "active_period": target_dt.strftime('%m-%Y')
            })
        except Exception as e:
            print(f"Error Performance API: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/stats-global', methods=['GET'])
    def get_stats_global():
        """Statistik ringkas per periode untuk halaman Performa Tim"""
        try:
            db = get_db()
            req_periode = request.args.get('periode')
            today = datetime.now()
            target_dt = datetime.strptime(req_periode, '%m-%Y') if req_periode else today

            curr_month_sql = target_dt.strftime('%Y-%m')
            last_month_dt = target_dt.replace(day=1) - timedelta(days=1)
            period_mb_filter = last_month_dt.strftime('%Y%m')
            target_mc_periode = last_month_dt.strftime('%m-%Y')

            query = f"""
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{target_mc_periode}'), 0) as total_pelanggan,
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{target_mc_periode}' AND (
                    EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = m.nomen AND mb.periode = '{period_mb_filter}') OR 
                    EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen AND c.periode = '{curr_month_sql}')
                 )), 0) as bayar_bulan_ini
            """
            return jsonify(dict(db.execute(query).fetchone()))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        """Leaderboard persentase performa per periode"""
        try:
            db = get_db()
            req_periode = request.args.get('periode')
            target_period = req_periode if req_periode else datetime.now().strftime('%m-%Y')

            query = f"""
            SELECT 
                petugas_name as petugas,
                COUNT(*) as total_dikunjungi,
                ROUND(CAST(SUM(CASE WHEN keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) as performa
            FROM kunjungan_petugas
            WHERE petugas_name IS NOT NULL AND periode = '{target_period}'
            GROUP BY petugas_name
            ORDER BY performa DESC
            """
            return jsonify([dict(row) for row in db.execute(query).fetchall()])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
