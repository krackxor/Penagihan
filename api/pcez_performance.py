from flask import jsonify, request
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Dashboard Utama dengan Nominal Lengkap dan Smart Search History"""
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

            # Periode Berjalan (n): "01-2026"
            curr_period_str = target_dt.strftime('%m-%Y')
            # Periode Lalu (n-1): "12-2025"
            last_month_dt = target_dt.replace(day=1) - timedelta(days=1)
            prev_period_str = last_month_dt.strftime('%m-%Y')

            # Query Global: Target MC (n-1) vs Realisasi
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
            
            # Query Officer: Ambil petugas dari rute berdasarkan rute terakhir pelanggan jika MC n-1 belum ada
            officer_query = f"""
            SELECT 
                COALESCE(
                    (SELECT rp.petugas FROM rute_petugas rp 
                     JOIN master_pelanggan mp ON rp.pcez = mp.pcez 
                     WHERE mp.nomen = k.nomen ORDER BY mp.id DESC LIMIT 1),
                    k.petugas_name, 'Petugas'
                ) as petugas,
                SUM(CASE WHEN date(k.created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
                COUNT(k.id) as bulanan
            FROM kunjungan_petugas k
            WHERE k.periode = '{curr_period_str}'
            GROUP BY petugas
            ORDER BY bulanan DESC
            """

            # Query History: Smart Search Nominal dan Petugas (Mencegah Nominal 0 sebelum tgl 10)
            history_query = f"""
            SELECT 
                date(k.created_at) as tanggal,
                COALESCE(
                    (SELECT rp.petugas FROM rute_petugas rp 
                     JOIN master_pelanggan mp ON rp.pcez = mp.pcez 
                     WHERE mp.nomen = k.nomen ORDER BY mp.id DESC LIMIT 1),
                    k.petugas_name, 'Sistem'
                ) as petugas,
                COUNT(*) as total,
                -- Hitung Orang
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) as jml_bayar,
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN 1 ELSE 0 END) as jml_janji,
                SUM(CASE WHEN k.keterangan LIKE 'Rumah Kosong%' OR k.keterangan LIKE 'RKS%' THEN 1 ELSE 0 END) as jml_rks,
                -- Ambil Nominal Terakhir dari Database Pelanggan (Jika MC bulan ini belum turun)
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN 
                    COALESCE((SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 0) 
                    ELSE 0 END) as nom_masuk,
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN 
                    COALESCE((SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 0) 
                    ELSE 0 END) as nom_potensi,
                SUM(CASE WHEN k.keterangan LIKE 'Rumah Kosong%' OR k.keterangan LIKE 'RKS%' THEN 
                    COALESCE((SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 0) 
                    ELSE 0 END) as nom_hilang
            FROM kunjungan_petugas k
            WHERE k.periode = '{curr_period_str}'
            GROUP BY tanggal, petugas
            ORDER BY tanggal DESC LIMIT 20
            """

            g_stat = db.execute(global_query).fetchone()
            o_stat = db.execute(officer_query).fetchall()
            h_stat = db.execute(history_query).fetchall()
            
            res_global = dict(g_stat) if g_stat else {
                "total_nomen_mc": 0, "total_nominal_mc": 0, "total_undue": 0, "total_current": 0,
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
                COALESCE(
                    (SELECT rp.petugas FROM rute_petugas rp 
                     JOIN master_pelanggan mp ON rp.pcez = mp.pcez 
                     WHERE mp.nomen = k.nomen ORDER BY mp.id DESC LIMIT 1),
                    k.petugas_name, 'Petugas'
                ) as petugas,
                COUNT(*) as total_dikunjungi,
                ROUND(CAST(SUM(CASE WHEN keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) as performa
            FROM kunjungan_petugas k
            WHERE k.periode = '{target_period}'
            GROUP BY petugas
            ORDER BY performa DESC
            """
            return jsonify([dict(row) for row in db.execute(query).fetchall()])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
