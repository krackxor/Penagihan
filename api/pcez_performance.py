from flask import jsonify, request
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Dashboard Utama dengan Logika Pintu Ganda (NOTAGIHAN + PERIODE)"""
        try:
            db = get_db()
            
            # --- LOGIKA PERIODE DINAMIS ---
            req_periode = request.args.get('periode') # Format: MM-YYYY (dari Kalender)
            today = datetime.now()
            
            if req_periode:
                try:
                    target_dt = datetime.strptime(req_periode, '%m-%Y')
                except:
                    target_dt = today
            else:
                target_dt = today

            # 1. Periode Berjalan (n) untuk filter Collection: "12-2025"
            curr_period_str = target_dt.strftime('%m-%Y')
            
            # 2. Periode Lalu (n-1) untuk MC dan MB Undue: "11-2025"
            last_month_dt = target_dt.replace(day=1) - timedelta(days=1)
            prev_period_str = last_month_dt.strftime('%m-%Y')

            # Query Global: Menggunakan NOTAGIHAN untuk akurasi pelunasan
            global_query = f"""
            SELECT 
                -- Total Target: MC Periode n-1
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{prev_period_str}'), 0) as total_nomen_mc,
                COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{prev_period_str}'), 0) as total_nominal_mc,
                
                -- Realisasi Lunas (Undue n-1 + Current n) menggunakan Pintu Ganda
                COALESCE((SELECT COUNT(DISTINCT m.nomen) 
                 FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND (
                    -- PINTU GANDA UNDUE: NOTAGIHAN cocok & MB Periode n-1 (BULAN_REK)
                    EXISTS (SELECT 1 FROM master_bayar mb 
                            WHERE mb.notagihan = m.notagihan AND mb.periode = '{prev_period_str}')
                    OR 
                    -- PINTU GANDA CURRENT: NOTAGIHAN cocok & Collection Periode n (PAY_DT)
                    EXISTS (SELECT 1 FROM collection_harian c 
                            WHERE c.notagihan = m.notagihan AND c.periode = '{curr_period_str}')
                 )), 0) as total_lunas_mc
            """
            
            # Query Officer: Berdasarkan laporan kunjungan pada bulan berjalan
            officer_query = f"""
            SELECT 
                petugas_name as petugas,
                SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
                COUNT(*) as bulanan
            FROM kunjungan_petugas
            WHERE petugas_name IS NOT NULL AND periode = '{curr_period_str}'
            GROUP BY petugas_name
            ORDER BY bulanan DESC
            """

            # Query History: Menampilkan log aktivitas tim
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
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.periode = '{prev_period_str}'
            WHERE k.periode = '{curr_period_str}'
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
                "active_period": curr_period_str,
                "target_mc_period": prev_period_str
            })
        except Exception as e:
            print(f"Error Performance API: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/stats-global', methods=['GET'])
    def get_stats_global():
        """Statistik ringkas untuk Performa Tim (Pintu Ganda)"""
        try:
            db = get_db()
            req_periode = request.args.get('periode')
            today = datetime.now()
            target_dt = datetime.strptime(req_periode, '%m-%Y') if req_periode else today

            curr_p = target_dt.strftime('%m-%Y')
            last_p = (target_dt.replace(day=1) - timedelta(days=1)).strftime('%m-%Y')

            query = f"""
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{last_p}'), 0) as total_pelanggan,
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{last_p}' AND (
                    EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan AND mb.periode = '{last_p}') OR 
                    EXISTS (SELECT 1 FROM collection_harian c WHERE c.notagihan = m.notagihan AND c.periode = '{curr_p}')
                 )), 0) as bayar_bulan_ini
            """
            return jsonify(dict(db.execute(query).fetchone()))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        """Leaderboard sukses penagihan per periode"""
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
