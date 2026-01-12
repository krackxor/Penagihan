"""
Belum Bayar API - Sunter Dashboard Pro (V9.0 Smart Sync Edition)
Pembaruan:
1. Autonomous Route Sync: Secara cerdas melakukan JOIN ke rute_petugas untuk mapping petugas terbaru.
2. Anti-Crash Logic: Menggunakan p.kubik dengan alias 'volume' agar sinkron dengan schema.sql.
3. Multi-Layer Filter: Memastikan data Ardebt, MB (Undue), dan Collection (Current) terfilter secara akurat.
4. Smart Watermarking: Penanaman metadata operasional pada bukti foto lapangan.
"""

import os, sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

# =========================================================================
# 1. LOGIKA WATERMARK CERDAS (VISUAL AUDIT)
# =========================================================================

def add_watermark(image_path, info):
    """Menanamkan informasi penagihan ke foto untuk validitas audit lapangan."""
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # Penyesuaian ukuran font dinamis berdasarkan resolusi gambar
        font_size = int(width * 0.035)
        font = None
        # Prioritas font sistem untuk konsistensi visual
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

        # Efek Shadow untuk keterbacaan di berbagai latar belakang foto
        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FFFF00", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Smart Watermark Failure: {str(e)}")

# =========================================================================
# 2. ENDPOINT DAFTAR TARGET (SMART SYNC LOGIC)
# =========================================================================

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """Mengambil daftar kerja harian yang tersinkronisasi dengan Master & Rute Petugas."""
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 
    petugas_filter = request.args.get('petugas')
    
    # Standarisasi Periode (MM-YYYY) untuk Global Sync
    raw_period = request.args.get('periode') or datetime.now().strftime('%m-%Y')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # QUERY SINERGI V9.0: 
        # Mengintegrasikan master_pelanggan dengan rute_petugas (Hasil upload Rute RL JS)
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, p.nomet, p.nominal, 
                   p.kubik as volume, p.rayon,
                   COALESCE(r.petugas, 'Belum Terplot') as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.nominal >= 300000 
            AND p.status_lunas = 0
            -- PROTEKSI: Memastikan tagihan lama (Ardebt) tidak muncul di daftar Current
            AND p.nomen NOT IN (SELECT DISTINCT nomen FROM ardebt)
            -- SYNC CHECK: Validasi lunas di Master Bayar (Bank)
            AND NOT EXISTS (
                SELECT 1 FROM master_bayar mb 
                WHERE mb.nomen = p.nomen AND mb.periode = p.periode
            )
            -- SYNC CHECK: Validasi lunas di Collection Harian (Lapangan)
            AND NOT EXISTS (
                SELECT 1 FROM collection_harian ch 
                WHERE ch.nomen = p.nomen AND ch.periode = p.periode
            )
        """
        params = [raw_period]
        
        # Filter berdasarkan hak akses atau pilihan admin
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        # Logika Pencarian Dinamis
        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            # Auto-Hide: Menyembunyikan data yang sudah dikunjungi hari ini
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
# 3. ENDPOINT PETUGAS TABS (UI SYNC)
# =========================================================================

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """Mengambil daftar petugas yang aktif dari tabel rute untuk filter frontend."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Mengambil daftar petugas unik dari hasil upload rute terbaru
        cursor.execute("""
            SELECT DISTINCT petugas 
            FROM rute_petugas 
            WHERE petugas IS NOT NULL AND petugas != '' 
            ORDER BY petugas ASC
        """)
        result = [row['petugas'] for row in cursor.fetchall()]
        return jsonify(result)
    finally:
        conn.close()

# =========================================================================
# 4. ENDPOINT LAPOR (OPERATIONAL SNAPSHOT)
# =========================================================================

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Mencatat aktivitas kunjungan lapangan petugas ke dalam audit trail."""
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
        
        # Eksekusi Watermark dengan informasi operasional lengkap
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
        # Injeksi data kunjungan ke database audit
        cursor.execute("""
            INSERT INTO kunjungan_petugas (
                nomen, petugas_name, keterangan, no_hp, catatan, 
                foto_path, latitude, longitude, periode
            ) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas_name, hasil, request.form.get('no_hp'), 
              request.form.get('keterangan'), filename, 
              request.form.get('latitude'), request.form.get('longitude'), 
              datetime.now().strftime('%m-%Y')))
        
        conn.commit()
        return APIResponse.success(message="Laporan kunjungan tersimpan.")
    finally:
        conn.close()
