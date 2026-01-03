import os
from flask import request, jsonify, current_app
from api.helpers import APIResponse
from datetime import datetime

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        # Parameter kategori dari frontend (undue, current, berekor)
        kategori = request.args.get('kategori', 'all')
        tgl_skala = 20 # Contoh tanggal jatuh tempo sesuai SOP
        tgl_sekarang = datetime.now().day

        query = """
        SELECT 
            m.nomen, m.nama, m.pcez, m.no_hp,
            COALESCE(m.nominal, 0) as bill_current,
            COALESCE(a.jumlah, 0) as bill_tunggakan,
            COALESCE(a.periode_bill, 0) as lembar_tunggakan,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            CASE 
                WHEN a.jumlah > 0 THEN 'Berekor'
                WHEN ? < ? THEN 'Undue'
                ELSE 'Current'
            END as kategori_tagihan
        FROM master_pelanggan m
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
        WHERE c.id IS NULL 
        AND (m.nominal > 0 OR a.jumlah > 0)
        """
        
        # Tambahkan filter jika kategori dipilih
        params = [tgl_sekarang, tgl_skala]
        if kategori == 'berekor':
            query += " AND a.jumlah > 0"
        elif kategori == 'undue':
            query += " AND a.jumlah IS NULL AND ? < ?"
            params.extend([tgl_sekarang, tgl_skala])
        elif kategori == 'current':
            query += " AND a.jumlah IS NULL AND ? >= ?"
            params.extend([tgl_sekarang, tgl_skala])

        query += " ORDER BY bill_tunggakan DESC, bill_current DESC"
        
        rows = db.execute(query, params).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        
        # Simpan Foto
        foto = request.files.get('foto')
        filename = f"{nomen}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        if foto:
            path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            foto.save(path)

        # Simpan ke DB
        db.execute("""
            INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, foto_path)
            VALUES (?, ?, ?, ?)
        """, (nomen, petugas, keterangan, filename))
        
        # Update Riwayat (History) agar data masuk ke menu log
        db.execute("""
            INSERT INTO upload_history (filename, file_type, periode, status)
            VALUES (?, ?, ?, ?)
        """, (filename, 'Kunjungan', datetime.now().strftime('%m/%Y'), 'Berhasil'))
        
        db.commit()
        return APIResponse.success(message="Laporan kunjungan berhasil disimpan")
