from flask import jsonify, request

def register_pcez_routes(app, get_db):
    @app.route('/api/performance/stats-global', methods=['GET'])
    def get_global_stats():
        """Ringkasan angka untuk dashboard utama"""
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
            data['sisa_target'] = (data['target_total'] or 0) - (data['realisasi_bayar'] or 0)
            return jsonify(data)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/daily-detail', methods=['GET'])
    def get_daily_detail():
        """Statistik harian per petugas dengan rincian status dan nominal"""
        db = get_db()
        query = """
        SELECT 
            date(k.created_at) as tanggal,
            k.petugas_name as petugas,
            COUNT(*) as total_kunjungan,
            -- Rincian Sudah Bayar
            SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN 1 ELSE 0 END) as jml_bayar,
            SUM(CASE WHEN k.keterangan = 'Sudah Bayar' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_bayar,
            -- Rincian Janji Bayar
            SUM(CASE WHEN k.keterangan = 'Janji Bayar' THEN 1 ELSE 0 END) as jml_janji,
            SUM(CASE WHEN k.keterangan = 'Janji Bayar' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_janji,
            -- Rincian Rumah Kosong (RKS)
            SUM(CASE WHEN k.keterangan = 'Rumah Kosong' THEN 1 ELSE 0 END) as jml_rks,
            SUM(CASE WHEN k.keterangan = 'Rumah Kosong' THEN CAST(m.nominal AS REAL) ELSE 0 END) as nom_rks,
            -- Lainnya
            SUM(CASE WHEN k.keterangan NOT IN ('Sudah Bayar', 'Janji Bayar', 'Rumah Kosong') THEN 1 ELSE 0 END) as jml_lain
        FROM kunjungan_petugas k
        LEFT JOIN master_pelanggan m ON k.nomen = m.nomen
        GROUP BY tanggal, petugas
        ORDER BY tanggal DESC, total_kunjungan DESC
        LIMIT 50
        """
        try:
            rows = db.execute(query).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
