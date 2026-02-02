"""
Ardebt (Tagihan Berekor) API - V7.13 (Daily Quota & Smart Sort)
Update: 2026-02-02
---------------------------------------------------------------------------
Perbaikan Strategis:
1. ✅ DAILY LIMIT: Membatasi tugas hanya 20 per hari per petugas.
2. ✅ SMART SORT: Mengurutkan berdasarkan Zona (PCEZ) lalu Nominal Terbesar.
3. ✅ DYNAMIC PROGRESS: Target harian dikunci di angka 20.
4. ✅ FIX DETAIL: Endpoint detail tetap tersedia.
"""

import os
import pytz 
from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

ardebt_bp = Blueprint('ardebt', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

# =========================================================================
# 1. FUNGSI WATERMARK (TIDAK BERUBAH)
# =========================================================================
def add_watermark(image_path, info):
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        font_size = int(width * 0.035)
        font = None
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:\\Windows\\Fonts\\arialbd.ttf", "arial.ttf"]
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()
        waktu_wib = get_wib_time().strftime('%d/%m/%Y %H:%M') + " WIB"
        text = (f"PETUGAS (AR) : {info['petugas']}\nIDPEL/NM     : {info['nomen']} ({info['nama'][:12]}...)\nSTATUS       : {info['keterangan']}\nTAGIHAN AR   : Rp {info['nominal']}\nWAKTU        : {waktu_wib}")
        margin = int(width * 0.04)
        line_height = font_size + 10
        y_pos = height - (line_height * 6) - margin
        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FF4500", spacing=10)
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Ardebt Watermark Failure: {str(e)}")

# =========================================================================
# 2. PROGRES AUDIT (UPDATED: FIXED TARGET 20)
# =========================================================================
@ardebt_bp.route('/progress', methods=['GET'])
def get_ardebt_progress():
    user_petugas_id = session.get('petugas_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d')
        
        # 1. Hitung Realisasi Hari Ini
        real_query = """
            SELECT COUNT(DISTINCT k.nomen) as total 
            FROM kunjungan_petugas k 
            INNER JOIN ardebt a ON k.nomen = a.nomen 
            WHERE DATE(k.created_at) = ?
        """
        params = [tgl_skrg]
        
        if user_petugas_id and user_petugas_id != 'ALL':
            real_query += " AND k.petugas_name = ?"
            params.append(user_petugas_id)
            
        total_real = cursor.execute(real_query, params).fetchone()['total'] or 0
        
        # 2. Target Harian Fix 20 (Sesuai Permintaan)
        total_target = 20
        
        percentage = round((total_real / total_target * 100), 1)
        
        return jsonify({
            "total_target": total_target, 
            "total_realisasi": total_real, 
            "percentage": min(100, percentage) # Cap di 100% agar rapi
        })
    finally:
        conn.close()

# =========================================================================
# 3. DAFTAR KERJA (UPDATED: QUOTA 20 & SMART SORTING)
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
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d')

        # --- LOGIKA KUOTA 20 PER HARI ---
        limit_kuota = 50 # Default limit untuk admin/all
        
        target_petugas = None
        if user_role == 'petugas':
            target_petugas = user_petugas_id
        elif petugas_filter != 'all':
            target_petugas = petugas_filter
            
        if target_petugas:
            # Hitung yang sudah dikerjakan hari ini
            cursor.execute("""
                SELECT COUNT(DISTINCT k.nomen) 
                FROM kunjungan_petugas k 
                JOIN ardebt a ON k.nomen = a.nomen
                WHERE k.petugas_name = ? AND DATE(k.created_at) = ?
            """, (target_petugas, tgl_skrg))
            sudah_dikerjakan = cursor.fetchone()[0]
            
            # Hitung sisa jatah
            limit_kuota = max(0, 20 - sudah_dikerjakan)
            
        # Jika kuota habis dan tidak sedang cari, return kosong
        if limit_kuota == 0 and not search_query:
            return jsonify([])

        # --- QUERY DATA UTAMA ---
        query = """
            SELECT 
                a.nomen, 
                p.nama, 
                p.alamat, 
                COALESCE(p.nomet, '-') as no_seri_meter, 
                p.pcez, 
                COALESCE(SUM(a.jumlah), 0) as total_ardebt,        -- Total Uang
                COUNT(a.nomen) as lembar_ardebt,                   -- Jumlah Lembar
                COALESCE(SUM(a.volume), 0) as total_kubik_ardebt,  -- Total Kubik
                COALESCE(p.nominal, 0) as nominal_mc,              -- Tagihan Bulan Ini
                COALESCE(r.petugas, 'UNMAPPED') as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? AND p.status_lunas = 0
            AND p.nomen NOT IN (SELECT nomen FROM master_bayar WHERE periode = ?)
        """
        params = [active_period, active_period]

        if search_query:
            query += " AND (p.nama LIKE ? OR p.nomen LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%'])
            limit_kuota = 50 # Longgarkan limit saat searching
        else:
            # Filter: Yang sudah dikunjungi hari ini HILANG
            query += " AND NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = p.nomen AND DATE(k.created_at) = ?)"
            params.append(tgl_skrg)

        if target_petugas:
            query += " AND r.petugas = ?"
            params.append(target_petugas)

        query += " GROUP BY a.nomen, p.nama, p.alamat, p.nomet, p.pcez, p.nominal, r.petugas"
        
        # --- SMART SORTING: ZONA DULU, BARU NOMINAL ---
        # 1. p.pcez ASC   : Mengelompokkan rute agar lokasi berdekatan (hemat waktu)
        # 2. total_ardebt DESC : Prioritas tagihan terbesar di rute tersebut
        query += f" ORDER BY p.pcez ASC, total_ardebt DESC LIMIT {limit_kuota}"
        
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

# =========================================================================
# 4. RINCIAN ARDEBT (TIDAK BERUBAH)
# =========================================================================
@ardebt_bp.route('/detail/<nomen>', methods=['GET'])
def get_ardebt_details(nomen):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        details = cursor.execute("""
            SELECT periode_bill, 'WATER' as tipe_bill, jumlah, volume 
            FROM ardebt 
            WHERE nomen = ? 
            ORDER BY periode_bill DESC
        """, (nomen,)).fetchall()
        return jsonify([dict(row) for row in details])
    finally:
        conn.close()

# =========================================================================
# 5. LAPOR KUNJUNGAN (TIDAK BERUBAH)
# =========================================================================
@ardebt_bp.route('/lapor', methods=['POST'])
def lapor_ardebt():
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
        return jsonify({"status": "error", "message": "Data tidak lengkap"}), 400
    
    waktu_skrg = get_wib_time()
    tgl_sql = waktu_skrg.strftime('%Y-%m-%d %H:%M:%S')
    periode_sekarang = waktu_skrg.strftime('%m-%Y')

    foto = request.files.get('foto')
    filename = "-"
    
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        filename = f"AR_{nomen}_{waktu_skrg.strftime('%Y%m%d_%H%M%S')}.jpg"
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        add_watermark(foto_path, {'petugas': petugas_name, 'nomen': nomen, 'nama': nama_cust, 'keterangan': hasil, 'nominal': nominal_disp})

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Ambil alamat real dari master
        data_pelanggan = cursor.execute("SELECT nama, alamat FROM master_pelanggan WHERE nomen = ? ORDER BY id DESC LIMIT 1", (nomen,)).fetchone()
        real_nama = data_pelanggan['nama'] if data_pelanggan else nama_cust
        real_alamat = data_pelanggan['alamat'] if data_pelanggan else "Alamat tidak tersedia"
        
        cursor.execute("""
            INSERT INTO kunjungan_petugas (nomen, nomet, petugas_name, keterangan, no_hp, catatan, foto_path, latitude, longitude, periode, nama_snapshot, alamat_snapshot, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, nomet, petugas_name, hasil, no_hp, catatan, filename, latitude, longitude, periode_sekarang, real_nama, real_alamat, tgl_sql)) 
        
        # Update Master
        cursor.execute("UPDATE master_pelanggan SET nomet = ?, no_hp = ? WHERE nomen = ? AND status_lunas = 0", (nomet, no_hp, nomen))
        conn.commit()
        
        base_url = request.host_url.rstrip('/') 
        share_link = f"{base_url}/api/history/share/view/{nomen}"

        return jsonify({
            "status": "success",
            "message": "Laporan tersimpan",
            "wa_data": {
                "petugas": petugas_name, "nama": real_nama, "nomen": nomen, "nomet": nomet,
                "alamat": real_alamat, "status": hasil, "catatan": catatan, "total": nominal_disp, "link_preview": share_link
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": f"Database Error: {str(e)}"}), 500
    finally:
        conn.close()

# --- FUNGSI PENDUKUNG ---
def get_active_target_period(cursor):
    res = cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    return res['periode'] if res else get_wib_time().strftime('%m-%Y')

@ardebt_bp.route('/petugas', methods=['GET'])
def get_list_petugas_ardebt():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC")
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    finally:
        conn.close()

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_history(nomen):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        history = cursor.execute("SELECT periode, kubik as pemakaian_air, nominal as rupiah, tarif, status_lunas FROM master_pelanggan WHERE nomen = ? ORDER BY id DESC LIMIT 6", (nomen,)).fetchall()
        if not history: return jsonify({"status": "empty"})
        nunggak_count = sum(1 for h in history if h['status_lunas'] == 0)
        return jsonify({
            "status": "available", 
            "history": [dict(h) for h in history],
            "analysis": {"count_nunggak": nunggak_count, "level": "danger" if nunggak_count >= 2 else "warning", "saran": "Tindakan penutupan" if nunggak_count >= 3 else "Berikan edukasi"}
        })
    finally:
        conn.close()
