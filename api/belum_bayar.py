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
            # Path font untuk sistem Linux/Ubuntu
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
    """Mengambil daftar petugas unik untuk dropdown filter."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL AND petugas != '' ORDER BY petugas ASC")
        petugas_list = [row[0] for row in cursor.fetchall()]
        return jsonify(petugas_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@belum_bayar_bp.route('/galeri', methods=['GET'])
def get_galeri_kunjungan():
    """Mengambil daftar foto kunjungan (Current & Ardebt) secara dinamis."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT 
                k.foto_path, 
                k.nomen, 
                COALESCE(m.nama, 'Pelanggan Ardebt/Luar Master') as nama,
                k.petugas_name,
                datetime(k.created_at, '+7 hours') as waktu,
                k.keterangan as hasil
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen
            WHERE k.foto_path IS NOT NULL 
            AND k.foto_path != '' 
            AND k.foto_path != 'None'
            ORDER BY k.created_at DESC
            LIMIT 60
        """
        cursor.execute(query)
        data = [dict(row) for row in cursor.fetchall()]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """Mengambil daftar pelanggan TAGIHAN CURRENT (Bulan Berjalan)."""
    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    
    today = datetime.now()
    target_dt = today
    if req_periode:
        try:
            target_dt = datetime.strptime(req_periode, '%m-%Y')
        except: pass

    curr_period_str = target_dt.strftime('%m-%Y')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT p.*, r.petugas as nama_petugas 
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON REPLACE(r.pcez, '/', '') = p.pcez
            WHERE p.tipe = 'MC' AND p.periode = ?
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian c WHERE c.notag = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM ardebt a WHERE a.nomen = p.nomen)
            AND p.nominal >= 100000
        """
        params = [curr_period_str]
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY p.nominal DESC LIMIT 50"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Menyimpan laporan hasil kunjungan petugas lapangan."""
    nomen = request.form.get('idpel')
    petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil')
    no_hp = request.form.get('no_hp')
    catatan = request.form.get('keterangan')
    nama_pelanggan = request.form.get('nama_pelanggan') 
    nominal_display = request.form.get('nominal_display') 
    janji_dt = request.form.get('janji_bayar_dt')
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    foto = request.files.get('foto')
    
    if not nomen or not hasil:
        return jsonify({"error": "Data tidak lengkap"}), 400
    
    filename = None
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = os.path.splitext(foto.filename)[1].lower()
        filename = secure_filename(f"LOG_{nomen}_{timestamp}{ext}")
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)

        info_watermark = {
            'waktu': datetime.now().strftime('%d/%m/%Y %H:%M WIB'),
            'petugas': petugas_name or "Petugas",
            'nomen': nomen,
            'nama': nama_pelanggan or "-",
            'nominal': nominal_display or "0"
        }
        add_watermark(foto_path, info_watermark)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        visit_period = datetime.now().strftime('%m-%Y')
        cursor.execute("""
            INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, no_hp, catatan, janji_bayar_dt, foto_path, latitude, longitude, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas_name, hasil, no_hp, catatan, janji_dt, filename, lat, lng, visit_period))
        conn.commit()
        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@belum_bayar_bp.route('/ardebt', methods=['GET'])
def get_tagihan_berekor():
    """Mengambil daftar TAGIHAN BEREKOR (Ardebt)."""
    petugas_filter = request.args.get('petugas')
    conn = get_db_connection()
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    try:
        query = f"""
            SELECT a.id, a.nomen, p.nama, p.pcez, a.periode_bill, a.jumlah, a.volume, r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON REPLACE(r.pcez, '/', '') = p.pcez
            WHERE NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = a.nomen AND date(k.created_at, '+7 hours') = '{today_str}'
            )
        """
        params = []
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY a.periode_bill ASC LIMIT 10"
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
