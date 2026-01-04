import os
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        """
        Menampilkan daftar tagihan (Target MC) yang:
        1. Belum lunas (Tidak ada di MB / Collection).
        2. Belum pernah dikunjungi (Tidak ada di log kunjungan).
        3. Menampilkan NAMA PETUGAS hasil join dari tabel rute_petugas.
        """
        try:
            db = get_db()
            petugas_filter = request.args.get('petugas', '')
            search = request.args.get('search', '')
            
            # QUERY UTAMA:
            # Menggabungkan Master Pelanggan (m) dengan Rute Petugas (r)
            # Menggunakan LEFT JOIN agar data MC tetap muncul meski rute belum disetting
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
            
            # Jika admin/petugas memilih filter nama di dropdown
            if petugas_filter and petugas_filter != 'all':
                query += " AND r.petugas = ?"
                params.append(petugas_filter)
            
            # Jika melakukan pencarian manual (Nomen/Nama)
            if search:
                query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%'])

            # LIMIT 20: Kunci agar aplikasi terasa sangat cepat (Fast)
            # Tidak membebani browser HP petugas
            query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 20"
            
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """Menyimpan hasil laporan dari lapangan (Sudah Bayar, Janji, RKS)"""
        try:
            db = get_db()
            nomen = request.form.get('nomen')
            petugas = request.form.get('petugas')
            keterangan = request.form.get('keterangan')
            janji_bayar_dt = request.form.get('janji_bayar_dt') # Null jika bukan 'Janji Bayar'
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            db.execute("""
                INSERT INTO kunjungan_petugas (
                    nomen, petugas_name, keterangan, janji_bayar_dt, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, janji_bayar_dt, now))
            
            db.commit()
            return jsonify({"status": "success", "message": "Laporan berhasil disimpan"})
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_tabs():
        """
        API untuk mengisi DROPDOWN Petugas secara dinamis.
        Begitu Anda upload Excel Rute, nama-nama di sini otomatis terisi.
        """
        try:
            db = get_db()
            # Ambil semua nama unik dari tabel rute
            rows = db.execute("""
                SELECT DISTINCT petugas FROM rute_petugas 
                WHERE petugas IS NOT NULL AND petugas != '' 
                ORDER BY petugas ASC
            """).fetchall()
            return jsonify([row['petugas'] for row in rows])
        except Exception as e:
            return jsonify([])
