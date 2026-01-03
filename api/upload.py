from flask import Blueprint, request, jsonify
from processors.auto_detect import detect_file_period
from core.database import get_db_connection
import pandas as pd
import os

upload_bp = Blueprint('upload', __name__)

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files.get('file')
    file_type = request.form.get('file_type')
    
    if not file or not file_type:
        return jsonify({"error": "File atau tipe file tidak ditemukan"}), 400

    # Simpan file sementara untuk diproses agar tidak membebani RAM
    temp_path = os.path.join('uploads', 'temp', file.filename)
    file.save(temp_path)

    db = get_db_connection()
    
    try:
        # 1. Deteksi Periode (Hanya ambil 5 baris pertama untuk deteksi cepat)
        sample_df = pd.read_csv(temp_path, nrows=5) if file.filename.endswith('.csv') else pd.read_excel(temp_path, nrows=5)
        bulan, tahun = detect_file_period(sample_df, file_type)
        
        if not bulan:
            return jsonify({"error": "Field acuan tanggal tidak ditemukan dalam file"}), 400

        # 2. Validasi Induk (SOP: MC harus ada lebih dulu)
        if file_type != 'mc':
            induk = db.execute(
                "SELECT id FROM master_pelanggan WHERE periode_bulan = ? AND periode_tahun = ?",
                (bulan, tahun)
            ).fetchone()
            if not induk:
                return jsonify({"error": f"SOP Gagal: Data MC periode {bulan}-{tahun} belum diupload"}), 400

        # 3. Simpan ke Database dengan CHUNKING (Khusus CSV)
        if file.filename.endswith('.csv'):
            # Baca per 10.000 baris agar RAM tidak meledak
            for chunk in pd.read_csv(temp_path, chunksize=10000):
                save_chunk_to_db(chunk, file_type, bulan, tahun, db)
        else:
            # Untuk Excel (Tidak disarankan untuk 10GB, sebaiknya convert ke CSV)
            df = pd.read_excel(temp_path)
            save_chunk_to_db(df, file_type, bulan, tahun, db)
        
        db.commit()
        # Hapus file temp setelah selesai
        os.remove(temp_path)

        return jsonify({
            "status": "success",
            "message": f"Data {file_type.upper()} periode {bulan}/{tahun} berhasil diolah"
        })

    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"error": str(e)}), 500

def save_chunk_to_db(df, file_type, bulan, tahun, db):
    """Fungsi pembantu untuk memasukkan data chunk ke database"""
    # Logika insert data ke tabel sesuai file_type
    # Contoh untuk master_pelanggan:
    if file_type == 'mc':
        for _, row in df.iterrows():
            db.execute(
                "INSERT INTO master_pelanggan (nomen, nama, pcez, periode_bulan, periode_tahun) VALUES (?, ?, ?, ?, ?)",
                (row.get('NOMEN'), row.get('NAMA'), row.get('PCEZ'), bulan, tahun)
            )
