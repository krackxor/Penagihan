import os
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        """
        Mengambil daftar target penagihan yang:
        1. Belum lunas di tabel Master Bayar (MB) atau Collection.
        2. Belum pernah dikunjungi oleh petugas.
        3. Menampilkan nama petugas berdasarkan mapping PCEZ.
        """
        try:
            db = get_db()
            petugas_filter = request.args.get('petugas', '')
            search = request.args.get('search', '')
            
            # Query dioptimalkan dengan LEFT JOIN agar loading instan
            # m.pcez sudah dalam format 096/02 hasil olahan saat upload MC
            query = """
                SELECT 
                    m.nomen, m.nama, m.pcez, m.block, m.nominal,
                    r.petugas as nama_petugas
                FROM master_pelanggan m
                LEFT JOIN rute_petugas r ON m.pcez = r.pcez
                LEFT JOIN master_bayar mb ON m.nomen = mb.nomen
                LEFT JOIN collection_harian c ON m.nomen = c.nomen
                LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
                WHERE m.tipe = 'MC' 
                  AND mb.nomen IS NULL 
                  AND c.nomen IS NULL
                  AND k.nomen IS NULL
            """
            
            params = []
            
            # Filter berdasarkan petugas yang dipilih di dropdown
            if petugas_filter and petugas_filter != 'all':
                query += " AND r.petugas = ?"
                params.append(petugas_filter)
            
            # Filter pencarian Nomen atau Nama
            if search:
                query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%'])

            # Limit 20 per petugas agar loading super cepat (Fast)
            query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 20"
            
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """
        Menyimpan hasil laporan kunjungan dari lapangan.
        Data yang sudah disimpan akan otomatis hilang dari daftar tugas.
        """
        try:
            db = get_db()
            nomen = request.form.get('nomen')
            petugas = request.form.get('petugas')
            keterangan = request.form.get('keterangan')
            janji_bayar_dt = request.form.get('janji_bayar_dt') # Format: YYYY-MM-DD
            lat = request.form.get('lat', '0')
            lng = request.form.get('lng', '0')
            
            # Ambil waktu sekarang Jakarta
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Insert ke tabel kunjungan_petugas
            db.execute("""
                INSERT INTO kunjungan_petugas (
                    nomen, petugas_name, keterangan, janji_bayar_dt, 
                    latitude, longitude, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, janji_bayar_dt, lat, lng, now))
            
            db.commit()
            return jsonify({
                "status": "success", 
                "message": f"Laporan {nomen} berhasil disimpan."
            })
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_tabs():
        """Mengambil daftar nama petugas unik untuk dropdown filter"""
        try:
            db = get_db()
            rows = db.execute("""
                SELECT DISTINCT petugas FROM rute_petugas 
                WHERE petugas IS NOT NULL AND petugas != '' 
                ORDER BY petugas ASC
            """).fetchall()
            return jsonify([row['petugas'] for row in rows])
        except:
            return jsonify([])
