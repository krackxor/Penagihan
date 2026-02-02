"""
Belum Bayar API - Sunter Dashboard Pro (V9.6 Daily Quota & Smart Sort)
Update: 2026-02-02
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ DAILY LIMIT: Membatasi tugas hanya 20 per hari per petugas (Sinkron Ardebt).
2. ✅ SMART SORT: Mengurutkan berdasarkan Zona (PCEZ) lalu Nominal Terbesar.
3. ✅ DYNAMIC FETCH: Data yang sudah dikerjakan hari ini otomatis hilang.
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
# 1. LOGIKA WATERMARK CERDAS (TIDAK BERUBAH)
# =========================================================================
def add_watermark(image_path, info):
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
# 2. ENDPOINT PROGRES AUDIT (FIXED TARGET 20)
# =========================================================================
@belum_bayar_bp.route('/progress', methods=['GET'])
def get_audit_progress():
    user_petugas_id = session.get('petugas_id')
    raw_period = get_wib_time().strftime('%m-%Y')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d')

        # 1. Hitung Realisasi Hari Ini (Khusus Belum Bayar/Reguler)
        realisasi_query = """
            SELECT COUNT(DISTINCT k.nomen) as total
            FROM kunjungan_petugas k
            WHERE DATE(k.created_at) = ?
            AND k.nomen NOT IN (SELECT nomen FROM ardebt)
        """
        params_real = [tgl_skrg]
        
        if user_petugas_id and user_petugas_id != 'ALL':
            realisasi_query += " AND k.petugas_name = ?"
            params_real.append(user_petugas_id)
            
        total_realisasi = cursor.execute(realisasi_query, params_real).fetchone()['total'] or 0
        
        # 2. Target Harian Fix 20 (Sesuai Permintaan)
        total_target = 20
        
        percentage = round((total_realisasi / total_target * 100), 1)
        
        return jsonify({
            "total_target": total_target,
            "total_realisasi": total_realisasi,
            "percentage": min(100, percentage) # Cap di 100%
        })
    finally:
        conn.close()

# =========================================================================
# 3. ENDPOINT DAFTAR TARGET (UPDATED: QUOTA 20 & SMART SORT)
# =========================================================================
@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 
    petugas_filter = request.args.get('petugas')
    raw_period = request.args.get('periode') or get_wib_time().strftime('%m-%Y')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d')
        
        # --- LOGIKA KUOTA 20 PER HARI ---
        limit_kuota = 50 # Default limit
        target_petugas = None

        if user_role == 'petugas':
            target_petugas = user_petugas_id
        elif petugas_filter and petugas_filter != 'all':
            target_petugas = petugas_filter
            
        if target_petugas:
            # Hitung yang sudah dikerjakan hari ini (Non-Ardebt)
            cursor.execute("""
                SELECT COUNT(DISTINCT k.nomen) 
                FROM kunjungan_petugas k 
                WHERE k.petugas_name = ? AND DATE(k.created_at) = ?
                AND k.nomen NOT IN (SELECT nomen FROM ardebt)
            """, (target_petugas, tgl_skrg))
            sudah_dikerjakan = cursor.fetchone()[0]
            
            # Hitung sisa jatah
            limit_kuota = max(0, 20 - sudah_dikerjakan)
        
        # Jika kuota habis dan tidak sedang cari, return kosong
        if limit_kuota == 0 and not search_query:
            return jsonify([])

        # --- QUERY DATA UTAMA ---
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
        
        if target_petugas:
            query += " AND r.petugas = ?"
            params.append(target_petugas)

        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
            limit_kuota = 50 # Longgarkan saat searching
        else:
            # Filter: Yang sudah dikunjungi hari ini HILANG
            query += " AND NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = p.nomen AND DATE(k.created_at) = ?)"
            params.append(tgl_skrg)
        
        # --- SMART SORTING: ZONA DULU, BARU NOMINAL ---
        # 1. p.pcez ASC   : Mengelompokkan rute agar lokasi berdekatan (hemat waktu)
        # 2. p.nominal DESC : Prioritas tagihan terbesar di rute tersebut
        query += f" ORDER BY p.pcez ASC, p.nominal DESC LIMIT {limit_kuota}"
        
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# =========================================================================
# 4. ENDPOINT LAPOR (TIDAK BERUBAH)
# =========================================================================
@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
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
    vol_air = request.form.get('pemakaian_air', '0')
    
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
        
        data_pelanggan = cursor.execute("""
            SELECT nama, alamat, kubik FROM master_pelanggan 
            WHERE nomen = ? AND status_lunas = 0 
            ORDER BY id DESC LIMIT 1
        """, (nomen,)).fetchone()
        
        real_nama = data_pelanggan['nama'] if data_pelanggan else nama_cust
        real_alamat = data_pelanggan['alamat'] if data_pelanggan else "Alamat tidak tersedia"
        final_vol = vol_air if vol_air != '0' else str(data_pelanggan['kubik'] if data_pelanggan else '0')

        cursor.execute("""
            INSERT INTO kunjungan_petugas (
                nomen, nomet, petugas_name, keterangan, no_hp, catatan, 
                foto_path, latitude, longitude, periode, 
                nama_snapshot, alamat_snapshot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, nomet, petugas_name, hasil, no_hp, catatan, filename, 
              latitude, longitude, periode_sekarang, 
              real_nama, real_alamat, tgl_sql))
        
        cursor.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (no_hp, nomen))
        conn.commit()
        
        base_url = request.host_url.rstrip('/') 
        share_link = f"{base_url}/api/history/share/view/{nomen}"

        return jsonify({
            "status": "success",
            "message": "Snapshot penagihan terkunci",
            "wa_data": {
                "petugas": petugas_name,
                "nama": real_nama,
                "nomen": nomen,
                "nomet": nomet,
                "alamat": real_alamat,
                "status": hasil,
                "catatan": catatan,
                "total": nominal_disp,
                "pemakaian_air": final_vol,
                "foto_path": filename,
                "link_preview": share_link 
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
