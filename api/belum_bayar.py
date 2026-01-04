import os
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import sqlite3

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def apply_pro_watermark(image_path, data):
    """Fungsi Watermark Profesional dengan Copyright Khoirul Anwar"""
    img = Image.open(image_path)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    
    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size
    
    # 1. Overlay Hitam Semi-Transparan di bawah (20% tinggi foto)
    overlay_h = int(height * 0.22)
    draw.rectangle([(0, height - overlay_h), (width, height)], fill=(0, 0, 0, 180))

    # 2. Setup Font
    try:
        # Gunakan arial atau font default sistem
        font_l = ImageFont.truetype("arial.ttf", int(overlay_h * 0.20))
        font_s = ImageFont.truetype("arial.ttf", int(overlay_h * 0.12))
        font_cp = ImageFont.truetype("arial.ttf", int(overlay_h * 0.10))
    except:
        font_l = font_s = font_cp = ImageFont.load_default()

    # 3. Teks Data Laporan (Sisi Kiri)
    margin = 40
    curr_y = height - overlay_h + 20
    waktu = datetime.now().strftime('%d/%m/%Y %H:%M:%S WIB')
    
    draw.text((margin, curr_y), f"PETUGAS: {data['petugas']} | {data['nomen']}", fill=(255, 255, 255), font=font_l)
    draw.text((margin, curr_y + int(overlay_h * 0.22)), f"PELANGGAN: {data['nama']}", fill=(255, 215, 0), font=font_s)
    draw.text((margin, curr_y + int(overlay_h * 0.38)), f"STATUS: {data['status']} | TAGIHAN: Rp {data['nominal']}", fill=(255, 255, 255), font=font_s)
    draw.text((margin, curr_y + int(overlay_h * 0.54)), f"WAKTU: {waktu}", fill=(0, 255, 127), font=font_s)

    # 4. COPYRIGHT KHOIRUL ANWAR (Bawah Tengah)
    cp_text = "© COPYRIGHT KHOIRUL ANWAR - SUNTER PRO SYSTEM"
    bbox = draw.textbbox((0, 0), cp_text, font=font_cp)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, height - 35), cp_text, fill=(200, 200, 200), font=font_cp)

    img.save(image_path, "JPEG", quality=85)

def register_belum_bayar_routes(app, get_db):
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list():
        db = get_db()
        petugas = request.args.get('petugas', 'all')
        query = """
            SELECT m.*, r.petugas as nama_petugas FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
            WHERE m.tipe = 'MC' AND k.nomen IS NULL
        """
        params = []
        if petugas != 'all' and petugas != '':
            query += " AND r.petugas = ?"
            params.append(petugas)
        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 25"
        return jsonify([dict(row) for row in db.execute(query, params).fetchall()])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan():
        db = get_db()
        f = request.form
        file = request.files.get('foto')
        
        # Save Foto
        filename = f"{f.get('nomen')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
        file.save(path)

        # Proses Watermark Profesional
        wm_data = {
            'petugas': f.get('petugas'), 'nomen': f.get('nomen'),
            'nama': f.get('nama_pelanggan'), 'nominal': f.get('nominal_val'),
            'status': f.get('keterangan')
        }
        apply_pro_watermark(path, wm_data)

        # Insert DB
        db.execute("""
            INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, janji_bayar_dt, foto_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (f.get('nomen'), f.get('petugas'), f.get('keterangan'), f.get('no_hp'), f.get('catatan'), f.get('janji_bayar_dt'), filename, datetime.now()))
        db.commit()
        return jsonify({"status": "success", "filename": filename})

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_tabs():
        db = get_db()
        rows = db.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL AND petugas != '' ORDER BY petugas ASC").fetchall()
        return jsonify([row['petugas'] for row in rows])
