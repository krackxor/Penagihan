"""
Belum Bayar API - Sunter Dashboard Pro (V9.2 Progres Audit Sync)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX: Schema Sync - Menambahkan kolom 'nomet' pada insert kunjungan_petugas.
2. ✅ FEATURE: Progres Audit - Menambahkan fungsi hitung persentase kunjungan harian.
3. Autonomous Route Sync: Secara cerdas melakukan JOIN ke rute_petugas untuk mapping petugas.
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
        
        font_size = int(width * 0.035)
        font = None
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()

        text = (
            f"PETUGAS    : {info['petugas']}\n"
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
        current_app.logger.error(f"❌ Smart Watermark Failure: {str(e)}")

# =========================================================================
# 2. ENDPOINT PROGRES AUDIT (NEW FEATURE)
# =========================================================================

@belum_bayar_bp.route('/progress', methods=['GET'])
def get_audit_progress():
    """Menghitung progres audit/kunjungan harian per petugas."""
    user_petugas_id = session.get('petugas_id')
    raw_period = datetime.now().strftime('%m-%Y')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Hitung Total Target Belum Lunas
        target_query = """
            SELECT COUNT(p.nomen) as total 
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? AND p.status_lunas = 0
        """
        params = [raw_period]
        if user_petugas_id:
            target_query += " AND r.petugas = ?"
            params.append(user_petugas_id)
            
        total_target = cursor.execute(target_query, params).fetchone()['total'] or 0
        
        # Hitung Realisasi Kunjungan Hari Ini
        realisasi_query = """
            SELECT COUNT(DISTINCT k.nomen) as total
            FROM kunjungan_petugas k
            LEFT JOIN rute_petugas r ON (SELECT pcez FROM master_pelanggan WHERE nomen = k.nomen LIMIT 1) = r.pcez
            WHERE k.periode = ? AND DATE(k.created_at) = DATE('now')
        """
        params_real = [raw_period]
        if user_petugas_id:
            realisasi_query += " AND r.petugas = ?"
            params_real.append(user_petugas_id)
            
        total_realisasi = cursor.execute(realisasi_query, params_real).fetchone()['total'] or 0
        
        percentage = round((total_realisasi / total_target * 100), 1) if total_target > 0 else 0
        
        return jsonify({
            "total_target": total_target,
            "total_realisasi": total_realisasi,
            "percentage": percentage
        })
    finally:
        conn.close()

# =========================================================================
# 3. ENDPOINT DAFTAR TARGET
# =========================================================================

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 
    petugas_filter = request.args.get('petugas')
    
    raw_period = request.args.get('periode') or datetime.now().strftime('%m-%Y')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.nomet, p.nominal, 
                   p.nominal as volume, p.rayon,
                   COALESCE(r.petugas, 'Belum Terplot') as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.status_lunas = 0
            AND p.nomen NOT IN (SELECT DISTINCT nomen FROM ardebt WHERE periode = ?)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = p.nomen AND mb.periode = p.periode)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.nomen = p.nomen AND ch.periode = p.periode)
        """
        params = [raw_period, raw_period]
        
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
            # Auto-Hide data yang sudah dikunjungi hari ini
            query += " AND NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = p.nomen AND k.periode = p.periode AND DATE(k.created_at) = DATE('now'))"
        
        query += " ORDER BY p.nominal DESC LIMIT 100"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# =========================================================================
# 4. ENDPOINT LAPOR (SNAPSHOT OPERASIONAL)
# =========================================================================

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    nomen = request.form.get('idpel')
    nomet = request.form.get('nomet') or "-" # Ambil data nomet dari form
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
        # FIX: Tambahkan kolom nomet agar tidak error "no column named nomet"
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
        return APIResponse.success(message="Laporan kunjungan tersimpan.")
    except Exception as e:
        return APIResponse.error(f"Gagal simpan snapshot: {str(e)}")
    finally:
        conn.close()

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL AND petugas != '' ORDER BY petugas ASC")
        result = [row['petugas'] for row in cursor.fetchall()]
        return jsonify(result)
    finally:
        conn.close()
