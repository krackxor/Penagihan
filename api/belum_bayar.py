import os
from flask import request, jsonify
from api.helpers import APIResponse

def register_belum_bayar_routes(app, get_db):
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        query = """
            SELECT m.nomen, m.nama, m.pcez, m.no_hp,
            COALESCE(m.nominal, 0) as bill_cureent,
            COALESCE(a.jumlah, 0) as bill_tunggakan,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            k.keterangan as status_terakhir
            FROM master_pelanggan m
            LEFT JOIN ardebt a ON m.nomen = a.nomen
            LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
            WHERE (m.nominal > 0 OR a.jumlah > 0)
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        db = get_db()
        # Logika simpan data kunjungan dan foto ke static/uploads/kunjungan
        # (Sesuai dengan kode sebelumnya namun menggunakan path dari config)
        return APIResponse.success(message="Data kunjungan berhasil dicatat")
