def register_pcez_routes(app, get_db):
    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        db = get_db()
        query = """
        SELECT 
            r.petugas,
            COUNT(DISTINCT m.nomen) as total_target,
            COUNT(DISTINCT k.nomen) as total_dikunjungi,
            ROUND(CAST(COUNT(DISTINCT k.nomen) AS FLOAT) / COUNT(DISTINCT m.nomen) * 100, 2) as performa
        FROM rute_petugas r
        JOIN master_pelanggan m ON r.pcez = m.pcez
        LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
        GROUP BY r.petugas
        ORDER BY performa DESC
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
