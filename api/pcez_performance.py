from flask import jsonify, request

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        try:
            db = get_db()
            
            # 1. Global Stats & Progres MC vs (MB + Collection)
            global_query = """
            SELECT 
                SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as tot_hari,
                SUM(CASE WHEN date(created_at) >= date('now', '-7 days', 'localtime') THEN 1 ELSE 0 END) as tot_minggu,
                SUM(CASE WHEN strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime') THEN 1 ELSE 0 END) as tot_bulan,
                (SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC') as total_nomen_mc,
                (SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC') as total_nominal_mc,
                (SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m WHERE m.tipe = 'MC' 
                 AND (EXISTS (SELECT 1 FROM master_pelanggan mb WHERE mb.tipe = 'MB' AND mb.nomen = m.nomen)
                      OR EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen))) as total_lunas_mc
            FROM kunjungan_petugas
            """
            
            # 2. Leaderboard Petugas
            officer_query = """
            SELECT petugas_name as petugas,
                   SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
                   SUM(CASE WHEN date(created_at) >= date('now', '-7 days', 'localtime') THEN 1 ELSE 0 END) as mingguan,
                   SUM(CASE WHEN strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime') THEN 1 ELSE 0 END) as bulanan
            FROM kunjungan_petugas GROUP BY petugas_name ORDER BY bulanan DESC
            """

            # 3. History Detail per Tanggal
            history_query = """
            SELECT date(k.created_at) as tanggal, k.petugas_name as petugas, COUNT(*) as total,
                   SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN 1 ELSE 0 END) as jml_bayar,
                   SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_bayar,
                   SUM(CASE WHEN k.keterangan = 'Janji Bayar' THEN 1 ELSE 0 END) as jml_janji,
                   SUM(CASE WHEN k.keterangan = 'Janji Bayar' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_janji,
                   SUM(CASE WHEN k.keterangan = 'Rumah Kosong' THEN 1 ELSE 0 END) as jml_rks
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.tipe = 'MC'
            GROUP BY tanggal, petugas ORDER BY tanggal DESC LIMIT 50
            """

            g_res = dict(db.execute(global_query).fetchone())
            g_res['sisa_target'] = (g_res['total_nomen_mc'] or 0) - (g_res['total_lunas_mc'] or 0)

            return jsonify({
                "global": g_res,
                "officers": [dict(r) for r in db.execute(officer_query).fetchall()],
                "history": [dict(r) for r in db.execute(history_query).fetchall()]
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
