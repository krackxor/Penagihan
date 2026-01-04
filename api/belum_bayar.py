import os
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import sqlite3

belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def apply_pro_watermark(image_path, data):
    """Watermark Profesional dengan penyesuaian ukuran otomatis"""
    try:
        img = Image.open(image_path)
        if img.mode in ("RGBA", "P"): 
            img = img.convert("RGB")
        
        draw = ImageDraw.Draw(img, "RGBA")
        width, height = img.size
        
        # Overlay di bagian bawah (22% dari tinggi gambar)
        overlay_h = int(height * 0.22)
        draw.rectangle([(0, height - overlay_h), (width, height)], fill=(0, 0, 0, 180))

        # Pengaturan Font (Menggunakan ukuran relatif terhadap gambar)
        font_size = int(overlay_h * 0.18)
        try:
            # Pastikan path font benar sesuai OS atau gunakan default
            font = ImageFont.truetype("arial.ttf", font_size)
            font_small = ImageFont.truetype("arial.ttf", int(font_size * 0.75))
        except:
            font = ImageFont.load_default()
            font_small = ImageFont.load_default()

        margin = 40
        curr_y = height - overlay_h + 20
        
        # Informasi Utama
        petugas_txt = str(data.get('petugas', 'OFFICER')).upper()
        draw.text((margin, curr_y), f"PETUGAS: {petugas_txt} | {data['nomen']}", fill=(255, 255, 255), font=font)
        draw.text((margin, curr_y + font_size + 10), f"PELANGGAN: {data['nama']}", fill=(255, 215, 0), font=font_small)
        draw.text((margin, curr_y + (font_size*2) + 15), f"STATUS: {data['status']} | Rp {data['nominal']}", fill=(255, 255, 255), font=font_small)
        draw.text((margin, curr_y + (font_size*3) + 20), f"WAKTU: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", fill=(0, 255, 127), font=font_small)
        
        # Copyright Tag
        draw.text((width // 2 - 150, height - 35), "© KHOIRUL ANWAR - PENAGIHAN SYSTEM", fill=(200, 200, 200, 150), font=font_small)
        
        img.save(image_path, "JPEG", quality=85)
    except Exception as e:
        print(f"Watermark Error: {e}")

def register_belum_bayar_routes(app, get_db):
    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list():
        db = get_db()
        petugas_filter = request.args.get('petugas', 'all')
        
        # Query utama yang dioptimalkan
        # Join langsung pada pcez karena sudah dibersihkan saat upload
        query = """
            SELECT 
                m.nomen, m.nama, m.nominal, m.pcez, m.block,
                COALESCE(NULLIF(r.petugas, ''), 'Belum Diatur') as nama_petugas
            FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            LEFT JOIN kunjungan_petugas k ON m.nomen = k.nomen
            WHERE m.tipe = 'MC' 
            AND k.nomen IS NULL
        """
        params = []
        
        if petugas_filter != 'all' and petugas_filter.strip() != '':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 100"
        
        rows = db.execute(query, params).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_tabs():
        db = get_db()
        # ✅ QUERY YANG DIPERBAIKI - Menangani berbagai format invalid
        query = """
            SELECT DISTINCT petugas 
            FROM rute_petugas 
            WHERE petugas IS NOT NULL 
            AND TRIM(UPPER(petugas)) NOT IN ('', 'NAN', 'NONE', 'NULL', '-', 'N/A', 'NA')
            AND LENGTH(TRIM(petugas)) >= 2
            ORDER BY petugas ASC
        """
        rows = db.execute(query).fetchall()
        return jsonify([row['petugas'] for row in rows])

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan():
        db = get_db()
        try:
            f = request.form
            file = request.files.get('foto')
            
            if not file:
                return jsonify({"error": "Foto wajib diunggah"}), 400

            # Penamaan file yang lebih aman
            nomen = f.get('nomen')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{nomen}_{timestamp}.jpg"
            path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            
            file.save(path)

            # Terapkan Watermark
            apply_pro_watermark(path, {
                'petugas': f.get('petugas'), 
                'nomen': nomen,
                'nama': f.get('nama_pelanggan'), 
                'nominal': f.get('nominal_val'),
                'status': f.get('keterangan')
            })

            # Simpan ke Database
            db.execute("""
                INSERT INTO kunjungan_petugas (
                    nomen, petugas_name, keterangan, no_hp, 
                    catatan, janji_bayar_dt, foto_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nomen, f.get('petugas'), f.get('keterangan'), f.get('no_hp'), 
                f.get('catatan'), f.get('janji_bayar_dt'), filename, datetime.now()
            ))
            
            db.commit()
            return jsonify({"status": "success", "filename": filename})
            
        except Exception as e:
            db.rollback()
            return jsonify({"error": str(e)}), 500
