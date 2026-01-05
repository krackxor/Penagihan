from flask import jsonify, request
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Dashboard Utama dengan rincian Nomen & Nominal serta Live Feed per Jam"""
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

            # 1. Query Global: Nomen & Nominal (Sisa Target, Undue, Current)
            global_query = f"""
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{prev_period_str}'), 0) as total_nomen_mc,
                COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = '{prev_period_str}'), 0) as total_nominal_mc,
                
                -- NOMINAL LUNAS UNDUE (MB n-1)
                COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan AND mb.periode = '{prev_period_str}')
                ), 0) as nom_undue,
                
                -- NOMINAL LUNAS CURRENT (Collection n)
                COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notagihan = m.notagihan AND c.periode = '{curr_period_str}')
                ), 0) as nom_current,

                -- JUMLAH ORANG (NOMEN) UNDUE
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan AND mb.periode = '{prev_period_str}')
                ), 0) as count_undue,
                
                -- JUMLAH ORANG (NOMEN) CURRENT
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = '{prev_period_str}'
                 AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notagihan = m.notagihan AND c.periode = '{curr_period_str}')
                ), 0) as count_current
            """
            
            # 2. Query History Tim (Ringkasan/Rekap per Hari)
            history_tim_query = f"""
            SELECT 
                date(k.created_at) as tanggal,
                COALESCE(
                    (SELECT rp.petugas FROM rute_petugas rp 
                     JOIN master_pelanggan mp ON rp.pcez = mp.pcez 
                     WHERE mp.nomen = k.nomen ORDER BY mp.id DESC LIMIT 1),
                    k.petugas_name, 'Petugas'
                ) as petugas,
                COUNT(*) as total,
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN 1 ELSE 0 END) as jml_bayar,
                SUM(CASE WHEN k.keterangan LIKE 'Sudah Bayar%' THEN 
                    COALESCE((SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 0) 
                    ELSE 0 END) as nom_masuk,
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN 1 ELSE 0 END) as jml_janji,
                SUM(CASE WHEN k.keterangan LIKE 'Janji Bayar%' THEN 
                    COALESCE((SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 0) 
                    ELSE 0 END) as nom_potensi,
                SUM(CASE WHEN k.keterangan LIKE 'Rumah Kosong%' OR k.keterangan LIKE 'RKS%' THEN 1 ELSE 0 END) as jml_rks,
                SUM(CASE WHEN k.keterangan LIKE 'Rumah Kosong%' OR k.keterangan LIKE 'RKS%' THEN 
                    COALESCE((SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 0) 
                    ELSE 0 END) as nom_hilang
            FROM kunjungan_petugas k
            WHERE k.periode = '{curr_period_str}'
            GROUP BY tanggal, petugas
            ORDER BY tanggal DESC LIMIT 15
            """

            # 3. Query Log Aktivitas Petugas (SUDAH DIPERBAIKI: JOIN NAMA PELANGGAN)
            log_petugas_query = f"""
            SELECT 
                k.created_at as waktu,
                k.nomen,
                COALESCE(m_nama.nama, 'Pelanggan') as nama,
                k.keterangan,
                COALESCE(
                    (SELECT rp.petugas FROM rute_petugas rp 
                     JOIN master_pelanggan mp ON rp.pcez = mp.pcez 
                     WHERE mp.nomen = k.nomen ORDER BY mp.id DESC LIMIT 1),
                    k.petugas_name, 'Petugas'
                ) as petugas,
                COALESCE((SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1), 0) as nominal
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m_nama ON k.nomen = m_nama.nomen 
            WHERE k.periode = '{curr_period_str}'
            GROUP BY k.id
            ORDER BY k.created_at DESC LIMIT 100
            """

            g_stat = db.execute(global_query).fetchone()
            h_tim = db.execute(history_tim_query).fetchall()
            l_petugas = db.execute(log_petugas_query).fetchall()
            
            res_global = dict(g_stat) if g_stat else {
                "total_nomen_mc": 0, "total_nominal_mc": 0, "count_undue": 0, "count_current": 0,
                "nom_undue": 0, "nom_current": 0
            }
            
            # Hitung Sisa Target (Nomen & Nominal)
            res_global['total_lunas_mc'] = res_global.get('count_undue', 0) + res_global.get('count_current', 0)
            res_global['sisa_nomen'] = res_global['total_nomen_mc'] - res_global['total_lunas_mc']
            res_global['sisa_nominal'] = res_global['total_nominal_mc'] - (res_global.get('nom_undue', 0) + res_global.get('nom_current', 0))

            return jsonify({
                "global": res_global,
                "history": [dict(row) for row in h_tim], 
                "log_petugas": [dict(row) for row in l_petugas], 
                "officers": [dict(row) for row in db.execute(f"SELECT COALESCE(petugas_name, 'Petugas') as petugas, COUNT(*) as bulanan FROM kunjungan_petugas WHERE periode='{curr_period_str}' GROUP BY petugas ORDER BY bulanan DESC").fetchall()],
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
