import os
import sqlite3
from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from datetime import datetime
from werkzeug.utils import secure_filename

belum_bayar_bp = Blueprint('belum_bayar', __name__)

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """
    Mengambil daftar pelanggan yang belum bayar.
    Data digabungkan (JOIN) antara master_pelanggan dan rute_petugas.
    Update: Hanya menampilkan nominal >= 100.000, limit 10, urutan nominal terbesar.
    """
    petugas_filter = request.args.get('petugas')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # QUERY DIOPTIMASI:
        # 1. Nominal >= 100.000 (SOP Efisiensi)
        # 2. Urutan Nominal Terbesar (Prioritas)
        # 3. Limit 10 (Fokus Petugas)
        query = """
            SELECT p.*, r.petugas as nama_petugas 
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.nomen NOT IN (SELECT nomen FROM master_bayar)
            AND p.nominal >= 100000
        """
        params = []
        
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        # Urutan: Nominal terbesar, lalu kelompokkan per rute (pcez)
        query += " ORDER BY p.nominal DESC, p.pcez ASC LIMIT 10"
        
        cursor.execute(query, params)
        data = [dict(row) for row in cursor.fetchall()]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """Mengambil daftar unik petugas dari tabel mapping rute petugas."""
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
    """Mencatat laporan kunjungan lapangan ke tabel kunjungan_petugas."""
    # Menangkap data dari form sesuai skema kunjungan_petugas
    nomen = request.form.get('idpel')
    petugas_name = request.form.get('petugas_name')
    hasil = request.form.get('hasil')          # Status: Janji Bayar, Sudah Bayar, dll
    no_hp = request.form.get('no_hp')          # Tangkap No HP (Input Terpisah)
    catatan = request.form.get('keterangan')   # Catatan tambahan lapangan
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
        foto.save(os.path.join(upload_folder, filename))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert ke tabel kunjungan_petugas (Field no_hp sekarang terpisah)
        query_log = """
            INSERT INTO kunjungan_petugas (
                nomen, petugas_name, keterangan, no_hp, 
                catatan, janji_bayar_dt, foto_path, latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query_log, (
            nomen, petugas_name, hasil, no_hp, 
            catatan, janji_dt, filename, lat, lng
        ))
        
        conn.commit()
        return jsonify({"message": "Laporan kunjungan berhasil disimpan", "status": "success"}), 200
    except Exception as e:
        return jsonify({"error": f"Database Error: {str(e)}"}), 500
    finally:
        conn.close()
