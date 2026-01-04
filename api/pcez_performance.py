from flask import jsonify

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        db = get_db()
        # Menghitung produktivitas berdasarkan rute yang dikelola petugas
        query = """
        SELECT 
            r.petugas,
            COUNT(DISTINCT m.nomen) as total_target,
            COUNT(DISTINCT k.nomen) as total_dikunjungi,
            ROUND(CAST(COUNT(DISTINCT k.nomen) AS FLOAT) / NULLIF(COUNT(DISTINCT m.nomen), 0) * 100, 2) as performa
        FROM rute_petugas r
        JOIN master_pelanggan m ON r.pcez = m.pcez
        LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
        GROUP BY r.petugas
        ORDER BY performa DESC
        """
        try:
            rows = db.execute(query).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/per-petugas', methods=['GET'])
    def get_stats_per_petugas():
        """Menampilkan angka aktivitas kunjungan nyata per petugas (Harian, Mingguan, Bulanan)"""
        db = get_db()
        query = """
        SELECT 
            petugas_name as petugas,
            SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as harian,
            SUM(CASE WHEN date(created_at) >= date('now', '-7 days', 'localtime') THEN 1 ELSE 0 END) as mingguan,
            SUM(CASE WHEN strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime') THEN 1 ELSE 0 END) as bulanan
        FROM kunjungan_petugas
        WHERE petugas_name IS NOT NULL
        GROUP BY petugas_name
        ORDER BY harian DESC, bulanan DESC
        """
        try:
            rows = db.execute(query).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/stats-global', methods=['GET'])
    def get_global_stats():
        """Ringkasan performa untuk dashboard utama"""
        db = get_db()
        query = """
        SELECT 
            (SELECT COUNT(*) FROM kunjungan_petugas WHERE date(created_at) = date('now', 'localtime')) as harian,
            (SELECT COUNT(*) FROM kunjungan_petugas WHERE date(created_at) >= date('now', '-7 days', 'localtime')) as mingguan,
            (SELECT COUNT(*) FROM kunjungan_petugas WHERE strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime')) as bulanan,
            (SELECT COUNT(*) FROM master_pelanggan) as target_total,
            (SELECT COUNT(*) FROM collection_harian WHERE strftime('%m-%Y', created_at) = strftime('%m-%Y', 'now', 'localtime')) as realisasi_bayar
        """
        try:
            row = db.execute(query).fetchone()
            data = dict(row)
            data['sisa_target'] = data['target_total'] - data['realisasi_bayar']
            return jsonify(data)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
