import os
from flask import request, jsonify
# Mengambil APIResponse dari folder api sesuai struktur project Anda
from api.helpers import APIResponse

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        """
        Mengambil daftar pelanggan yang belum bayar.
        Nomor HP tetap diambil agar frontend bisa membuat link WhatsApp manual.
        """
        db = get_db()
        query = """
        SELECT 
            m.nomen, m.nama, m.pcez, m.no_hp,
            COALESCE(m.nominal, 0) as bill_cureent,
            COALESCE(a.jumlah, 0) as bill_tunggakan,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            k.created_at as tgl_kunjungan,
            k.keterangan as status_terakhir
        FROM master_pelanggan m
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
        LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
        WHERE c.id IS NULL 
        AND (m.nominal > 0 OR a.jumlah > 0)
        ORDER BY bill_tunggakan DESC
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """
        Menyimpan laporan hasil kunjungan petugas ke database lokal.
        """
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        tgl_janji = request.form.get('tgl_janji_bayar')
        
        # Koordinat GPS dari browser petugas
        lat = request.form.get('lat')
        lng = request.form.get('lng')
        
        # Penanganan upload foto bukti lapangan
        foto = request.files.get('foto')
        filename = f"{nomen}_{foto.filename}" if foto else None
        if foto:
            # Pastikan folder static/uploads/kunjungan sudah ada
            save_path = os.path.join('static', 'uploads', 'kunjungan')
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            foto.save(os.path.join(save_path, filename))

        # Simpan data ke tabel kunjungan_petugas
        db.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, keterangan, tgl_janji_bayar, foto_path, latitude, longitude) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, keterangan, tgl_janji, filename, lat, lng))
        db.commit()
        
        return APIResponse.success(message="Laporan kunjungan berhasil disimpan di database lokal")
