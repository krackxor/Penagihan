import os
import pytz
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from PIL import Image, ImageDraw
import socket

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def get_jakarta_time():
    tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(tz)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        try:
            db = get_db()
            petugas = request.args.get('petugas', '')
            search = request.args.get('search', '')
            
            # Query dioptimalkan: Mengambil data MC yang TIDAK ADA di MB maupun Collection
            # Menggunakan WHERE ... IS NULL untuk kecepatan maksimal
            query = """
                SELECT 
                    m.nomen, m.nama, m.pcez, m.block, m.no_hp, r.petugas,
                    (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total,
                    (SELECT COUNT(*) FROM kunjungan_petugas k 
                     WHERE k.nomen = m.nomen 
                     AND date(k.created_at) = date('now', 'localtime')) as is_visited
                FROM master_pelanggan m
                INNER JOIN rute_petugas r ON m.pcez = r.pcez
                LEFT JOIN ardebt a ON m.nomen = a.nomen
                
                -- JOIN ke tabel pelunasan
                LEFT JOIN master_bayar mb ON m.nomen = mb.nomen
                LEFT JOIN collection_harian c ON m.nomen = c.nomen
                
                WHERE m.tipe = 'MC' 
                  AND mb.nomen IS NULL  -- Sembunyikan jika ada di Master Bayar
                  AND c.nomen IS NULL   -- Sembunyikan jika ada di Collection
            """
            
            params = []
            if petugas and petugas != 'all':
                query += " AND r.petugas = ?"
                params.append(petugas)
            
            if search:
                query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%'])
            
            # LIMIT 250 untuk menjaga performa rendering di browser HP
            query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 250"
            
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        try:
            db = get_db()
            nomen = request.form.get('nomen')
            petugas = request.form.get('petugas', 'ADMIN')
            keterangan = request.form.get('keterangan')
            lat = request.form.get('lat', '0')
            lng = request.form.get('lng', '0')
            foto = request.files.get('foto')

            waktu_jkt = get_jakarta_time()
            waktu_str = waktu_jkt.strftime('%Y-%m-%d %H:%M:%S')
            
            filename = None
            if foto:
                filename = f"BUKTI_{nomen}_{waktu_jkt.strftime('%Y%m%d_%H%M%S')}.jpg"
                save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
                img = Image.open(foto).convert("RGB")
                img.thumbnail((1024, 1024))
                img.save(save_path, "JPEG", quality=85)

            db.execute("""
                INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, foto_path, latitude, longitude, created_at) 
                VALUES (?,?,?,?,?,?,?)
            """, (nomen, petugas, keterangan, filename, lat, lng, waktu_str))
            
            db.commit()
            return jsonify({"status": "success", "wa_text": f"Laporan {nomen} berhasil disimpan."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_tabs():
        db = get_db()
        rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas ORDER BY petugas").fetchall()
        return jsonify([row['petugas'] for row in rows])
