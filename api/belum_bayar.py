import os
import socket
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def get_server_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except: ip = 'localhost'
    finally: s.close()
    return ip

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_petugas_tabs():
        db = get_db()
        rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC").fetchall()
        return jsonify([row['petugas'] for row in rows])

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        petugas = request.args.get('petugas', '')
        search = request.args.get('search', '')
        query = """
            SELECT m.nomen, m.nama, m.pcez, m.block, m.no_hp, r.petugas,
                   (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total
            FROM master_pelanggan m
            INNER JOIN rute_petugas r ON m.pcez = r.pcez
            LEFT JOIN ardebt a ON m.nomen = a.nomen
            LEFT JOIN collection_harian c ON m.nomen = c.nomen AND m.periode_bulan = c.periode_bulan
            WHERE c.id IS NULL
        """
        params = []
        if petugas and petugas != 'all':
            query += " AND r.petugas = ?"; params.append(petugas)
        if search:
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"; params.extend([f'%{search}%', f'%{search}%'])
        
        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 10"
        return jsonify([dict(row) for row in db.execute(query, params).fetchall()])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        no_hp = request.form.get('no_hp')
        lat = request.form.get('lat')
        lng = request.form.get('lng')
        foto = request.files.get('foto')

        filename = None
        photo_url = "Tanpa Foto"
        maps_url = f"https://www.google.com/maps?q={lat},{lng}"

        if foto:
            filename = f"BUKTI_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            
            # PROSES WATERMARK
            img = Image.open(foto)
            img = img.convert("RGB")
            img.thumbnail((1024, 1024))
            draw = ImageDraw.Draw(img)
            
            waktu = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            text = f"WAKTU: {waktu}\nPETUGAS: {petugas}\nGPS: {lat}, {lng}"
            
            # Draw simple background for text
            draw.rectangle([5, img.height-80, 450, img.height-5], fill=(0,0,0))
            draw.text((15, img.height-75), text, fill=(255,255,255))
            
            img.save(path, "JPEG", quality=80)
            photo_url = f"http://{get_server_ip()}:5000/uploads/kunjungan/{filename}"

        try:
            db.execute("INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, foto_path, created_at) VALUES (?,?,?,?,?)",
                       (nomen, petugas, keterangan, filename, datetime.now()))
            if no_hp:
                db.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (no_hp, nomen))
            db.commit()

            wa_text = (
                f"📢 *LAPORAN KUNJUNGAN ANTI-MANIPULASI*\n"
                f"--------------------------------\n"
                f"👷 *Petugas:* {petugas}\n"
                f"🏠 *Nama:* {nomen}\n"
                f"📝 *Hasil:* {keterangan}\n"
                f"📱 *No HP:* {no_hp if no_hp else '-'}\n\n"
                f"📍 *Lokasi GPS:* \n{maps_url}\n\n"
                f"📸 *Bukti Foto (Watermark):* \n{photo_url}\n"
                f"--------------------------------"
            )
            return jsonify({"status": "success", "wa_text": wa_text})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
