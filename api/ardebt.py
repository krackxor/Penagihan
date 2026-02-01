"""
Ardebt (Tagihan Berekor) API - V7.4 (Gallery Sync & Stability Update)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ GALLERY SYNC: Sinkronisasi data ke master_pelanggan agar foto muncul di galeri.
2. ✅ FEATURE SYNC: Watermark foto khusus kategori Ardebt (Warna Orange-Red).
3. ✅ FIX: Penanganan input 'nomet' & 'no_hp' untuk integrasi Database V12.95.
4. ✅ STABILITY: Penambahan return 'wa_data' untuk mendukung fitur Share WA Otomatis.
"""

import os
from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

ardebt_bp = Blueprint('ardebt', __name__)

# =========================================================================
# 1. LOGIKA WATERMARK (DIFERENSIASI VISUAL ARDEBT)
# =========================================================================
def add_watermark(image_path, info):
    """Menanamkan informasi penagihan berekor ke foto bukti lapangan."""
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        font_size = int(width * 0.035)
        font = None
        # Path font disesuaikan untuk Linux (server) dan Windows (local)
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:\\Windows\\Fonts\\arialbd.ttf", "arial.ttf"]
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()

        # Metadata Transmisi
        text = (
            f"PETUGAS (AR) : {info['petugas']}\n"
            f"IDPEL/NM     : {info['nomen']} ({info['nama'][:12]}...)\n"
            f"STATUS       : {info['keterangan']}\n"
            f"TAGIHAN AR   : Rp {info['nominal']}\n"
            f"WAKTU        : {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )

        margin = int(width * 0.04)
        line_height = font_size + 10
        y_pos = height - (line_height * 6) - margin

        # Layer Shadow (Hitam)
        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        # Layer Utama (Orange Red - Identitas Ardebt)
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
        
        # 1. Total Target Ardebt bulan berjalan
        target_query = """
            SELECT COUNT(a.nomen) as total 
            FROM ardebt a 
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen 
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez 
            WHERE p.periode = ? AND p.status_lunas = 0
        """
        params = [active_period]
        if user_petugas_id and user_petugas_id != 'ALL':
            target_query += " AND r.petugas = ?"
            params.append(user_petugas_id)
            
        total_target = cursor.execute(target_query, params).fetchone()['total'] or 0
        
        # 2. Realisasi Kunjungan Hari Ini (Kategori Ardebt)
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
# 3. ENDPOINT DAFTAR KERJA
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
        """
        params = [active_period, active_period]

        # Filter Pencarian
        if search_query:
            query += " AND (p.nama LIKE ? OR p.nomen LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%'])
        else:
            # Sembunyikan yang sudah dikunjungi hari ini (kecuali sedang dicari)
            query += """ AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = p.nomen AND DATE(k.created_at) = DATE('now')
            )"""

        # Filter Hak Akses
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
# 4. ENDPOINT LAPOR (SNAPSHOT & TRANSMISI)
# =========================================================================
@ardebt_bp.route('/lapor', methods=['POST'])
def lapor_ardebt():
    """Validasi dan penyimpanan snapshot laporan Ardebt."""
    # Ekstraksi data dengan proteksi .get() untuk menghindari Error 400
    nomen = request.form.get('idpel')
    nomet = request.form.get('nomet', '-')
    petugas_name = request.form.get('petugas_name', 'System')
    hasil = request.form.get('hasil')
    latitude = request.form.get('latitude', '0.0')
    longitude = request.form.get('longitude', '0.0')
    no_hp = request.form.get('no_hp', '-')
    catatan = request.form.get('catatan', '')
    nominal_disp = request.form.get('nominal_display', '0')
    nama_cust = request.form.get('nama_pelanggan', 'Pelanggan')
    
    if not nomen or not hasil:
        return jsonify({"status": "error", "message": "Atribut pelaporan tidak lengkap"}), 400
    
    foto = request.files.get('foto')
    filename = "-"
    
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        filename = f"AR_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        
        # Inject Watermark
        add_watermark(foto_path, {
            'petugas': petugas_name, 
            'nomen': nomen,
            'nama': nama_cust,
            'keterangan': hasil,
            'nominal': nominal_disp
        })

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        current_period = datetime.now().strftime('%m-%Y')

        # 1. Simpan ke Kunjungan Petugas (Tabel Histori)
        cursor.execute("""
            INSERT INTO kunjungan_petugas (
                nomen, nomet, petugas_name, keterangan, no_hp, catatan, 
                foto_path, latitude, longitude, periode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (nomen, nomet, petugas_name, hasil, no_hp, catatan, filename, 
              latitude, longitude, current_period))
        
        # 2. ✅ FIX: SYNC KE MASTER PELANGGAN (Kunci agar muncul di Galeri Web)
        # Tanpa ini, foto ada di folder server tapi tidak muncul di menu Galeri
        cursor.execute("""
            UPDATE master_pelanggan 
            SET nomet = ?, no_hp = ?, tgl_lunas = ?
            WHERE nomen = ? AND status_lunas = 0
        """, (nomet, no_hp, datetime.now().strftime('%Y-%m-%d'), nomen))
        
        conn.commit()
        
        # Return data untuk pemicu otomatis Share WA di Frontend
        return jsonify({
            "status": "success",
            "message": "Snapshot Ardebt berhasil dikunci & masuk galeri",
            "wa_data": {
                "petugas": petugas_name,
                "nama": nama_cust,
                "nomen": nomen,
                "nomet": nomet,
                "status": hasil,
                "catatan": catatan,
                "total": nominal_disp,
                "foto_path": filename
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": f"Database Failure: {str(e)}"}), 500
    finally:
        conn.close()

# =========================================================================
# 5. FUNGSI PENDUKUNG (HELPERS)
# =========================================================================
def get_active_target_period(cursor):
    """Mendeteksi periode target aktif di database."""
    res = cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    return res['periode'] if res else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/petugas', methods=['GET'])
def get_list_petugas_ardebt():
    """Mengambil daftar petugas unik dari rute."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC")
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    finally:
        conn.close()

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_history(nomen):
    """Audit rekam jejak piutang per pelanggan (Intelligence Mode)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Mengambil histori 6 bulan terakhir
        history = cursor.execute("""
            SELECT periode, kubik as pemakaian_air, nominal as rupiah, tarif, status_lunas 
            FROM master_pelanggan 
            WHERE nomen = ? 
            ORDER BY id DESC LIMIT 6
        """, (nomen,)).fetchall()
        
        if not history:
            return jsonify({"status": "empty"})
            
        nunggak_count = sum(1 for h in history if h['status_lunas'] == 0)
        level = "danger" if nunggak_count >= 2 else "warning"
        saran = "Segera lakukan tindakan penutupan" if nunggak_count >= 3 else "Berikan edukasi pelunasan"
        
        return jsonify({
            "status": "available",
            "history": [dict(h) for h in history],
            "analysis": {
                "count_nunggak": nunggak_count,
                "level": level,
                "saran": saran
            }
        })
    finally:
        conn.close()
