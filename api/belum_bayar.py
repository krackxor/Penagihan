import os
import sqlite3
import logging
from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def add_watermark(image_path, info):
    """Menambahkan watermark informasi penagihan secara robust."""
    try:
        img = Image.open(image_path)
        # Pastikan orientasi foto benar (mengatasi masalah rotasi otomatis pada beberapa smartphone)
        if hasattr(img, '_getexif'): img = Image.open(image_path) 
        
        draw = ImageDraw.Draw(img)
        width, height = img.size
        font_size = int(width * 0.035) # Ukuran proporsional
        
        # Mencari font yang tersedia di sistem secara berurutan
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf" # Support Windows dev environment
        ]
        
        font = None
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        if not font: font = ImageFont.load_default()

        text = (
            f"WAKTU: {info['waktu']}\n"
            f"PETUGAS: {info['petugas']}\n"
            f"NOMEN: {info['nomen']} ({info['nama'][:20]})\n"
            f"TAGIHAN: Rp {info['nominal']}"
        )

        margin = int(width * 0.02)
        # Menghitung posisi di pojok kiri bawah
        x = margin
        y = height - (font_size * 6) - margin

        # Gambar Shadow (Hitam) agar teks terbaca di background terang
        shadow = 2
        draw.multiline_text((x + shadow, y + shadow), text, font=font, fill="black", spacing=5)
        # Gambar Teks Utama (Kuning)
        draw.multiline_text((x, y), text, font=font, fill="yellow", spacing=5)
        
        img.save(image_path, quality=85) # Kompresi dikit agar hemat storage
        return True
    except Exception as e:
        current_app.logger.error(f"❌ Watermark Error: {str(e)}")
        return False

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """
    LOGIKA OPERASIONAL:
    - Kuota 20 data per petugas berdasarkan urutan PCEZ.
    - Sembunyikan Nomen yang sudah dikunjungi dalam 30 hari terakhir.
    """
    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, p.nomet, p.nominal, p.volume,
                   r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE (p.periode = ? OR (p.periode < ? AND p.tipe = 'MC'))
            
            -- Filter 1: Belum lunas (Validasi Pintu Ganda)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = p.notagihan)
            
            -- Filter 2: Sembunyikan jika sudah dikunjungi dalam 30 hari terakhir
            AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = p.nomen 
                AND k.created_at >= datetime('now', '-30 days')
            )
            
            -- Filter 3: Sembunyikan jika nomen ada di list Ardebt (pindah ke menu sebelah)
            AND NOT EXISTS (SELECT 1 FROM ardebt a WHERE a.nomen = p.nomen)
        """
        params = [req_periode, req_periode]
        
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY p.pcez ASC, p.nomen ASC LIMIT 20"
        
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Menyimpan laporan dengan fitur revisi otomatis (Upsert harian)."""
    nomen = request.form.get('idpel')
    petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil')
    foto = request.files.get('foto')
    
    if not nomen or not hasil:
        return APIResponse.error("ID Pelanggan dan Hasil wajib diisi", code=400)
    
    filename = None
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        
        ext = os.path.splitext(foto.filename)[1].lower()
        filename = f"LOG_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        
        # Proses Watermarking
        add_watermark(foto_path, {
            'waktu': datetime.now().strftime('%d/%m/%Y %H:%M WIB'),
            'petugas': petugas_name or "Petugas Lapangan", 
            'nomen': nomen,
            'nama': request.form.get('nama_pelanggan') or "-",
            'nominal': request.form.get('nominal_display') or "0"
        })

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Cek revisi harian (Berdasarkan Nomen + Tanggal Hari Ini)
        cursor.execute("""
            SELECT id FROM kunjungan_petugas 
            WHERE nomen = ? AND date(created_at, '+7 hours') = date('now', 'localtime')
        """, (nomen,))
        existing = cursor.fetchone()
        
        if existing:
            # UPDATE (REVISI)
            cursor.execute("""
                UPDATE kunjungan_petugas 
                SET keterangan = ?, catatan = ?, no_hp = ?, janji_bayar_dt = ?, 
                    foto_path = COALESCE(?, foto_path), created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (hasil, request.form.get('keterangan'), request.form.get('no_hp'), 
                  request.form.get('janji_bayar_dt'), filename, existing['id']))
        else:
            # INSERT BARU
            cursor.execute("""
                INSERT INTO kunjungan_petugas (
                    nomen, petugas_name, keterangan, no_hp, catatan, 
                    janji_bayar_dt, foto_path, latitude, longitude, periode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (nomen, petugas_name, hasil, request.form.get('no_hp'), 
                  request.form.get('keterangan'), request.form.get('janji_bayar_dt'), 
                  filename, request.form.get('latitude'), request.form.get('longitude'), 
                  datetime.now().strftime('%m-%Y')))
        
        conn.commit()
        return APIResponse.success(data={"filename": filename, "revisi": bool(existing)})
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@belum_bayar_bp.route('/ardebt', methods=['GET'])
def get_tagihan_berekor():
    """Mengambil rincian Ardebt dengan kuota 20 data dan LOGIKA 30 HARI."""
    petugas_filter = request.args.get('petugas')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT a.nomen, p.nama, p.pcez, r.petugas as nama_petugas,
                   a.periode_bill, a.jumlah, a.volume
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE 1=1
            
            -- Sembunyikan jika sudah dikunjungi dalam 30 hari terakhir
            AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = a.nomen 
                AND k.created_at >= datetime('now', '-30 days')
            )
        """
        params = []
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY a.periode_bill ASC LIMIT 20"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()
