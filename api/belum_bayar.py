import os
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar', __name__)

def register_belum_bayar_routes(app, get_db):
    """
    Rute API untuk manajemen penagihan cerdas.
    Mendukung auto-mapping petugas dan pengurutan rute jalur terdekat.
    """

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        
        # Ambil parameter filter dari permintaan aplikasi
        petugas_name = request.args.get('petugas', '') # Filter petugas (Pian/Teguh/dll)
        search_query = request.args.get('search', '')  # Cari Nama atau Nomen
        kategori = request.args.get('kategori', 'all') # all, berekor, undue, current
        
        # Konfigurasi Jatuh Tempo SOP
        TGL_JATUH_TEMPO = 20
        tgl_sekarang = datetime.now().day

        # Query Cerdas: Menggabungkan Master, Ardebt, dan Rute Petugas
        # Diurutkan berdasarkan Jalur Terdekat (PCEZ dan Urutan Blok)
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

        # Logika Filter Pencarian
        if petugas_name:
            query += " AND r.petugas = ?"
            params.append(petugas_name)
        
        if search_query:
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%'])

        if kategori == 'berekor':
            query += " AND COALESCE(a.jumlah, 0) > 0"
        elif kategori == 'undue':
            query += " AND COALESCE(a.jumlah, 0) = 0 AND ? < ?"
            params.extend([tgl_sekarang, TGL_JATUH_TEMPO])

        # CERDAS: Urutan Jalur Rute (PCEZ lalu urutan Blok 01, 02, dst)
        query += " ORDER BY m.pcez ASC, m.block ASC"
        
        try:
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """Menyimpan hasil laporan petugas dari lapangan dengan GPS dan Foto"""
        db = get_db()
        
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        lat = request.form.get('lat')
        lng = request.form.get('lng')
        
        # Manajemen File Foto Proof of Visit
        foto = request.files.get('foto')
        filename = f"PROOF_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        
        if foto:
            save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            foto.save(save_path)

        try:
            # 1. Simpan detail kunjungan
            db.execute("""
                INSERT INTO kunjungan_petugas 
                (nomen, petugas_name, keterangan, foto_path, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, filename, lat, lng))
            
            # 2. Catat ke log history agar admin bisa memantau
            db.execute("""
                INSERT INTO upload_history (filename, file_type, periode, status)
                VALUES (?, 'KUNJUNGAN', ?, 'Berhasil')
            """, (filename, datetime.now().strftime('%m/%Y')))
            
            db.commit()
            return jsonify({"status": "success", "message": "Laporan cerdas berhasil disimpan!"})
        except Exception as e:
            db.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/get-petugas-list', methods=['GET'])
    def get_petugas_unique():
        """Mengambil daftar petugas unik untuk filter di aplikasi"""
        db = get_db()
        rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas ORDER BY petugas ASC").fetchall()
        return jsonify([row['petugas'] for row in rows])
