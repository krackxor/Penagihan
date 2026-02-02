"""
Belum Bayar API - Sunter Dashboard Pro (V9.4 Intelligence Sync)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX MAPPING: Sinkronisasi kolom p.alamat, p.nomet (no_seri_meter), dan p.kubik (pemakaian_air).
2. ✅ FEATURE SYNC: Penambahan objek 'wa_data' pada respons lapor untuk auto-share WhatsApp.
3. ✅ FIX SCHEMA: Penanganan transmisi kolom 'nomet' pada tabel kunjungan_petugas.
4. Smart Watermarking: Metadata visual dengan identitas Belum Bayar (Warna Kuning).
5. ✅ WA SHARE LINK: Menyertakan link 'share_link' untuk thumbnail WA.
6. ✅ FULL SNAPSHOT: Menyimpan Nama & Alamat saat lapor (Data Integrity).
"""

import os, sqlite3, pytz
from flask import Blueprint, jsonify, request, current_app, session, url_for
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

# =========================================================================
# 1. LOGIKA WATERMARK CERDAS (VISUAL AUDIT)
# =========================================================================

def add_watermark(image_path, info):
    """Menanamkan informasi penagihan ke foto bukti lapangan."""
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

        # Metadata Label: BELUM BAYAR (Identitas Kuning)
        waktu_wib = get_wib_time().strftime('%d/%m/%Y %H:%M') + " WIB"
        text = (
            f"PETUGAS    : {info['petugas']}\n"
            f"IDPEL/NM   : {info['nomen']} ({info['nama'][:12]}...)\n"
            f"STATUS     : {info['keterangan']}\n"
            f"TAGIHAN    : Rp {info['nominal']}\n"
            f"WAKTU      : {waktu_wib}"
        )

        margin = int(width * 0.04)
        line_height = font_size + 10
        y_pos = height - (line_height * 6) - margin

        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FFFF00", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Smart Watermark Failure: {str(e)}")

# =========================================================================
# 2. ENDPOINT PROGRES AUDIT
# =========================================================================

