"""
Belum Bayar API - Sunter Dashboard Pro (Updated)
Sinergi: 
1. Kunci Rute Otomatis berdasarkan session login (Mapping User).
2. Data Lengkap: Nomet, Vol, Rayon, dan No Admin pada respon laporan.
3. Watermark 4 Baris: Petugas, Nomen, Keterangan, Nominal.
"""

import os, sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def add_watermark(image_path, info):
    """Menambahkan watermark informasi penagihan (4 Baris)."""
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        font_size = int(width * 0.04)
        
        font = None
        for path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:\\Windows\\Fonts\\arialbd.ttf", "arial.ttf"]:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()

        text = (
            f"PETUGAS: {info['petugas']}\n"
            f"NOMEN: {info['nomen']} ({info['nama'][:15]})\n"
            f"KETERANGAN: {info['keterangan']}\n"
            f"NOMINAL: Rp {info['nominal']}"
        )

        margin = int(width * 0.03)
        x, y = margin, height - (font_size * 6) - margin

        draw.multiline_text((x + 2, y + 2), text, font=font, fill="black", spacing=8) # Shadow
        draw.multiline_text((x, y), text, font=font, fill="yellow", spacing=8) # Teks Kuning
        img.save(image_path, quality=90)
    except Exception as e:
        current_app.logger.error(f"❌ Watermark Error: {str(e)}")

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """Mengambil daftar petugas unik untuk filter dropdown (Admin)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas != '' ORDER BY petugas ASC")
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """LOGIKA OPERASIONAL: Kunci Rute Petugas & Filter 30 Hari."""
    # AMBIL DATA SESSION (SINERGI LOGIN)
    user_role = session.get('role')
    user_petugas_id = session.get('petugas_id') 

    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, p.nomet, p.nominal, p.volume, p.rayon,
                   r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE (p.periode = ? OR (p.periode < ? AND p.tipe = 'MC'))
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = p.notagihan)
        """
        params = [req_periode, req_periode]
        
        # --- LOGIKA KUNCI RUTE (3 LEVEL LOGIN) ---
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
            query += """ 
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE k.nomen = p.nomen 
                    AND k.created_at >= datetime('now', '-30 days')
                )
                AND NOT EXISTS (SELECT 1 FROM ardebt a WHERE a.nomen = p.nomen)
            """
        
        query += " ORDER BY p.pcez ASC, p.nomen ASC LIMIT 20"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Simpan laporan dengan data sinergi untuk WhatsApp Admin."""
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
        
        add_watermark(foto_path, {
            'petugas': petugas_name or "Petugas Lapangan", 
            'nomen': nomen,
            'nama': request.form.get('nama_pelanggan') or "-",
            'keterangan': hasil,
            'nominal': request.form.get('nominal_display') or "0"
        })

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # DATA SINERGI UNTUK WA_DATA
        cursor.execute("""
            SELECT p.nama, p.nomet, p.rayon, p.volume as vol, p.nominal as mc,
                COALESCE((SELECT jumlah FROM ardebt WHERE nomen = p.nomen LIMIT 1), 0) as ardebt,
                COALESCE((SELECT no_admin FROM rute_petugas WHERE petugas = ? LIMIT 1), '628123456789') as no_admin
            FROM master_pelanggan p
            WHERE p.nomen = ? ORDER BY p.periode DESC LIMIT 1
        """, (petugas_name, nomen))
        master = cursor.fetchone()

        # CEK REVISI HARI INI
        cursor.execute("SELECT id FROM kunjungan_petugas WHERE nomen = ? AND date(created_at) = date('now')", (nomen,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE kunjungan_petugas SET keterangan = ?, catatan = ?, no_hp = ?, janji_bayar_dt = ?, 
                foto_path = COALESCE(?, foto_path), created_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (hasil, request.form.get('keterangan'), request.form.get('no_hp'), 
                  request.form.get('janji_bayar_dt'), filename, existing['id']))
        else:
            cursor.execute("""
                INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, 
                janji_bayar_dt, foto_path, latitude, longitude, periode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (nomen, petugas_name, hasil, request.form.get('no_hp'), 
                  request.form.get('keterangan'), request.form.get('janji_bayar_dt'), 
                  filename, request.form.get('latitude'), request.form.get('longitude'), datetime.now().strftime('%m-%Y')))
        
        conn.commit()

        mc_val = master['mc'] if master else 0
        ardebt_val = master['ardebt'] if master else 0
        
        return APIResponse.success(data={
            "filename": filename, 
            "revisi": bool(existing),
            "wa_data": {
                "nomen": nomen, "nama": master['nama'] if master else "-",
                "nomet": master['nomet'] if master else "-", "rayon": master['rayon'] if master else "-",
                "vol": master['vol'] if master else "0", "mc": mc_val, "ardebt": ardebt_val,
                "total": (mc_val + ardebt_val), "hp": request.form.get('no_hp'),
                "status": hasil, "catatan": request.form.get('keterangan') or "-",
                "petugas": petugas_name, "no_admin": master['no_admin'] if master else "628123456789"
            }
        })
    finally:
        conn.close()

@belum_bayar_bp.route('/ardebt', methods=['GET'])
def get_tagihan_berekor():
    user_role = session.get('role')
    user_petugas_id = session.get('petugas_id')
    p_filter, search = request.args.get('petugas'), request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT a.nomen, p.nama, p.pcez, p.nomet, p.rayon, r.petugas as nama_petugas,
                   a.periode_bill, a.jumlah, a.volume
            FROM ardebt a INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez WHERE 1=1
        """
        params = []
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif user_role == 'admin' and p_filter and p_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(p_filter)

        if search:
            query += " AND (a.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        else:
            query += " AND NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = a.nomen AND k.created_at >= datetime('now', '-30 days'))"
            
        cursor.execute(query + " ORDER BY a.periode_bill ASC LIMIT 20", params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()
