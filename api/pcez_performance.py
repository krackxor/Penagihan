from flask import jsonify, request

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """Mengambil semua data statistik untuk Dashboard Utama"""
        db = get_db()
        
        # 1. Statistik Global (Total Semua Petugas)
        global_query = """
        SELECT 
            SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as tot_hari,
            SUM(CASE WHEN date(created_at) >= date('now', '-7 days', 'localtime') THEN 1 ELSE 0 END) as tot_minggu,
            SUM(CASE WHEN strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime') THEN 1 ELSE 0 END) as tot_bulan,
            (SELECT COUNT(*) FROM master_pelanggan) as target_total,
            (SELECT COUNT(*) FROM collection_harian WHERE strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime')) as lunas_bulan_ini
        FROM kunjungan_petugas
        """
        
        # 2. Akumulasi Per Petugas (Seminggu & Sebulan)
        officer_query = """
        SELECT 
            petugas_name as petugas,
            SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
            SUM(CASE WHEN date(created_at) >= date('now', '-7 days', 'localtime') THEN 1 ELSE 0 END) as mingguan,
            SUM(CASE WHEN strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime') THEN 1 ELSE 0 END) as bulanan
        FROM kunjungan_petugas
        WHERE petugas_name IS NOT NULL
        GROUP BY petugas_name
        ORDER BY bulanan DESC
        """

        # 3. History Detail Per Tanggal Per Petugas (Nominal & Status)
        history_query = """
        SELECT 
            date(k.created_at) as tanggal,
            k.petugas_name as petugas,
            COUNT(*) as total,
            SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN 1 ELSE 0 END) as jml_bayar,
            SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_bayar,
            SUM(CASE WHEN k.keterangan = 'Janji Bayar' THEN 1 ELSE 0 END) as jml_janji,
            SUM(CASE WHEN k.keterangan = 'Janji Bayar' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_janji,
            SUM(CASE WHEN k.keterangan = 'Rumah Kosong' THEN 1 ELSE 0 END) as jml_rks,
            SUM(CASE WHEN k.keterangan = 'Rumah Kosong' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_rks
        FROM kunjungan_petugas k
        LEFT JOIN master_pelanggan m ON k.nomen = m.nomen
        GROUP BY tanggal, petugas
        ORDER BY tanggal DESC, total DESC
        LIMIT 30
        """

        try:
            g_stat = db.execute(global_query).fetchone()
            o_stat = db.execute(officer_query).fetchall()
            h_stat = db.execute(history_query).fetchall()
            
            return jsonify({
                "global": dict(g_stat) if g_stat else {},
                "officers": [dict(row) for row in o_stat],
                "history": [dict(row) for row in h_stat]
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
