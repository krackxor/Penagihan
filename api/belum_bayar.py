import os
from flask import Blueprint, request, jsonify
from datetime import datetime

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        try:
            db = get_db()
            petugas = request.args.get('petugas', '')
            search = request.args.get('search', '')
            
            # Query Teroptimasi menggunakan INDEX agar loading instan
            query = """
                SELECT 
                    m.nomen, m.nama, m.pcez, m.block, m.no_hp, r.petugas,
                    m.nominal as total,
                    (SELECT COUNT(*) FROM kunjungan_petugas k 
                     WHERE k.nomen = m.nomen 
                     AND date(k.created_at) = date('now', 'localtime')) as is_visited
                FROM master_pelanggan m
                INNER JOIN rute_petugas r ON m.pcez = r.pcez
                LEFT JOIN master_bayar mb ON m.nomen = mb.nomen
                WHERE m.tipe = 'MC' 
                  AND mb.nomen IS NULL 
            """
            
            params = []
            if petugas and petugas != 'all':
                query += " AND r.petugas = ?"
                params.append(petugas)
            
            if search:
                query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%'])
            
            query += " ORDER BY m.pcez ASC LIMIT 300"
            
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_tabs():
        try:
            db = get_db()
            rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas ORDER BY petugas").fetchall()
            return jsonify([row['petugas'] for row in rows])
        except:
            return jsonify([])
