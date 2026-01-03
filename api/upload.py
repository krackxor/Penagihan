from flask import Blueprint, request, jsonify, current_app
from processors.auto_detect import detect_file_period
from core.database import get_db_connection
import pandas as pd
import os

upload_bp = Blueprint('upload', __name__)

def save_chunk_to_db(df, file_type, bulan, tahun, db):
    """Logika penyimpanan data per chunk"""
    if file_type == 'mc':
        for _, row in df.iterrows():
            db.execute(
                "INSERT INTO master_pelanggan (nomen, nama, pcez, periode_bulan, periode_tahun) VALUES (?, ?, ?, ?, ?)",
                (row.get('NOMEN'), row.get('NAMA'), row.get('PCEZ'), bulan, tahun)
            )

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files.get('file')
    file_type = request.form.get('file_type')
    
    if not file or not file_type:
        return jsonify({"error": "File atau tipe file tidak ditemukan"}), 400

    # Path menggunakan UPLOAD_FOLDER dari config
    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
    temp_path = os.path.join(temp_dir, file.filename)
    
    # Simpan file ke disk terlebih dahulu
    file.save(temp_path)

    db = get_db_connection()
    
    try:
        # Deteksi periode menggunakan sample (5 baris pertama)
        sample = pd.read_csv(temp_path, nrows=5) if file.filename.endswith('.csv') else pd.read_excel(temp_path, nrows=5)
        bulan, tahun = detect_file_period(sample, file_type)

        if file.filename.endswith('.csv'):
            # Proses file CSV besar dengan chunksize 10.000 baris
            for chunk in pd.read_csv(temp_path, chunksize=10000):
                save_chunk_to_db(chunk, file_type, bulan, tahun, db)
        else:
            # Untuk Excel (xls/xlsx)
            df = pd.read_excel(temp_path)
            save_chunk_to_db(df, file_type, bulan, tahun, db)
        
        db.commit()
        if os.path.exists(temp_path): os.remove(temp_path)

        return jsonify({"status": "success", "message": f"Data {file_type.upper()} berhasil diolah"})
    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"error": str(e)}), 500
