import os
from flask import Blueprint, jsonify, request, current_app
from core.database import get_db_connection
from datetime import datetime
from werkzeug.utils import secure_filename

belum_bayar_bp = Blueprint('belum_bayar', __name__)

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    petugas = request.args.get('petugas')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = "SELECT * FROM pelanggan_tagihan WHERE status_bayar = 'BELUM BAYAR'"
    params = []
    
    if petugas and petugas != 'all':
        query += " AND petugas = %s"
        params.append(petugas)
        
    cursor.execute(query, params)
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

@belum_bayar_bp.route('/petugas-tabs', methods=['GET'])
def get_petugas_tabs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT petugas FROM pelanggan_tagihan WHERE petugas IS NOT NULL AND petugas != ''")
    petugas_list = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify(petugas_list)

@belum_bayar_bp.route('/lapor', methods=['POST'])
def lapor_kunjungan():
    idpel = request.form.get('idpel')
    hasil = request.form.get('hasil')
    keterangan = request.form.get('keterangan')
    foto = request.files.get('foto')
    
    filename = None
    if foto:
        # Buat folder jika belum ada
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = os.path.splitext(foto.filename)[1]
        filename = secure_filename(f"{idpel}_{timestamp}{ext}")
        foto.save(os.path.join(upload_folder, filename))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Masukkan ke tabel history_kunjungan
        query_history = """
            INSERT INTO history_kunjungan (idpel, tanggal, hasil, keterangan, foto)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query_history, (idpel, datetime.now(), hasil, keterangan, filename))
        
        # 2. Update status di tabel utama (opsional, jika ingin menandai sudah dikunjungi)
        query_update = "UPDATE pelanggan_tagihan SET last_kunjungan = %s WHERE idpel = %s"
        cursor.execute(query_update, (datetime.now(), idpel))
        
        conn.commit()
        conn.close()
        return jsonify({"message": "Laporan berhasil disimpan"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500
