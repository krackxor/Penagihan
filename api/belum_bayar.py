import os
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_petugas_tabs():
        """Mengambil daftar nama petugas untuk navigasi Tab di atas"""
        db = get_db()
        try:
            # Mengambil nama petugas dari tabel rute yang sudah diupload
            rows = db.execute("""
                SELECT DISTINCT petugas 
                FROM rute_petugas 
                WHERE petugas IS NOT NULL AND petugas != '' 
                ORDER BY petugas ASC
            """).fetchall()
            return jsonify([row['petugas'] for row in rows])
        except Exception as e:
            return jsonify([])

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        """
        Mengambil 10 pelanggan prioritas per petugas.
        Diurutkan berdasarkan Jalur Terdekat (PCEZ & BLOK).
        """
        db = get_db()
        petugas_name = request.args.get('petugas', '')
        search_query = request.args.get('search', '')
        
        TGL_JATUH_TEMPO = 20
        tgl_hari_ini = datetime.now().day

        # Query JOIN antara Master Pelanggan dan Rute Petugas
        query = """
        SELECT 
            m.nomen, m.nama, m.pcez, m.block, m.no_hp,
            r.petugas as nama_petugas,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            CASE 
                WHEN COALESCE(a.jumlah, 0) > 0 THEN 'Berekor'
                WHEN ? < ? THEN 'Undue'
                ELSE 'Current'
            END as status_kategori
        FROM master_pelanggan m
        INNER JOIN rute_petugas r ON m.pcez = r.pcez
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
        WHERE c.id IS NULL
        """
        
        params = [tgl_hari_ini, TGL_JATUH_TEMPO]

        # Filter Nama Petugas (berdasarkan Tab yang diklik)
        if petugas_name and petugas_name != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_name)
        
        # Filter Pencarian
        if search_query:
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ? OR m.block LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

        # ORDER BY PCEZ dan BLOCK (Jalur Linear)
        # LIMIT 10 (Sesuai instruksi: 10 pelanggan per hari setiap petugas)
        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 10"
        
        try:
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/stats-harian', methods=['GET'])
    def get_stats_harian():
        """Menghitung progres 0/10 target harian petugas"""
        db = get_db()
        petugas = request.args.get('petugas', '')
        today = datetime.now().strftime('%Y-%m-%d')
        
        query = "SELECT COUNT(*) as done FROM kunjungan_petugas WHERE petugas_name = ? AND date(created_at) = date(?)"
        row = db.execute(query, [petugas, today]).fetchone()
        return jsonify({"done": row['done'] if row else 0, "target": 10})

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        
        try:
            db.execute("""
                INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, created_at)
                VALUES (?, ?, ?, ?)
            """, (nomen, petugas, keterangan, datetime.now()))
            db.commit()
            return jsonify({"status": "success", "message": "Laporan tersimpan"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