@belum_bayar_bp.route('/progress', methods=['GET'])
def get_audit_progress():
    """Menghitung progres kunjungan harian kategori Belum Bayar."""
    user_petugas_id = session.get('petugas_id')
    raw_period = get_wib_time().strftime('%m-%Y')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Total Target (Khusus kategori non-ardebt)
        target_query = """
            SELECT COUNT(p.nomen) as total 
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? AND p.status_lunas = 0 AND p.tipe = 'MC'
            AND p.nomen NOT IN (SELECT nomen FROM ardebt)
        """
        params = [raw_period]
        if user_petugas_id and user_petugas_id != 'ALL':
            target_query += " AND r.petugas = ?"
            params.append(user_petugas_id)
            
        total_target = cursor.execute(target_query, params).fetchone()['total'] or 0
        
        # Realisasi hari ini (WIB)
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d')
        realisasi_query = """
            SELECT COUNT(DISTINCT k.nomen) as total
            FROM kunjungan_petugas k
            LEFT JOIN rute_petugas r ON (SELECT pcez FROM master_pelanggan WHERE nomen = k.nomen LIMIT 1) = r.pcez
            WHERE k.periode = ? AND DATE(k.created_at) = ?
            AND k.nomen NOT IN (SELECT nomen FROM ardebt)
        """
        params_real = [raw_period, tgl_skrg]
        if user_petugas_id and user_petugas_id != 'ALL':
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
# 3. ENDPOINT DAFTAR TARGET (FIXED MAPPING)
# =========================================================================

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """Daftar kerja dengan sinkronisasi variabel Alamat, Meter, dan Kubikasi."""
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 
    petugas_filter = request.args.get('petugas')
    # Default periode ambil dari WIB
    raw_period = request.args.get('periode') or get_wib_time().strftime('%m-%Y')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d')
        
        # FIXED QUERY: Menyediakan alias yang sama dengan Ardebt (no_seri_meter, pemakaian_air)
        query = """
            SELECT p.nomen, p.nama, p.alamat, 
                   COALESCE(p.nomet, '-') as no_seri_meter, 
                   p.nominal, 
                   p.kubik as pemakaian_air, 
                   p.pcez, p.rayon,
                   COALESCE(r.petugas, 'Belum Terplot') as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.status_lunas = 0
            AND p.nomen NOT IN (SELECT nomen FROM ardebt)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.nomen = p.nomen AND mb.periode = p.periode)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.nomen = p.nomen AND ch.periode = p.periode)
        """
        params = [raw_period]
        
        if user_role == 'petugas' and user_petugas_id:
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            # Filter sudah dikunjungi hari ini (WIB)
            query += " AND NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = p.nomen AND DATE(k.created_at) = ?)"
            params.append(tgl_skrg)
        
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
    """Validasi dan transmisi snapshot dengan data respons Share WA."""
    nomen = request.form.get('idpel')
    nomet = request.form.get('nomet') or "-" 
    petugas_name = request.form.get('petugas_name', 'System')
    hasil = request.form.get('hasil')
    latitude = request.form.get('latitude', '0.0')
    longitude = request.form.get('longitude', '0.0')
    no_hp = request.form.get('no_hp', '-')
    catatan = request.form.get('catatan', '')
    nominal_disp = request.form.get('nominal_display', '0')
    nama_cust = request.form.get('nama_pelanggan', 'Konsumen')
    
    if not nomen or not hasil:
        return APIResponse.error("Atribut laporan tidak lengkap", code=400)
    
    waktu_skrg = get_wib_time()
    tgl_sql = waktu_skrg.strftime('%Y-%m-%d %H:%M:%S')
    periode_sekarang = waktu_skrg.strftime('%m-%Y')

    foto = request.files.get('foto')
    filename = "-"
    
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        filename = f"LOG_{nomen}_{waktu_skrg.strftime('%Y%m%d_%H%M%S')}.jpg"
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        
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
        
        # 1. AMBIL SNAPSHOT DATA ASLI (Agar History tidak berubah jika master berubah)
        data_pelanggan = cursor.execute("""
            SELECT nama, alamat FROM master_pelanggan 
            WHERE nomen = ? AND status_lunas = 0 
            ORDER BY id DESC LIMIT 1
        """, (nomen,)).fetchone()
        
        real_nama = data_pelanggan['nama'] if data_pelanggan else nama_cust
        real_alamat = data_pelanggan['alamat'] if data_pelanggan else "Alamat tidak tersedia"

        # 2. SIMPAN KUNJUNGAN
        cursor.execute("""
            INSERT INTO kunjungan_petugas (
                nomen, nomet, petugas_name, keterangan, no_hp, catatan, 
                foto_path, latitude, longitude, periode, 
                nama_snapshot, alamat_snapshot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, nomet, petugas_name, hasil, no_hp, catatan, filename, 
              latitude, longitude, periode_sekarang, 
              real_nama, real_alamat, tgl_sql))
        
        # 3. UPDATE MASTER (Opsional, simpan no HP baru)
        cursor.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (no_hp, nomen))
        conn.commit()
        
        # 4. GENERATE LINK PREVIEW UNTUK WHATSAPP
        base_url = request.host_url.rstrip('/') 
        share_link = f"{base_url}/api/history/share/view/{nomen}"

        # Integrasi Data Respons WA Blast Dinamis
        return jsonify({
            "status": "success",
            "message": "Snapshot penagihan terkunci",
            "wa_data": {
                "petugas": petugas_name,
                "nama": real_nama,
                "nomen": nomen,
                "nomet": nomet,
                "alamat": real_alamat, # <--- Data Alamat disertakan
                "status": hasil,
                "catatan": catatan,
                "total": nominal_disp,
                "foto_path": filename,
                "link_preview": share_link # <--- Link Preview disertakan
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        return APIResponse.error(f"Gagal simpan snapshot: {str(e)}")
    finally:
        conn.close()

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL AND petugas != '' ORDER BY petugas ASC")
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    finally:
        conn.close()
