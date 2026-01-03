import os
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_petugas_tabs():
        db = get_db()
        try:
            rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC").fetchall()
            return jsonify([row['petugas'] for row in rows])
        except Exception as e:
            return jsonify([])

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        petugas_name = request.args.get('petugas', '')
        search_query = request.args.get('search', '')
        
        query = """
        SELECT 
            m.nomen, m.nama, m.pcez, m.block, m.no_hp,
            r.petugas as nama_petugas,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan
        FROM master_pelanggan m
        INNER JOIN rute_petugas r ON m.pcez = r.pcez
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen AND m.periode_bulan = c.periode_bulan
        WHERE c.id IS NULL
        """
        params = []
        if petugas_name and petugas_name != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_name)
        if search_query:
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%'])

        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 10"
        rows = db.execute(query, params).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        no_hp = request.form.get('no_hp')
        foto = request.files.get('foto')

        filename = None
        if foto:
            filename = f"LRP_{nomen}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            foto.save(save_path)

        try:
            # 1. Simpan Laporan
            db.execute("""
                INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, foto_path, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, filename, datetime.now()))

            # 2. Update No HP di Master (Enrichment Data)
            if no_hp:
                db.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (no_hp, nomen))
            
            db.commit()
            return jsonify({"status": "success", "message": "Laporan & No HP berhasil diperbarui"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
