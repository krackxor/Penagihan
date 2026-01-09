"""
Belum Bayar API - Sunter Dashboard Pro (Updated)
Sinergi: 
1. Kunci Rute Otomatis: Berdasarkan session login (Mapping User Petugas).
2. Data Lengkap: Integrasi Nomet, Vol, Rayon, dan No Admin pada respon laporan.
3. Watermark 4 Baris: Petugas, Nomen, Keterangan, Nominal (Kuning Kontras).
4. Validasi Pintu Ganda: Filter lunas MB & Collection Harian secara real-time.
"""

import os, sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def add_watermark(image_path, info):
    """Menambahkan watermark informasi penagihan (4 Baris) di pojok kiri bawah."""
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # Skalasi font dinamis berdasarkan lebar gambar
        font_size = int(width * 0.035)
        
        font = None
        # Path font standar di Linux & Windows
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
            "C:\\Windows\\Fonts\\arialbd.ttf", 
            "arial.ttf"
        ]
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()

        # Konstruksi teks 4 baris
        text = (
            f"PETUGAS   : {info['petugas']}\n"
            f"IDPEL/NM : {info['nomen']} ({info['nama'][:12]}...)\n"
            f"STATUS    : {info['keterangan']}\n"
            f"TAGIHAN   : Rp {info['nominal']}"
        )

        margin = int(width * 0.04)
        line_height = font_size + 10
        x, y = margin, height - (line_height * 5) - margin

        # Efek Drop Shadow (Hitam) untuk keterbacaan di latar terang
        draw.multiline_text((x + 2, y + 2), text, font=font, fill="black", spacing=10)
        # Teks Utama (Kuning)
        draw.multiline_text((x, y), text, font=font, fill="#FFFF00", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Watermark Engine Error: {str(e)}")

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """Mengambil daftar petugas aktif untuk filter Admin."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC")
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """LOGIKA OPERASIONAL: Kunci Rute Petugas & Validasi Pintu Ganda (MB + Harian)."""
    user_role = session.get('role')
    user_petugas_id = session.get('petugas_id') 

    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Query Sinergi: Memastikan data yang muncul benar-benar belum bayar di bulan lalu (MB) dan hari ini (Coll)
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, p.nomet, p.nominal, p.volume, p.rayon,
                   r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = p.notagihan)
        """
        params = [req_periode]
        
        # Keamanan Level 3: Kunci data rute jika user adalah petugas
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif user_role == 'admin' and petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ? OR p.nomet LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        else:
            # Filter Kotak 30 Hari: Jangan tagih rumah yang sama dua kali dalam sebulan jika sudah dilaporkan
            query += """ 
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE k.nomen = p.nomen 
                    AND k.created_at >= datetime('now', '-30 days')
                )
            """
        
        # Batasi 20 data agar aplikasi ringan di mobile
        query += " ORDER BY p.pcez ASC, p.nomen ASC LIMIT 20"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Simpan laporan lapangan & siapkan data integrasi untuk WA Blast/Laporan WA."""
    nomen = request.form.get('idpel')
    petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil')
    foto = request.files.get('foto')
    
    if not nomen or not hasil:
        return APIResponse.error("IDPEL dan Hasil Kunjungan wajib diisi", code=400)
    
    filename = None
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        filename = f"LOG_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        
        # Proses Watermark Sinergi
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
        
        # Snapshot Data Sinergi (Mengambil rincian MC & Ardebt terbaru)
        cursor.execute("""
            SELECT p.nama, p.nomet, p.rayon, p.volume as vol, p.nominal as mc, p.pcez,
                COALESCE((SELECT jumlah FROM ardebt WHERE nomen = p.nomen LIMIT 1), 0) as ardebt,
                COALESCE((SELECT no_admin FROM rute_petugas WHERE pcez = p.pcez LIMIT 1), '628123456789') as wa_spv
            FROM master_pelanggan p
            WHERE p.nomen = ? ORDER BY p.periode DESC LIMIT 1
        """, (nomen,))
        master = cursor.fetchone()

        # Database Logging: Lacak laporan hari ini untuk mencegah duplikasi/revisi
        cursor.execute("SELECT id FROM kunjungan_petugas WHERE nomen = ? AND date(created_at) = date('now')", (nomen,))
        existing = cursor.fetchone()
        
        data_db = (
            nomen, petugas_name, hasil, request.form.get('no_hp'), 
            request.form.get('keterangan'), request.form.get('janji_bayar_dt'),
            filename, request.form.get('latitude'), request.form.get('longitude'), 
            datetime.now().strftime('%m-%Y')
        )

        if existing:
            cursor.execute("""
                UPDATE kunjungan_petugas SET keterangan=?, no_hp=?, catatan=?, janji_bayar_dt=?, 
                foto_path=COALESCE(?, foto_path), created_at=CURRENT_TIMESTAMP WHERE id=?
            """, (hasil, request.form.get('no_hp'), request.form.get('keterangan'), 
                  request.form.get('janji_bayar_dt'), filename, existing['id']))
        else:
            cursor.execute("""
                INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, 
                janji_bayar_dt, foto_path, latitude, longitude, periode) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data_db)
        
        conn.commit()

        # Output Data untuk diolah Frontend menjadi pesan WA
        return APIResponse.success(data={
            "filename": filename, 
            "wa_data": {
                "nomen": nomen, "nama": master['nama'] if master else "-",
                "nomet": master['nomet'] if master else "-", "rayon": master['rayon'] if master else "-",
                "mc": master['mc'] if master else 0, "ardebt": master['ardebt'] if master else 0,
                "total": (master['mc'] or 0) + (master['ardebt'] or 0),
                "vol": master['vol'] if master else 0, "spv": master['wa_spv'],
                "status": hasil, "petugas": petugas_name
            }
        })
    finally:
        conn.close()
