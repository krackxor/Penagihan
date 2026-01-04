import os
import socket
import pytz
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from PIL import Image, ImageDraw

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def get_jakarta_time():
    tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(tz)

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
                   (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total,
                   (SELECT COUNT(*) FROM kunjungan_petugas k 
                    WHERE k.nomen = m.nomen 
                    AND date(k.created_at) = date('now')) as is_visited
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
        
        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 20"
        return jsonify([dict(row) for row in db.execute(query, params).fetchall()])

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

            query = "SELECT nama, nominal FROM master_pelanggan WHERE nomen = ?"
            pel = db.execute(query, (nomen,)).fetchone()
            nama_pel = pel['nama'] if pel else "-"
            nominal_tagihan = f"{pel['nominal']:,}" if pel else "0"

            waktu_jkt = get_jakarta_time()
            waktu_str = waktu_jkt.strftime('%d/%m/%Y %H:%M:%S')
            
            filename = None
            photo_url = "Tanpa Foto"
            # URL Google Maps diperbaiki: Menghapus angka '0' di depan koordinat
            maps_url = f"https://www.google.com/maps?q={lat},{lng}"

            if foto:
                filename = f"BUKTI_{nomen}_{waktu_jkt.strftime('%Y%m%d_%H%M%S')}.jpg"
                save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
                
                img = Image.open(foto).convert("RGB")
                img.thumbnail((1024, 1024))
                draw = ImageDraw.Draw(img)
                
                wm_text = (
                    f"WAKTU: {waktu_str} WIB\n"
                    f"PETUGAS: {petugas}\n"
                    f"NOMEN: {nomen}\n"
                    f"TAGIHAN: Rp {nominal_tagihan}\n"
                    f"GPS: {lat}, {lng}"
                )
                
                draw.rectangle([10, img.height - 130, 600, img.height - 10], fill=(0, 0, 0))
                draw.text((20, img.height - 120), wm_text, fill=(255, 255, 255))
                img.save(save_path, "JPEG", quality=85)
                photo_url = f"http://{get_server_ip()}:5000/uploads/kunjungan/{filename}"

            db.execute("INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, foto_path, latitude, longitude, created_at) VALUES (?,?,?,?,?,?,?)",
                       (nomen, petugas, keterangan, filename, lat, lng, waktu_jkt))
            
            if no_hp:
                db.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (no_hp, nomen))
            db.commit()

            wa_text = (
                f"📢 *LAPORAN PENAGIHAN*\n"
                f"--------------------------------\n"
                f"👷 *Petugas:* {petugas}\n"
                f"🆔 *Nomen:* {nomen}\n"
                f"🏠 *Nama:* {nama_pel}\n"
                f"💰 *Tagihan:* Rp {nominal_tagihan}\n"
                f"📝 *Hasil:* {keterangan}\n"
                f"⏰ *Waktu:* {waktu_str} WIB\n\n"
                f"📍 *Lokasi GPS:* \n{maps_url}\n\n"
                f"📸 *Bukti Foto:* \n{photo_url}\n"
                f"--------------------------------"
            )
            return jsonify({"status": "success", "wa_text": wa_text})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
