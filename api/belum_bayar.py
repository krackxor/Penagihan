"""
Belum Bayar API - Sunter Dashboard Pro (V8.2 Sinergi & Global Sync)
Pembaruan:
1. Sinkronisasi Kolom: Mengganti p.volume menjadi p.kubik sesuai schema.sql.
2. Fix 404: Menambahkan endpoint /petugas-tabs untuk kebutuhan filter di frontend.
3. Anti-NULL Payment Guard: Memastikan tagihan lunas tidak muncul kembali.
4. Ardebt Exclusion: Memisahkan data tunggakan lama secara mutlak.
"""

import os, sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

# =========================================================================
# 1. LOGIKA WATERMARK (BUKTI VISUAL LAPANGAN)
# =========================================================================

def add_watermark(image_path, info):
    """ Fungsi Watermark: Menanamkan info penagihan ke foto. """
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        font_size = int(width * 0.035)
        font = None
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()

        text = (
            f"PETUGAS   : {info['petugas']}\n"
            f"IDPEL/NM : {info['nomen']} ({info['nama'][:12]}...)\n"
            f"STATUS    : {info['keterangan']}\n"
            f"TAGIHAN   : Rp {info['nominal']}"
        )

        margin = int(width * 0.04)
        line_height = font_size + 10
        y_pos = height - (line_height * 5) - margin

        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FFFF00", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Watermark Error: {str(e)}")

# =========================================================================
# 2. ENDPOINT DAFTAR TARGET (FIXED: KUBIK & SYNC LOGIC)
# =========================================================================

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """ [DAFTAR KERJA HARIAN: FOKUS CURRENT & MURNI BELUM BAYAR] """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 
    petugas_filter = request.args.get('petugas')
    
    # Konsistensi format periode MM-YYYY
    raw_period = request.args.get('periode') or datetime.now().strftime('%m-%Y')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # QUERY SINERGI (V8.2): Menggunakan p.kubik sesuai schema.sql
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, p.nomet, p.nominal, p.kubik as volume, p.rayon,
                   r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.nominal >= 300000 
            AND p.status_lunas = 0
            -- Kecualikan data tunggakan lama (Ardebt)
            AND p.nomen NOT IN (SELECT DISTINCT nomen FROM ardebt)
            -- Cek sinkronisasi pembayaran di MB dan Collection
            AND NOT EXISTS (
                SELECT 1 FROM master_bayar mb 
                WHERE mb.nomen = p.nomen AND mb.periode = p.periode
            )
            AND NOT EXISTS (
                SELECT 1 FROM collection_harian ch 
                WHERE ch.nomen = p.nomen AND ch.periode = p.periode
            )
        """
        params = [raw_period]
        
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            # Sembunyikan jika sudah dikunjungi pada periode ini
            query += """ 
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE k.nomen = p.nomen AND k.periode = p.periode
                )
            """
        
        query += " ORDER BY p.nominal DESC LIMIT 100"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

# =========================================================================
# 3. ENDPOINT FILTER TABS (FIX: MENGATASI 404)
# =========================================================================

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """ Menyediakan daftar petugas unik untuk filter di UI. """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC")
        result = [row['petugas'] for row in cursor.fetchall()]
        return jsonify(result)
    finally:
        conn.close()

# =========================================================================
# 4. ENDPOINT LAPOR (SNAPSHOT OPERASIONAL)
# =========================================================================

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """ Mencatat hasil kunjungan lapangan petugas. """
    nomen = request.form.get('idpel')
    petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil')
    foto = request.files.get('foto')
    
    if not nomen or not hasil:
        return APIResponse.error("Data tidak lengkap", code=400)
    
    filename = None
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        filename = f"LOG_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        
        add_watermark(foto_path, {
            'petugas': petugas_name or "Petugas", 
            'nomen': nomen,
            'nama': request.form.get('nama_pelanggan') or "-",
            'keterangan': hasil,
            'nominal': request.form.get('nominal_display') or "0"
        })

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, 
            foto_path, latitude, longitude, periode) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas_name, hasil, request.form.get('no_hp'), 
              request.form.get('keterangan'), filename, 
              request.form.get('latitude'), request.form.get('longitude'), 
              datetime.now().strftime('%m-%Y')))
        
        conn.commit()
        return APIResponse.success(message="Laporan kunjungan tersimpan.")
    finally:
        conn.close()
