from flask import Blueprint, request, jsonify
from core.helpers import APIResponse
import os

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        # Logika: 
        # 1. Cureent: Ada di MC (tagihan bln lalu) tapi belum ada di Collection bln ini.
        # 2. Tunggakan: Ada di Ardebt (> 2 bln).
        # 3. Undue: (Dikecualikan dari list ini karena hanya untuk WA Blast).
        
        query = """
        SELECT 
            m.nomen, m.nama, m.pcez,
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
        WHERE c.id IS NULL -- Belum Bayar
        AND (m.nominal > 0 OR a.jumlah > 0) -- Cureent atau Tunggakan
        ORDER BY bill_tunggakan DESC
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/wa-blast-list', methods=['GET'])
    def get_undue_list():
        db = get_db()
        # Undue: Tagihan bln ini yang dibayar bln ini (untuk apresiasi/reminder)
        query = "SELECT nomen, nama FROM master_pelanggan WHERE nominal > 0"
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        tgl_janji = request.form.get('tgl_janji_bayar')
        
        foto = request.files.get('foto')
        filename = f"{nomen}_{foto.filename}" if foto else None
        if foto:
            foto.save(os.path.join('static/uploads/kunjungan', filename))

        db.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, keterangan, tgl_janji_bayar, foto_path) 
            VALUES (?, ?, ?, ?, ?)
        """, (nomen, petugas, keterangan, tgl_janji, filename))
        db.commit()
        return APIResponse.success(message="Data kunjungan berhasil dicatat")
