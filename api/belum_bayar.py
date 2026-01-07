import os
import sqlite3
from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from datetime import datetime, timedelta
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

        shadow_offset = 2
        draw.multiline_text((x + shadow_offset, y + shadow_offset), text, font=font, fill="black", spacing=5)
        draw.multiline_text((x, y), text, font=font, fill="yellow", spacing=5)
        
        img.save(image_path)
        return True
    except Exception as e:
        print(f"Gagal membuat watermark: {e}")
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

@belum_bayar_bp.route('/galeri', methods=['GET'])
def get_galeri_kunjungan():
    """Mengambil foto kunjungan menyeluruh (Current & Ardebt)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT k.foto_path, k.nomen, COALESCE(m.nama, a.nomen, 'Pelanggan Ardebt') as nama,
                   k.petugas_name, datetime(k.created_at, '+7 hours') as waktu, k.keterangan as hasil
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen
            LEFT JOIN ardebt a ON k.nomen = a.nomen
            WHERE k.foto_path IS NOT NULL AND k.foto_path NOT IN ('', 'None', 'null')
            GROUP BY k.id ORDER BY k.created_at DESC LIMIT 60
        """
        cursor.execute(query)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """LOGIKA SMART: Mengambil tagihan aktif (gabungan MC lama & baru) >= Rp 10.000."""
    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    
    # Normalisasi Periode Otomatis
    bulan_map = {'Januari':'01','Februari':'02','Maret':'03','April':'04','Mei':'05','Juni':'06',
                 'Juli':'07','Agustus':'08','September':'09','Oktober':'10','November':'11','Desember':'12'}
    try:
        part = req_periode.split(' ')
        curr_period = f"{bulan_map[part[0]]}-{part[1]}"
    except:
        curr_period = datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Menjumlahkan sisa MC bulan lalu dengan Mainbill/MC bulan ini
        query = """
            SELECT p.nomen, p.nama, p.pcez, p.notagihan, r.petugas as nama_petugas,
            SUM(p.nominal) as total_ditagih
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON REPLACE(r.pcez, '/', '') = p.pcez
            WHERE (p.periode = ? OR (p.periode < ? AND p.tipe = 'MC'))
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = p.notagihan)
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

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Menyimpan laporan hasil kunjungan lapangan dengan watermark."""
    nomen = request.form.get('idpel'); petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil'); foto = request.files.get('foto')
    
    if not nomen or not hasil:
        return jsonify({"error": "Data laporan tidak lengkap"}), 400
    
    filename = None
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        filename = secure_filename(f"LOG_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(foto.filename)[1].lower()}")
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)
        add_watermark(foto_path, {
            'waktu': datetime.now().strftime('%d/%m/%Y %H:%M WIB'),
            'petugas': petugas_name or "Petugas Lapangan", 'nomen': nomen,
            'nama': request.form.get('nama_pelanggan') or "-",
            'nominal': request.form.get('nominal_display') or "0"
        })

    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, janji_bayar_dt, foto_path, latitude, longitude, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas_name, hasil, request.form.get('no_hp'), request.form.get('keterangan'), 
              request.form.get('janji_bayar_dt'), filename, request.form.get('latitude'), request.form.get('longitude'), datetime.now().strftime('%m-%Y')))
        conn.commit()
        return jsonify({"status": "success", "filename": filename})
    finally:
        conn.close()

@belum_bayar_bp.route('/ardebt', methods=['GET'])
def get_tagihan_berekor():
    """LOGIKA ARDEBT MANDIRI: Mendeteksi sisa tagihan > 2 bulan dari database internal."""
    petugas_filter = request.args.get('petugas')
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        query = """
            SELECT p.nomen, p.nama, p.pcez, r.petugas as nama_petugas,
            COUNT(p.id) as jumlah_bulan_tunggak, SUM(p.nominal) as total_tunggakan
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON REPLACE(r.pcez, '/', '') = p.pcez
            WHERE NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM kunjungan_petugas k WHERE k.nomen = p.nomen AND date(k.created_at, '+7 hours') = date('now', 'localtime'))
        """
        params = []
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"; params.append(petugas_filter)
            
        query += " GROUP BY p.nomen HAVING jumlah_bulan_tunggak >= 2 ORDER BY total_tunggakan DESC LIMIT 15"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    finally:
        conn.close()
