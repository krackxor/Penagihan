import os
import socket
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def get_server_ip():
    """Mengambil IP Address Server untuk Link WA"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_petugas_tabs():
        db = get_db()
        try:
            rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC").fetchall()
            return jsonify([row['petugas'] for row in rows])
        except: return jsonify([])

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        petugas_name = request.args.get('petugas', '')
        search_query = request.args.get('search', '')
        
        query = """
        SELECT m.nomen, m.nama, m.pcez, m.block, m.no_hp, r.petugas,
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
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ? OR m.block LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 10"
        rows = db.execute(query, params).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        db = get_db()
        try:
            nomen = request.form.get('nomen')
            petugas = request.form.get('petugas', 'ADMIN')
            keterangan = request.form.get('keterangan')
            no_hp = request.form.get('no_hp')
            lat = request.form.get('lat', '0')
            lng = request.form.get('lng', '0')
            foto = request.files.get('foto')

            pel = db.execute("SELECT nama FROM master_pelanggan WHERE nomen = ?", (nomen,)).fetchone()
            nama_pel = pel['nama'] if pel else "-"
            
            filename = None
            photo_url = "Tanpa Foto"
            # Link Google Maps
            maps_url = f"https://www.google.com/maps?q={lat},{lng}"

            if foto:
                filename = f"BUKTI_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
                
                # Proses Watermark dengan Pillow
                img = Image.open(foto).convert("RGB")
                img.thumbnail((1024, 1024))
                draw = ImageDraw.Draw(img)
                
                waktu_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                wm_text = f"WAKTU: {waktu_str}\nPETUGAS: {petugas}\nGPS: {lat}, {lng}"
                
                # Gambar kotak background text di pojok bawah
                draw.rectangle([10, img.height - 90, 550, img.height - 10], fill=(0, 0, 0))
                draw.text((20, img.height - 80), wm_text, fill=(255, 255, 255))
                
                img.save(save_path, "JPEG", quality=85)
                photo_url = f"http://{get_server_ip()}:5000/uploads/kunjungan/{filename}"

            # Simpan ke Database
            db.execute("""INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, foto_path, created_at)
                          VALUES (?, ?, ?, ?, ?)""", (nomen, petugas, keterangan, filename, datetime.now()))
            
            if no_hp:
                db.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (no_hp, nomen))
            
            db.commit()

            # Susun Pesan WhatsApp
            wa_text = (
                f"📢 *LAPORAN PENAGIHAN*\n"
                f"--------------------------------\n"
                f"👷 *Petugas:* {petugas}\n"
                f"🏠 *Nama:* {nama_pel}\n"
                f"🆔 *Nomen:* {nomen}\n"
                f"📝 *Hasil:* {keterangan}\n"
                f"📱 *No HP:* {no_hp if no_hp else '-'}\n\n"
                f"📍 *Lokasi GPS:* \n{maps_url}\n\n"
                f"📸 *Bukti Foto:* \n{photo_url}\n"
                f"--------------------------------"
            )

            return jsonify({"status": "success", "wa_text": wa_text})

        except Exception as e:
            db.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/belum-bayar/stats-harian', methods=['GET'])
    def get_stats_harian():
        db = get_db()
        petugas = request.args.get('petugas', '')
        row = db.execute("SELECT COUNT(*) as done FROM kunjungan_petugas WHERE petugas_name = ? AND date(created_at) = date('now')", (petugas,)).fetchone()
        return jsonify({"done": row['done'] if row else 0, "target": 10})
