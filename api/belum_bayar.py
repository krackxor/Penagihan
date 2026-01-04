import os
import pytz
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        try:
            db = get_db()
            petugas = request.args.get('petugas', '')
            search = request.args.get('search', '')
            
            # Query dioptimalkan: Mengambil data MC yang TIDAK ADA di MB maupun Collection
            # Menggunakan LIMIT untuk mencegah browser 'hang' jika data terlalu banyak
            query = """
                SELECT 
                    m.nomen, m.nama, m.pcez, m.block, m.no_hp, r.petugas,
                    (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total,
                    CASE WHEN k.id IS NOT NULL THEN 1 ELSE 0 END as is_visited
                FROM master_pelanggan m
                INNER JOIN rute_petugas r ON m.pcez = r.pcez
                LEFT JOIN ardebt a ON m.nomen = a.nomen
                
                -- Cek Pelunasan MB (Jika ada, maka di-filter keluar)
                LEFT JOIN master_bayar mb ON m.nomen = mb.nomen
                
                -- Cek Pelunasan Harian
                LEFT JOIN collection_harian c ON m.nomen = c.nomen
                
                -- Cek Kunjungan Hari Ini
                LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen 
                     AND date(k.created_at) = date('now', 'localtime')
                
                WHERE m.tipe = 'MC' 
                  AND mb.nomen IS NULL  -- Filter: Harus tidak ada di Master Bayar
                  AND c.nomen IS NULL   -- Filter: Harus tidak ada di Collection
            """
            
            params = []
            if petugas and petugas != 'all':
                query += " AND r.petugas = ?"
                params.append(petugas)
            
            if search:
                query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%'])
            
            # Tambahkan limit untuk keamanan performa mobile
            query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 250"
            
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_tabs():
        db = get_db()
        rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas ORDER BY petugas").fetchall()
        return jsonify([row['petugas'] for row in rows])
