import os
import sqlite3
from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def add_watermark(image_path, info):
    """Menambahkan watermark informasi penagihan pada foto bukti kunjungan."""
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        font_size = int(width * 0.04)
        
        try:
            # Path font standar Linux VPS, fallback ke default jika gagal
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()

        text = (
            f"{info['waktu']}\n"
            f"Petugas: {info['petugas']}\n"
            f"Nomen: {info['nomen']}\n"
            f"Pelanggan: {info['nama']}\n"
            f"Tagihan: Rp {info['nominal']}"
        )

        margin = int(width * 0.02)
        text_height = font_size * 6 
        x = margin
        y = height - text_height - margin

        # Efek bayangan agar teks terbaca di background terang
        shadow_offset = 2
        draw.multiline_text((x + shadow_offset, y + shadow_offset), text, font=font, fill="black", spacing=5)
        draw.multiline_text((x, y), text, font=font, fill="yellow", spacing=5)
        
        img.save(image_path)
        return True
    except Exception as e:
        print(f"❌ Gagal membuat watermark: {e}")
        return False

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """Mengambil daftar petugas unik dari tabel rute."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL AND petugas != '' ORDER BY petugas ASC")
        return jsonify([row[0] for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """
    LOGIKA SMART: Mengambil tagihan aktif >= Rp 10.000.
    Pintu Ganda: Validasi terhadap Master Bayar dan Collection Harian (notag).
    """
    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    
    # Normalisasi Periode (Frontend: 'Januari 2026' -> Backend: '01-2026')
    bulan_map = {'Januari':'01','Februari':'02','Maret':'03','April':'04','Mei':'05','Juni':'06',
                 'Juli':'07','Agustus':'08','September':'09','Oktober':'10','November':'11','Desember':'12'}
    try:
        if req_periode and ' ' in req_periode:
            part = req_periode.split(' ')
            curr_period = f"{bulan_map[part[0]]}-{part[1]}"
        else:
            curr_period = req_periode or datetime.now().strftime('%m-%Y')
    except:
        curr_period = datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # FIX: Join PCEZ langsung (p.pcez = r.pcez) karena upload sudah menstandardisasi format
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, r.petugas as nama_petugas,
            SUM(p.nominal) as total_ditagih
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE (p.periode = ? OR (p.periode < ? AND p.tipe = 'MC'))
            
            -- Filter Pintu Ganda
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = p.notagihan)
            
            -- Sembunyikan jika ada di Ardebt (diproses di menu terpisah)
            AND NOT EXISTS (SELECT 1 FROM ardebt a WHERE a.nomen = p.nomen)
        """
        params = [curr_period, curr_period]
        
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " GROUP BY p.nomen HAVING total_ditagih >= 10000 ORDER BY total_ditagih DESC LIMIT 100"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('/ardebt', methods=['GET'])
def get_tagihan_berekor():
    """
    LOGIKA ARDEBT: Mengambil rincian tunggakan lama dari tabel Ardebt.
    """
    petugas_filter = request.args.get('petugas')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT 
                a.nomen, p.nama, p.pcez, r.petugas as nama_petugas,
                a.periode_bill, a.jumlah, a.volume
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE 1=1
            -- Sembunyikan jika sudah dikunjungi hari ini
            AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = a.nomen 
                AND date(k.created_at, '+7 hours') = date('now', 'localtime')
            )
        """
        params = []
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY a.periode_bill ASC LIMIT 50"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Menyimpan laporan lapangan dengan penanganan file yang robust."""
    nomen = request.form.get('idpel')
    petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil')
    foto = request.files.get('foto')
    
    if not nomen or not hasil:
        return APIResponse.error("Data laporan tidak lengkap", code=400)
    
    filename = None
    if foto:
        # Gunakan path absolut untuk stabilitas di VPS
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = os.path.splitext(foto.filename)[1].lower()
        filename = secure_filename(f"LOG_{nomen}_{timestamp}{ext}")
        foto_path = os.path.join(upload_folder, filename)
        
        foto.save(foto_path)
        
        # Tambahkan watermark ke file fisik
        add_watermark(foto_path, {
            'waktu': datetime.now().strftime('%d/%m/%Y %H:%M WIB'),
            'petugas': petugas_name or "Petugas Lapangan", 
            'nomen': nomen,
            'nama': request.form.get('nama_pelanggan') or "-",
            'nominal': request.form.get('nominal_display') or "0"
        })

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO kunjungan_petugas (
                nomen, petugas_name, keterangan, no_hp, catatan, 
                janji_bayar_dt, foto_path, latitude, longitude, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nomen, petugas_name, hasil, request.form.get('no_hp'), 
            request.form.get('keterangan'), request.form.get('janji_bayar_dt'), 
            filename, request.form.get('latitude'), request.form.get('longitude'), 
            datetime.now().strftime('%m-%Y')
        ))
        conn.commit()
        return APIResponse.success(data={"filename": filename})
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@belum_bayar_bp.route('/history-analisis', methods=['GET'])
def get_history_analisis():
    """Analisis 3 bulan terakhir untuk Radar Macet."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # 1. Radar Macet (Pelanggan yang sering muncul di Ardebt)
        query_macet = """
            SELECT p.nomen, p.nama, p.nominal, COUNT(a.id) as record_macet
            FROM master_pelanggan p
            LEFT JOIN ardebt a ON p.nomen = a.nomen
            WHERE p.tipe = 'MC' 
            AND p.periode = (SELECT MAX(periode) FROM master_pelanggan WHERE tipe='MC')
            GROUP BY p.nomen
            ORDER BY record_macet DESC LIMIT 50
        """
        cursor.execute(query_macet)
        macet_data = [dict(row) for row in cursor.fetchall()]
        
        return APIResponse.success(data={"radar_macet": macet_data})
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()
