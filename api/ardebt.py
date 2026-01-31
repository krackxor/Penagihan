"""
Ardebt (Tagihan Berekor) API - V7.2 (Snapshot & Audit Feature Sync)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FEATURE SYNC: Menambahkan fitur Snapshot Foto & Watermark (Sama dengan Belum Bayar).
2. ✅ FEATURE SYNC: Menambahkan Progres Audit khusus untuk kategori Ardebt.
3. ✅ FIX: Schema Sync - Penambahan kolom 'nomet' pada pelaporan kunjungan.
4. Global History Sync: Konsistensi penarikan data Ardebt lintas periode.
"""

import os
from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

ardebt_bp = Blueprint('ardebt', __name__)

# =========================================================================
# 1. LOGIKA WATERMARK (SINKRON DENGAN BELUM BAYAR)
# =========================================================================
def add_watermark(image_path, info):
    """Menanamkan informasi penagihan berekor ke foto bukti lapangan."""
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
            f"PETUGAS (AR) : {info['petugas']}\n"
            f"IDPEL/NM     : {info['nomen']} ({info['nama'][:12]}...)\n"
            f"STATUS       : {info['keterangan']}\n"
            f"TAGIHAN AR   : Rp {info['nominal']}"
        )

        margin = int(width * 0.04)
        line_height = font_size + 10
        y_pos = height - (line_height * 5) - margin

        # Efek Shadow dan Warna Orange-Red untuk pembeda kategori Ardebt
        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FF4500", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Ardebt Watermark Failure: {str(e)}")

# =========================================================================
# 2. PROGRES AUDIT ARDEBT
# =========================================================================
@ardebt_bp.route('/progress', methods=['GET'])
def get_ardebt_progress():
    """Menghitung progres penagihan khusus untuk data berekor."""
    user_petugas_id = session.get('petugas_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        active_period = get_active_target_period(cursor)
        
        # Hitung Total Target Ardebt yang belum lunas
        target_query = """
            SELECT COUNT(a.nomen) as total 
            FROM ardebt a 
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen 
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez 
            WHERE p.periode = ? AND p.status_lunas = 0
        """
        params = [active_period]
        if user_petugas_id:
            target_query += " AND r.petugas = ?"
            params.append(user_petugas_id)
            
        total_target = cursor.execute(target_query, params).fetchone()['total'] or 0
        
        # Hitung Realisasi hari ini (Join ke ardebt untuk memastikan kategori)
        real_query = """
            SELECT COUNT(DISTINCT k.nomen) as total 
            FROM kunjungan_petugas k 
            INNER JOIN ardebt a ON k.nomen = a.nomen 
            WHERE DATE(k.created_at) = DATE('now')
        """
        total_real = cursor.execute(real_query).fetchone()['total'] or 0
        
        percentage = round((total_real / total_target * 100), 1) if total_target > 0 else 0
        return jsonify({
            "total_target": total_target, 
            "total_realisasi": total_real, 
            "percentage": percentage
        })
    finally:
        conn.close()

# =========================================================================
# 3. ENDPOINT DAFTAR KERJA (V7.2)
# =========================================================================
@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    search_query = request.args.get('search', '').strip()
    petugas_filter = request.args.get('petugas', 'all')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        active_period = get_active_target_period(cursor)

        query = """
            SELECT 
                a.nomen, a.periode_bill as rincian_periode, a.jumlah as nominal_ardebt,
                p.nama, p.alamat, COALESCE(p.nomet, '-') as no_seri_meter, 
                p.tarif, p.kubik as pemakaian_air, p.pcez, p.nominal as nominal_mc,
                COALESCE(r.petugas, 'UNMAPPED') as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? AND p.status_lunas = 0
            AND p.nomen NOT IN (SELECT nomen FROM master_bayar WHERE periode = ?)
            AND p.nomen NOT IN (SELECT nomen FROM collection_harian WHERE periode = ?)
        """
        params = [active_period, active_period, active_period]

        if not search_query:
            query += """ AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = p.nomen AND DATE(k.created_at) = DATE('now')
            )"""

        if user_role == 'petugas' and user_petugas_id:
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        query += " ORDER BY p.kubik DESC LIMIT 50"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

# =========================================================================
# 4. ENDPOINT LAPOR (SNAPSHOT ARDEBT)
# =========================================================================
@ardebt_bp.route('/lapor', methods=['POST'])
def lapor_ardebt():
    """Snapshot operasional khusus untuk kategori Ardebt."""
    nomen = request.form.get('idpel')
    nomet = request.form.get('nomet') or "-"
    petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil')
    foto = request.files.get('foto')
    
    if not nomen or not hasil:
        return APIResponse.error("Data tidak lengkap", code=400)
    
    filename = None
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        filename = f"AR_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        
        add_watermark(foto_path, {
            'petugas': petugas_name or "Petugas AR", 
            'nomen': nomen,
            'nama': request.form.get('nama_pelanggan') or "-",
            'keterangan': hasil,
            'nominal': request.form.get('nominal_display') or "0"
        })

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # FIX: Menyertakan nomet agar tidak terjadi error transmisi
        cursor.execute("""
            INSERT INTO kunjungan_petugas (
                nomen, nomet, petugas_name, keterangan, no_hp, catatan, 
                foto_path, latitude, longitude, periode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (nomen, nomet, petugas_name, hasil, request.form.get('no_hp'), 
              request.form.get('keterangan'), filename, 
              request.form.get('latitude'), request.form.get('longitude'), 
              datetime.now().strftime('%m-%Y')))
        conn.commit()
        return APIResponse.success(message="Laporan Ardebt berhasil dikirim.")
    except Exception as e:
        return APIResponse.error(f"Gagal kirim snapshot Ardebt: {str(e)}")
    finally:
        conn.close()

# Pastikan fungsi pendukung tetap ada
def get_active_target_period(cursor):
    res = cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    return res['periode'] if res else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/petugas', methods=['GET'])
def get_list_petugas_ardebt():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC"
        cursor.execute(query)
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    finally:
        conn.close()
