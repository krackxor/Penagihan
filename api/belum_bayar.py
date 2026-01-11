"""
Belum Bayar API - Sunter Dashboard Pro (V7.0 Ultra-Fast Edition)
Sinergi & Smart Update:
1. Ultra-Fast Join: Menghapus CAST() agar database menggunakan INDEX secara maksimal.
2. High Value Filter: Fokus pada data dengan nominal >= 300.000 (Prioritas Penagihan).
3. Watermark 4 Baris: Injeksi data penagihan ke foto kunjungan untuk bukti audit visual.
4. Smart Auto-Hide: Data otomatis hilang jika sudah dibayar (MB/Collection) atau sudah dikunjungi.
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
    """
    Fungsi Watermark: Menanamkan info penagihan ke foto.
    """
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

        # Shadow & Text Utama
        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FFFF00", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Watermark Error: {str(e)}")

# =========================================================================
# 2. ENDPOINT DAFTAR TARGET (BELUM BAYAR CURRENT)
# =========================================================================

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """
    [DAFTAR KERJA HARIAN: FOKUS CURRENT >= 300K]
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 

    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Query Utama: Join Cepat (Tanpa CAST)
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, p.nomet, p.nominal, p.volume, p.rayon,
                   r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.nominal >= 300000 
            AND p.status_lunas = 0
            AND p.kubik > 0
        """
        params = [req_periode]
        
        # Otorisasi & Filter Admin
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        # Logika Pencarian & Smart Auto-Hide (Sudah Dikunjungi)
        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            query += """ 
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE k.nomen = p.nomen AND k.periode = p.periode
                )
            """
        
        query += " ORDER BY p.nominal DESC LIMIT 50"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

# =========================================================================
# 3. ENDPOINT LAPOR (SINERGI MC + ARDEBT)
# =========================================================================

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """
    Menyimpan laporan kunjungan dan menyertakan data ARDEBT (Tunggakan Lama) 
    untuk kalkulasi total tagihan saat dilaporkan ke SPV.
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
        
        # Sinergi Report: Ambil nominal MC saat ini dan tunggakan Ardebt
        cursor.execute("""
            SELECT p.nama, p.nominal as mc, p.pcez,
                COALESCE((SELECT jumlah FROM ardebt WHERE nomen = p.nomen LIMIT 1), 0) as ardebt,
                COALESCE((SELECT no_admin FROM rute_petugas WHERE pcez = p.pcez LIMIT 1), '628123456789') as wa_spv
            FROM master_pelanggan p
            WHERE p.nomen = ? ORDER BY p.id DESC LIMIT 1
        """, (nomen,))
        master = cursor.fetchone()

        # Database Logging
        cursor.execute("""
            INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, 
            foto_path, latitude, longitude, periode) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas_name, hasil, request.form.get('no_hp'), 
              request.form.get('keterangan'), filename, 
              request.form.get('latitude'), request.form.get('longitude'), 
              datetime.now().strftime('%m-%Y')))
        
        conn.commit()

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
