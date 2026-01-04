from flask import jsonify, request

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Statistik Dashboard Utama"""
        try:
            db = get_db()
            
            # Query Global: Menghitung Target (MC) vs Realisasi (MB + Collection)
            global_query = """
            SELECT 
                (SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC') as total_nomen_mc,
                (SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC') as total_nominal_mc,
                (SELECT COUNT(DISTINCT m.nomen) 
                 FROM master_pelanggan m 
                 WHERE m.tipe = 'MC' 
                 AND (
                    EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = m.nomen)
                    OR EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen)
                 )) as total_lunas_mc
            """
            
            # Query Officer: Berdasarkan kunjungan petugas
            officer_query = """
            SELECT 
                petugas_name as petugas,
                SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
                COUNT(*) as bulanan
            FROM kunjungan_petugas
            GROUP BY petugas_name
            ORDER BY bulanan DESC
            """

            # Query History: Detail aktivitas harian
            history_query = """
            SELECT 
                date(k.created_at) as tanggal,
                k.petugas_name as petugas,
                COUNT(*) as total,
                SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN 1 ELSE 0 END) as jml_bayar,
                SUM(CASE WHEN k.keterangan = 'Janji Bayar' THEN 1 ELSE 0 END) as jml_janji
            FROM kunjungan_petugas k
            GROUP BY tanggal, petugas
            ORDER BY tanggal DESC LIMIT 20
            """

            g_stat = db.execute(global_query).fetchone()
            o_stat = db.execute(officer_query).fetchall()
            h_stat = db.execute(history_query).fetchall()
            
            res_global = dict(g_stat) if g_stat else {}
            res_global['sisa_target'] = (res_global.get('total_nomen_mc', 0)) - (res_global.get('total_lunas_mc', 0))

            return jsonify({
                "global": res_global,
                "officers": [dict(row) for row in o_stat],
                "history": [dict(row) for row in h_stat]
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/stats-global', methods=['GET'])
    def get_stats_global():
        """Digunakan oleh halaman Performa Tim"""
        db = get_db()
        query = """
        SELECT 
            (SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC') as total_pelanggan,
            (SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
             WHERE m.tipe = 'MC' AND (
                EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = m.nomen) OR 
                EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen)
             )) as bayar_bulan_ini
        """
        return jsonify(dict(db.execute(query).fetchone()))

    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        """Leaderboard untuk grafik Performa"""
        db = get_db()
        query = """
        SELECT 
            petugas_name as petugas,
            COUNT(*) as total_dikunjungi,
            ROUND(CAST(SUM(CASE WHEN keterangan = 'Sudah Bayar' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) as performa
        FROM kunjungan_petugas
        GROUP BY petugas_name
        ORDER BY performa DESC
        """
        return jsonify([dict(row) for row in db.execute(query).fetchall()])
