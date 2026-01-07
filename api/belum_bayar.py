import os
import sqlite3
from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def add_watermark(image_path, info):
    """Fungsi untuk menambahkan watermark teks pada foto hasil kunjungan."""
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

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """
    Mengambil daftar pelanggan yang belum bayar (Target CURRENT).
    Logika Pintu Ganda: 
    - Sumber: MC (master_pelanggan)
    - Pengecekan: master_bayar (notagihan match)
    - Pengecekan: collection_harian (notag match)
    - Pengecekan: ardebt (nomen match)
    """
    petugas_filter = request.args.get('petugas')
    req_periode = request.args.get('periode') 
    
    today = datetime.now()
    if req_periode:
        try:
            target_dt = datetime.strptime(req_periode, '%m-%Y')
        except:
            target_dt = today
    else:
        target_dt = today

    curr_period_str = target_dt.strftime('%m-%Y')

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # QUERY DIPERBARUI: Cocokkan p.notagihan dengan c.notag (Collection)
        query = """
            SELECT p.*, r.petugas as nama_petugas 
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.tipe = 'MC' 
            AND p.periode = ?
            
            -- Filter 1: Cek di Master Bayar (MB)
            AND NOT EXISTS (
                SELECT 1 FROM master_bayar mb 
                WHERE mb.notagihan = p.notagihan
            )
            
            -- Filter 2: Cek di Collection Harian (Field notag)
            AND NOT EXISTS (
                SELECT 1 FROM collection_harian c 
                WHERE c.notag = p.notagihan
            )

            -- Filter 3: Cek di Ardebt (Berekor)
            AND NOT EXISTS (
                SELECT 1 FROM ardebt a 
                WHERE a.nomen = p.nomen
            )
            
            AND p.nominal >= 100000
        """
        
        params = [curr_period_str]
        
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY p.nominal DESC LIMIT 50"
        
        cursor.execute(query, params)
        data = [dict(row) for row in cursor.fetchall()]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL AND petugas != ''")
        petugas_list = [row[0] for row in cursor.fetchall()]
        return jsonify(petugas_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
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
        return jsonify({"error": "Nomen dan Hasil Kunjungan wajib diisi"}), 400
    
    filename = None
    if foto:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = os.path.splitext(foto.filename)[1].lower()
        
        if ext not in ['.jpg', '.jpeg', '.png']:
            return jsonify({"error": "Format foto harus JPG atau PNG"}), 400
            
        filename = secure_filename(f"LOG_{nomen}_{timestamp}{ext}")
        foto_path = os.path.join(upload_folder, filename)
        foto.save(foto_path)

        visit_period = datetime.now().strftime('%m-%Y')

        info_watermark = {
            'waktu': datetime.now().strftime('%d/%m/%Y %H:%M WIB'),
            'petugas': petugas_name or "Petugas Lapangan",
            'nomen': nomen,
            'nama': nama_pelanggan or "-",
            'nominal': nominal_display or "0"
        }
        add_watermark(foto_path, info_watermark)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query_log = """
            INSERT INTO kunjungan_petugas (
                nomen, petugas_name, keterangan, no_hp, 
                catatan, janji_bayar_dt, foto_path, latitude, longitude, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query_log, (
            nomen, petugas_name, hasil, no_hp, 
            catatan, janji_dt, filename, lat, lng, visit_period
        ))
        
        conn.commit()
        return jsonify({
            "message": "Laporan kunjungan berhasil disimpan", 
            "status": "success",
            "filename": filename
        }), 200
    except Exception as e:
        return jsonify({"error": f"Database Error: {str(e)}"}), 500
    finally:
        conn.close()

# --- ENDPOINT: TUNGGAKAN BEREKOR (ARDEBT - RAW DATA) ---
@belum_bayar_bp.route('/ardebt', methods=['GET'])
def get_tagihan_berekor():
    """
    Mengambil rincian tagihan berekor (Ardebt).
    LOGIKA: Tampil APA ADANYA (Tanpa SUM/COUNT).
    """
    petugas_filter = request.args.get('petugas')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Query RAW DATA: Menampilkan rincian per periode_bill, jumlah, dan volume
        query = """
            SELECT 
                a.id,
                a.nomen, 
                p.nama,
                p.pcez,
                a.periode_bill, 
                a.jumlah,       
                a.volume,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON (p.pcez = r.pcez)
        """
        
        params = []
        if petugas_filter and petugas_filter != 'all':
            query += " WHERE r.petugas = ?"
            params.append(petugas_filter)
            
        query += " ORDER BY a.nomen ASC, a.periode_bill DESC"

        cursor.execute(query, params)
        data = [dict(row) for row in cursor.fetchall()]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
