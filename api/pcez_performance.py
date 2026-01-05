from flask import jsonify, request
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Dashboard Utama dengan Nominal Uang Lengkap dan Nama Petugas Otomatis"""
        try:
            db = get_db()
            
            # --- LOGIKA PERIODE DINAMIS ---
            req_periode = request.args.get('periode') 
            today = datetime.now()
            
            if req_periode:
                try:
                    target_dt = datetime.strptime(req_periode, '%m-%Y')
                except:
                    target_dt = today
            else:
                target_dt = today

            # Periode Berjalan (n): "12-2025"
            curr_period_str = target_dt.strftime('%m-%Y')
            # Periode Lalu (n-1): "11-2025"
            last_month_dt = target_dt.replace(day=1) - timedelta(days=1)
            prev_period_str = last_month_dt.strftime('%m-%Y')

            # Query Global: Mengambil Total Nomen & Total Nominal Rupiah
            global_query = f"""
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{prev_period_str}'), 0) as total_nomen_mc,
                COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{prev_period_str}'), 0) as total_nominal_mc,
                
                -- NOMINAL LUNAS UNDUE (MB n-1)
                COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan AND mb.periode = '{prev_period_str}')
                ), 0) as total_nom_undue,
                
                -- NOMINAL LUNAS CURRENT (Collection n)
                COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notagihan = m.notagihan AND c.periode = '{curr_period_str}')
                ), 0) as total_nom_current,

                -- JUMLAH ORANG (NOMEN)
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan AND mb.periode = '{prev_period_str}')
                ), 0) as total_undue,
                
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notagihan = m.notagihan AND c.periode = '{curr_period_str}')
                ), 0) as total_current
            """
            
            # Query Officer: Menampilkan Nama Petugas dari Mapping Rute (Join Otomatis)
            officer_query = f"""
            SELECT 
                COALESCE(r.petugas, k.petugas_name, 'Petugas') as petugas,
                SUM(CASE WHEN date(k.created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
                COUNT(k.id) as bulanan
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.periode = '{prev_period_str}'
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            WHERE k.periode = '{curr_period_str}'
            GROUP BY petugas
            ORDER BY bulanan DESC
            """

            # Query History: Detail Log Aktivitas (Jumlah Orang + Nominal Uang)
            history_query = f"""
            SELECT 
                date(k.created_at) as tanggal,
                COALESCE(r.petugas, k.petugas_name, 'Sistem') as petugas,
                COUNT(*) as total,
                -- LUNAS (UANG MASUK)
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) as jml_bayar,
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN m.nominal ELSE 0 END) as nom_masuk,
                -- JANJI BAYAR (POTENSI)
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN 1 ELSE 0 END) as jml_janji,
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN m.nominal ELSE 0 END) as nom_potensi,
                -- RKS/LL (HILANG/TERTUNDA)
                SUM(CASE WHEN k.keterangan LIKE 'Rumah Kosong%' OR k.keterangan LIKE 'RKS%' THEN 1 ELSE 0 END) as jml_rks,
                SUM(CASE WHEN k.keterangan LIKE 'Rumah Kosong%' OR k.keterangan LIKE 'RKS%' THEN m.nominal ELSE 0 END) as nom_hilang
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.periode = '{prev_period_str}'
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            WHERE k.periode = '{curr_period_str}'
            GROUP BY tanggal, petugas
            ORDER BY tanggal DESC LIMIT 20
            """

            g_stat = db.execute(global_query).fetchone()
            o_stat = db.execute(officer_query).fetchall()
            h_stat = db.execute(history_query).fetchall()
            
            res_global = dict(g_stat) if g_stat else {
                "total_nomen_mc": 0, "total_nominal_mc": 0, 
                "total_undue": 0, "total_current": 0,
                "total_nom_undue": 0, "total_nom_current": 0
            }
            
            res_global['total_lunas_mc'] = res_global.get('total_undue', 0) + res_global.get('total_current', 0)
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
        try:
            db = get_db()
            req_periode = request.args.get('periode')
            target_dt = datetime.strptime(req_periode, '%m-%Y') if req_periode else datetime.now()

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
        try:
            db = get_db()
            req_periode = request.args.get('periode')
            target_period = req_periode if req_periode else datetime.now().strftime('%m-%Y')

            query = f"""
            SELECT 
                COALESCE(r.petugas, k.petugas_name, 'Petugas') as petugas,
                COUNT(*) as total_dikunjungi,
                ROUND(CAST(SUM(CASE WHEN keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) as performa
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen 
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            WHERE k.periode = '{target_period}'
            GROUP BY petugas
            ORDER BY performa DESC
            """
            return jsonify([dict(row) for row in db.execute(query).fetchall()])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
