import requests
from flask import Blueprint, request, jsonify
# PERBAIKAN: Ubah core.helpers menjadi api.helpers
from api.helpers import APIResponse
import os

WA_TOKEN = "YOUR_FONNTE_TOKEN" 

def send_wa_notification(phone, message):
    url = "https://api.fonnte.com/send"
    payload = {'target': phone, 'message': message, 'countryCode': '62'}
    headers = {'Authorization': WA_TOKEN}
    try:
        response = requests.post(url, data=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Error sending WA: {e}")
        return None

def register_belum_bayar_routes(app, get_db):
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
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
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        tgl_janji = request.form.get('tgl_janji_bayar')
        lat = request.form.get('lat')
        lng = request.form.get('lng')
        
        foto = request.files.get('foto')
        filename = f"{nomen}_{foto.filename}" if foto else None
        if foto:
            foto.save(os.path.join('static/uploads/kunjungan', filename))

        db.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, keterangan, tgl_janji_bayar, foto_path, latitude, longitude) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, keterangan, tgl_janji, filename, lat, lng))
        db.commit()
        return APIResponse.success(message="Data kunjungan berhasil dicatat")
