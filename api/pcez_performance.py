from flask import jsonify

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/leaderboard', methods=['GET'])
    def get_leaderboard():
        db = get_db()
        # Query dioptimalkan untuk menghitung produktivitas dan efektivitas
        query = """
        SELECT 
            r.petugas,
            COUNT(DISTINCT m.nomen) as total_target,
            COUNT(DISTINCT k.nomen) as total_dikunjungi,
            ROUND(
                CAST(COUNT(DISTINCT k.nomen) AS FLOAT) / 
                NULLIF(COUNT(DISTINCT m.nomen), 0) * 100, 2
            ) as performa,
            SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN 1 ELSE 0 END) as total_closed
        FROM rute_petugas r
        JOIN master_pelanggan m ON r.pcez = m.pcez
        LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
        GROUP BY r.petugas
        ORDER BY performa DESC
        """
        try:
            rows = db.execute(query).fetchall()
            # Mengembalikan data dalam format list dictionary untuk dikonsumsi Chart.js
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/stats-global', methods=['GET'])
    def get_global_stats():
        """Endpoint tambahan untuk ringkasan angka di dashboard utama"""
        db = get_db()
        query = """
        SELECT 
            (SELECT COUNT(*) FROM kunjungan_petugas WHERE date(created_at) = date('now')) as kunjungan_hari_ini,
            (SELECT COUNT(*) FROM master_pelanggan) as total_pelanggan,
            (SELECT COUNT(*) FROM collection_harian WHERE periode_bulan = strftime('%m','now')) as bayar_bulan_ini
        """
        row = db.execute(query).fetchone()
        return jsonify(dict(row))
