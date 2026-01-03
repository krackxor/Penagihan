import os
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar', __name__)

def register_belum_bayar_routes(app, get_db):
    """
    Rute API Cerdas untuk Manajemen Penagihan Lapangan.
    Mendukung tab petugas, jalur terdekat, & pembatasan target 10 data.
    """

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        
        # Parameter filter dari aplikasi
        petugas_name = request.args.get('petugas', '') # Diambil dari klik Tab Nama
        search_query = request.args.get('search', '')  # Pencarian Nomen/Nama
        kategori = request.args.get('kategori', 'all') 
        
        # Konfigurasi Jatuh Tempo SOP (Tanggal 20)
        TGL_JATUH_TEMPO = 20
        tgl_sekarang = datetime.now().day

        # Query Cerdas: Menggabungkan Master, Ardebt (Ekor), dan Rute Petugas
        # Status Kategori ditentukan secara dinamis
        query = """
        SELECT 
            m.nomen, m.nama, m.pcez, m.block, m.rayon, m.no_hp,
            r.petugas as nama_petugas,
            COALESCE(m.nominal, 0) as bill_current,
            COALESCE(a.jumlah, 0) as bill_tunggakan,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            CASE 
                WHEN COALESCE(a.jumlah, 0) > 0 THEN 'Berekor'
                WHEN ? < ? THEN 'Undue'
                ELSE 'Current'
            END as status_kategori
        FROM master_pelanggan m
        LEFT JOIN rute_petugas r ON m.pcez = r.pcez
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
            AND m.periode_tahun = c.periode_tahun
        WHERE c.id IS NULL 
        AND (m.nominal > 0 OR COALESCE(a.jumlah, 0) > 0)
        """
        
        params = [tgl_sekarang, TGL_JATUH_TEMPO]

        # Filter berdasarkan Petugas (Tab yang dipilih)
        if petugas_name and petugas_name != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_name)
        
        # Filter Pencarian Nama/Nomen
        if search_query:
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%'])

        # Filter Kategori (Misal hanya ingin lihat yang berekor)
        if kategori == 'berekor':
            query += " AND COALESCE(a.jumlah, 0) > 0"

        # LOGIKA CERDAS:
        # 1. Urutkan berdasarkan rute linear (PCEZ -> BLOCK)
        # 2. Ambil 10 teratas untuk target harian agar petugas fokus
        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 10"
        
        try:
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_petugas_tabs():
        """Mengambil daftar nama petugas unik untuk navigasi tab di frontend"""
        db = get_db()
        try:
            rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC").fetchall()
            return jsonify([row['petugas'] for row in rows])
        except Exception as e:
            return jsonify([])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """Menyimpan laporan lapangan dengan foto dan koordinat GPS"""
        db = get_db()
        
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        lat = request.form.get('lat')
        lng = request.form.get('lng')
        
        foto = request.files.get('foto')
        filename = f"KUNJ_{nomen}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        
        if foto:
            save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            foto.save(save_path)

        try:
            db.execute("""
                INSERT INTO kunjungan_petugas 
                (nomen, petugas_name, keterangan, foto_path, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, filename, lat, lng))
            
            db.commit()
            return jsonify({"status": "success", "message": "Laporan berhasil masuk sistem!"})
        except Exception as e:
            db.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/stats-harian', methods=['GET'])
    def get_stats_harian():
        """Menghitung progres target 10 pelanggan per petugas per hari"""
        db = get_db()
        petugas = request.args.get('petugas', '')
        today = datetime.now().strftime('%Y-%m-%d')
        
        query = """
            SELECT COUNT(*) as done 
            FROM kunjungan_petugas 
            WHERE petugas_name = ? AND date(created_at) = date(?)
        """
        row = db.execute(query, [petugas, today]).fetchone()
        return jsonify({"done": row['done'] if row else 0, "target": 10})
