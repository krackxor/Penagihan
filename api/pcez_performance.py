from flask import jsonify, request

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """
        Mengambil semua data statistik untuk Dashboard Utama:
        1. Statistik Global (Total tim)
        2. Akumulasi Per Petugas (Leaderboard)
        3. History Detail per Tanggal per Petugas
        """
        db = get_db()
        
        # 1. Statistik Global (Total Semua Petugas & Progres MC)
        # Lunas MC dihitung jika Nomen MC ada di MB atau di Collection
        global_query = """
        SELECT 
            SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as tot_hari,
            SUM(CASE WHEN date(created_at) >= date('now', '-7 days', 'localtime') THEN 1 ELSE 0 END) as tot_minggu,
            SUM(CASE WHEN strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime') THEN 1 ELSE 0 END) as tot_bulan,
            (SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC') as total_nomen_mc,
            (SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC') as total_nominal_mc,
            (SELECT COUNT(DISTINCT m.nomen) 
             FROM master_pelanggan m 
             WHERE m.tipe = 'MC' 
             AND (
                EXISTS (SELECT 1 FROM master_pelanggan mb WHERE mb.tipe = 'MB' AND mb.nomen = m.nomen)
                OR EXISTS (SELECT 1 FROM collection_harian c WHERE c.nomen = m.nomen)
             )) as total_lunas_mc
        FROM kunjungan_petugas
        """
        
        # 2. Akumulasi Per Petugas (Leaderboard & Performa Waktu)
        officer_query = """
        SELECT 
            petugas_name as petugas,
            SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
            SUM(CASE WHEN date(created_at) >= date('now', '-7 days', 'localtime') THEN 1 ELSE 0 END) as mingguan,
            SUM(CASE WHEN strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime') THEN 1 ELSE 0 END) as bulanan
        FROM kunjungan_petugas
        WHERE petugas_name IS NOT NULL
        GROUP BY petugas_name
        ORDER BY bulanan DESC, harian DESC
        """

        # 3. History Detail Per Tanggal Per Petugas (Status & Nominal)
        # Mengambil nominal dari master_pelanggan (MC) berdasarkan nomen kunjungan
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
            SUM(CASE WHEN k.keterangan = 'Rumah Kosong' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_rks,
            SUM(CASE WHEN k.keterangan NOT IN ('Sudah Bayar', 'Janji Bayar', 'Rumah Kosong') THEN 1 ELSE 0 END) as jml_lain
        FROM kunjungan_petugas k
        LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.tipe = 'MC'
        GROUP BY tanggal, petugas
        ORDER BY tanggal DESC, total DESC
        LIMIT 50
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

    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        """Endpoint sederhana untuk peringkat berdasarkan rute (PCEZ)"""
        db = get_db()
        query = """
        SELECT 
            r.petugas,
            COUNT(DISTINCT m.nomen) as total_target,
            COUNT(DISTINCT k.nomen) as total_dikunjungi,
            ROUND(CAST(COUNT(DISTINCT k.nomen) AS FLOAT) / NULLIF(COUNT(DISTINCT m.nomen), 0) * 100, 2) as performa
        FROM rute_petugas r
        JOIN master_pelanggan m ON r.pcez = m.pcez AND m.tipe = 'MC'
        LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
        GROUP BY r.petugas
        ORDER BY performa DESC
        """
        try:
            rows = db.execute(query).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
