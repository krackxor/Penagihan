"""
Belum Bayar API - Sunter Dashboard Pro (Optimized & Smart)
Sinergi: 
1. High Value Filter: Hanya menampilkan data dengan nominal >= 300.000 (Sesuai Permintaan).
2. Smart Casting: Normalisasi NOMEN dan NOTAGIHAN ke TEXT agar link data MC, MB, & Ardebt tidak putus.
3. Rolling Target: Memastikan petugas tetap memiliki daftar kerja meskipun ganti bulan.
4. Watermark 4 Baris: Informasi penagihan tertanam pada foto bukti kunjungan.
"""

import os, sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def add_watermark(image_path, info):
    """
    Fungsi untuk menambahkan informasi penagihan langsung ke dalam foto (Watermark).
    Membantu Admin melakukan audit visual dengan cepat tanpa membuka database.
    """
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # Skala font otomatis (3.5% dari lebar gambar) agar proporsional di semua HP
        font_size = int(width * 0.035)
        
        font = None
        # Mencari font yang tersedia di sistem (Linux/Windows)
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()

        # Teks 4 baris: Petugas, ID Pelanggan, Status Kunjungan, dan Nominal
        text = (
            f"PETUGAS   : {info['petugas']}\n"
            f"IDPEL/NM : {info['nomen']} ({info['nama'][:12]}...)\n"
            f"STATUS    : {info['keterangan']}\n"
            f"TAGIHAN   : Rp {info['nominal']}"
        )

        margin = int(width * 0.04)
        line_height = font_size + 10
        y_pos = height - (line_height * 5) - margin

        # Efek Shadow Hitam agar tulisan kuning tetap terbaca di latar belakang putih/terang
        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        # Teks Utama Kuning Kontras
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FFFF00", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Watermark Error: {str(e)}")

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """Mengambil daftar nama petugas dari mapping rute untuk filter di dashboard admin."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC")
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """
    LOGIKA UTAMA DAFTAR KUNJUNGAN:
    - Memfilter data berdasarkan periode dan rute petugas.
    - Menghilangkan data yang sudah lunas di MB (Kantor) atau sudah tertagih hari ini (Collection).
    - SMART FILTER: Hanya menampilkan tagihan >= 300.000 agar petugas fokus pada target besar.
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 

    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Query Sinergi: Menghubungkan MC (Tagihan) dengan Rute Petugas
        # Ditambahkan filter p.nominal >= 300000
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, p.nomet, p.nominal, p.volume, p.rayon,
                   r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.nominal >= 300000  -- [SMART FILTER] Fokus High Value Target
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE CAST(mb.nomen AS TEXT) = CAST(p.nomen AS TEXT))
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE CAST(c.notag AS TEXT) = CAST(p.notagihan AS TEXT))
        """
        params = [req_periode]
        
        # Otorisasi: Petugas hanya bisa melihat rute miliknya sendiri
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif user_role == 'admin' and petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        # Logika Pencarian Nama/IDPEL
        if search_query:
            query += " AND (CAST(p.nomen AS TEXT) LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            # Filter Kotak 30 Hari: Jangan kunjungi rumah yang sudah dilaporkan dalam 1 bulan terakhir
            query += """ 
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE CAST(k.nomen AS TEXT) = CAST(p.nomen AS TEXT) 
                    AND k.created_at >= datetime('now', '-30 days')
                )
            """
        
        # Batasi data agar loading aplikasi di HP petugas tetap cepat (Ringan)
        query += " ORDER BY p.nominal DESC, p.pcez ASC LIMIT 25"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """
    Menyimpan laporan hasil kunjungan lapangan.
    Otomatis menyertakan data ARDEBT (Tunggakan Lama) agar laporan setoran ke SPV lebih lengkap.
    """
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
        
        # Menambahkan Watermark ke foto yang baru diupload
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
        
        # Mengambil rincian data pelanggan (MC + ARDEBT) untuk sinergi laporan WhatsApp
        cursor.execute("""
            SELECT p.nama, p.nomet, p.nominal as mc,
                COALESCE((SELECT jumlah FROM ardebt WHERE CAST(nomen AS TEXT) = CAST(p.nomen AS TEXT) LIMIT 1), 0) as ardebt,
                COALESCE((SELECT no_admin FROM rute_petugas WHERE pcez = p.pcez LIMIT 1), '628123456789') as wa_spv
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT) LIMIT 1
        """, (nomen,))
        master = cursor.fetchone()

        # Database Logging: Masukkan laporan ke tabel kunjungan_petugas
        cursor.execute("""
            INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, 
            janji_bayar_dt, foto_path, latitude, longitude, periode) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas_name, hasil, request.form.get('no_hp'), 
              request.form.get('keterangan'), request.form.get('janji_bayar_dt'),
              filename, request.form.get('latitude'), request.form.get('longitude'), 
              datetime.now().strftime('%m-%Y')))
        
        conn.commit()

        # Kirim respon ke frontend agar bisa membuka WhatsApp otomatis
        return APIResponse.success(data={
            "filename": filename, 
            "wa_data": {
                "nomen": nomen, "nama": master['nama'] if master else "-",
                "mc": master['mc'] if master else 0, "ardebt": master['ardebt'] if master else 0,
                "total": (master['mc'] or 0) + (master['ardebt'] or 0),
                "spv": master['wa_spv'], "status": hasil
            }
        })
    finally:
        conn.close()
