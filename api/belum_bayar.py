import os
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        try:
            db = get_db()
            petugas = request.args.get('petugas', '')
            
            # LOGIKA:
            # 1. Ambil data dari MC yang belum ada di MB/Collection (Belum Lunas)
            # 2. Filter data yang BELUM PERNAH dikunjungi (k.nomen IS NULL)
            # 3. Limit 20 agar sangat cepat
            query = """
                SELECT m.nomen, m.nama, m.pcez, m.block, m.nominal
                FROM master_pelanggan m
                INNER JOIN rute_petugas r ON m.pcez = r.pcez
                LEFT JOIN master_bayar mb ON m.nomen = mb.nomen
                LEFT JOIN collection_harian c ON m.nomen = c.nomen
                LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
                WHERE m.tipe = 'MC' 
                  AND mb.nomen IS NULL 
                  AND c.nomen IS NULL
                  AND k.nomen IS NULL
            """
            
            params = []
            if petugas and petugas != 'all':
                query += " AND r.petugas = ?"
                params.append(petugas)
            
            query += " ORDER BY m.block ASC LIMIT 20"
            
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        try:
            db = get_db()
            nomen = request.form.get('nomen')
            keterangan = request.form.get('keterangan')
            petugas = request.form.get('petugas')
            janji_dt = request.form.get('janji_bayar_dt') # Tanggal Janji Bayar
            
            db.execute("""
                INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, janji_bayar_dt) 
                VALUES (?, ?, ?, ?)
            """, (nomen, petugas, keterangan, janji_dt))
            db.commit()
            
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
