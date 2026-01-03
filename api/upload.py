from flask import Blueprint, request, jsonify
from processors.auto_detect import detect_file_period
from core.database import get_db_connection
import pandas as pd

upload_bp = Blueprint('upload', __name__)

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files.get('file')
    file_type = request.form.get('file_type') # 'mc', 'collection', dll
    
    if not file or not file_type:
        return jsonify({"error": "File atau tipe file tidak ditemukan"}), 400

    # Baca file (dukungan CSV dan Excel)
    df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
    
    # 1. Deteksi Periode (SOP Poin 2 & 4)
    bulan, tahun = detect_file_period(df, file_type)
    if not bulan:
        return jsonify({"error": "Field acuan tanggal tidak ditemukan dalam file"}), 400

    db = get_db_connection()
    
    # 2. Validasi Induk (SOP Poin 3)
    if file_type != 'mc':
        induk = db.execute(
            "SELECT id FROM master_pelanggan WHERE periode_bulan = ? AND periode_tahun = ?",
            (bulan, tahun)
        ).fetchone()
        if not induk:
            return jsonify({"error": f"SOP Gagal: Data MC periode {bulan}-{tahun} belum diupload"}), 400

    # 3. Simpan ke Database (Logika per tipe file)
    # Data disimpan dengan periode asli hasil deteksi (SOP Poin 4)
    save_to_database(df, file_type, bulan, tahun, db)
    
    return jsonify({
        "status": "success",
        "message": f"Data {file_type.upper()} periode {bulan}/{tahun} berhasil diolah"
    })
