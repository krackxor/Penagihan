import os
import sqlite3
from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from datetime import datetime
from werkzeug.utils import secure_filename

belum_bayar_bp = Blueprint('belum_bayar', __name__)

def dict_factory(cursor, row):
    """Konverter hasil query SQLite ke dictionary."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """Mengambil daftar pelanggan belum bayar dengan filter petugas."""
    petugas = request.args.get('petugas')
    conn = get_db_connection()
    conn.row_factory = dict_factory # Solusi untuk TypeError dictionary=True
    cursor = conn.cursor()
    
    # Query menggunakan placeholder '?' untuk SQLite
    query = "SELECT * FROM pelanggan_tagihan WHERE status_bayar = 'BELUM BAYAR'"
    params = []
    
    if petugas and petugas != 'all':
        query += " AND petugas = ?"
        params.append(petugas)
        
    cursor.execute(query, params)
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    """Mengambil daftar unik petugas untuk filter di UI."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Mengambil petugas yang aktif saja dari tabel tagihan
    cursor.execute("SELECT DISTINCT petugas FROM pelanggan_tagihan WHERE petugas IS NOT NULL AND petugas != ''")
    petugas_list = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify(petugas_list)

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    """Mencatat laporan kunjungan lapangan beserta foto dan koordinat."""
    idpel = request.form.get('idpel')
    hasil = request.form.get('hasil')
    keterangan = request.form.get('keterangan')
    lat = request.form.get('latitude') # Fitur Canggih: Koordinat GPS
    lng = request.form.get('longitude')
    foto = request.files.get('foto')
    
    # Validasi input minimal
    if not idpel or not hasil:
        return jsonify({"error": "ID Pelanggan dan Hasil wajib diisi"}), 400
    
    filename = None
    if foto:
        # Konfigurasi folder upload yang aman
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        os.makedirs(upload_folder, exist_ok=True)
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = os.path.splitext(foto.filename)[1].lower()
        
        # Validasi ekstensi file untuk keamanan
        if ext not in ['.jpg', '.jpeg', '.png']:
            return jsonify({"error": "Format foto harus JPG atau PNG"}), 400
            
        filename = secure_filename(f"{idpel}_{timestamp}{ext}")
        foto.save(os.path.join(upload_folder, filename))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 1. Masukkan ke tabel history_kunjungan
        # Menggunakan placeholder '?' untuk SQLite
        query_history = """
            INSERT INTO history_kunjungan (nomen, created_at, keterangan, foto_path, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query_history, (idpel, now, hasil + ": " + keterangan, filename, lat, lng))
        
        # 2. Update status di tabel utama pelanggan_tagihan
        query_update = "UPDATE pelanggan_tagihan SET last_kunjungan = ? WHERE nomen = ?"
        cursor.execute(query_update, (now, idpel))
        
        conn.commit()
        conn.close()
        return jsonify({"message": "Laporan berhasil disimpan", "status": "success"}), 200
    except Exception as e:
        print(f"Database Error: {e}")
        return jsonify({"error": "Terjadi kesalahan saat menyimpan ke database"}), 500
