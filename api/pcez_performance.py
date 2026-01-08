from flask import jsonify, request
from datetime import datetime, timedelta

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Strategis: Target (N-1) vs Realisasi (N)"""
        try:
            db = get_db()
            today = datetime.now()
            
            # --- 1. PERIODE REALISASI ---
            req_periode = request.args.get('periode') # Format: MM-YYYY
            if req_periode:
                try:
                    target_dt = datetime.strptime(req_periode, '%m-%Y')
                except:
                    target_dt = today
            else:
                target_dt = today

            curr_period_str = target_dt.strftime('%m-%Y') 

            # --- 2. LOGIKA TARGET SMART (N-1) ---
            # Mengambil periode MC terbaru yang tersedia di database
            last_mc_query = db.execute("""
                SELECT periode FROM master_pelanggan 
                WHERE tipe = 'MC' 
                ORDER BY substr(periode,4,4) DESC, substr(periode,1,2) DESC 
                LIMIT 1
            """).fetchone()
            
            target_period = last_mc_query[0] if last_mc_query else (target_dt.replace(day=1) - timedelta(days=1)).strftime('%m-%Y')

            # --- 3. QUERY GLOBAL DASHBOARD (Pintu Ganda) ---
            # Menggunakan parameterized query untuk keamanan dan efisiensi
            global_query = """
            SELECT 
                COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ?), 0) as total_nomen_mc,
                COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ?), 0) as total_nominal_mc,
                
                COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = ?
                 AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan)
                ), 0) as nom_undue,
                
                COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = ?
                 AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = m.notagihan)
                ), 0) as nom_current,

                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = ?
                 AND EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan)
                ), 0) as count_undue,
                
                COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' AND m.periode = ?
                 AND EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = m.notagihan)
                ), 0) as count_current
            """
            
            # --- 4. QUERY RANKING PETUGAS (Join PCEZ Langsung) ---
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
            GROUP BY petugas ORDER BY total_nominal DESC
            """

            # --- 5. QUERY LIVE FEED ---
            log_petugas_query = """
            SELECT 
                datetime(k.created_at, '+7 hours') as waktu,
                k.nomen, COALESCE(mp.nama, 'Pelanggan') as nama, k.keterangan,
                COALESCE(r.petugas, k.petugas_name, 'Petugas Umum') as petugas,
                COALESCE(
                    (SELECT nominal FROM master_pelanggan WHERE nomen = k.nomen ORDER BY id DESC LIMIT 1),
                    (SELECT SUM(jumlah) FROM ardebt WHERE nomen = k.nomen), 0
                ) as nominal
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan mp ON k.nomen = mp.nomen
            LEFT JOIN rute_petugas r ON mp.pcez = r.pcez
            WHERE k.periode = ?
            GROUP BY k.id ORDER BY k.created_at DESC LIMIT 100
            """

            g_stat = db.execute(global_query, [target_period] * 6).fetchone()
            o_rank = db.execute(officer_ranking_query, [curr_period_str]).fetchall()
            l_petugas = db.execute(log_petugas_query, [curr_period_str]).fetchall()
            
            res_global = dict(g_stat) if g_stat else {"total_nomen_mc": 0, "total_nominal_mc": 0}
            res_global['total_lunas_mc'] = res_global.get('count_undue', 0) + res_global.get('count_current', 0)
            res_global['sisa_nomen'] = res_global.get('total_nomen_mc', 0) - res_global.get('total_lunas_mc', 0)
            res_global['sisa_nominal'] = res_global.get('total_nominal_mc', 0) - (res_global.get('nom_undue', 0) + res_global.get('nom_current', 0))

            return jsonify({
                "global": res_global,
                "officers": [dict(row) for row in o_rank],
                "log_petugas": [dict(row) for row in l_petugas],
                "active_period": curr_period_str,
                "target_period": target_period
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/reminders', methods=['GET'])
    def get_reminders():
        """Monitoring Janji Bayar dengan Validasi Lunas Terkini"""
        try:
            db = get_db()
            req_periode = request.args.get('periode')
            
            if req_periode:
                # Filter berdasarkan bulan janji bayar
                date_filter = "strftime('%m-%Y', k.janji_bayar_dt) = ?"
                param = req_periode
            else:
                # Default: Janji bayar hari ini
                date_filter = "date(k.janji_bayar_dt) = ?"
                param = datetime.now().strftime('%Y-%m-%d')

            query = f"""
                SELECT 
                    date(k.created_at, '+7 hours') as tanggal_jalan,
                    COALESCE(r.petugas, k.petugas_name, 'Petugas Umum') as petugas_name,
                    k.nomen, k.no_hp, k.janji_bayar_dt as tanggal_janji,
                    COALESCE(m.nama, 'Pelanggan') as nama,
                    COALESCE(m.nominal, (SELECT SUM(jumlah) FROM ardebt WHERE nomen = k.nomen)) as nominal,
                    k.catatan,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan) OR 
                             EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = m.notagihan)
                        THEN 'LUNAS' ELSE 'BELUM BAYAR'
                    END as status_bayar
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan m ON k.nomen = m.nomen
                LEFT JOIN rute_petugas r ON m.pcez = r.pcez
                WHERE {date_filter}
                AND (k.keterangan LIKE '%Janji%' OR k.catatan LIKE '%Janji%')
                GROUP BY k.id ORDER BY k.janji_bayar_dt ASC
            """
            rows = db.execute(query, [param]).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
