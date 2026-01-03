import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from processors.auto_detect import detect_file_period
from core.database import get_db_connection

# Inisialisasi Blueprint untuk API Upload
upload_bp = Blueprint('upload', __name__)

def save_chunk_to_db(df, file_type, bulan, tahun, db):
    """
    Fungsi pembantu untuk memproses data per chunk dan menyimpannya ke database.
    Mengintegrasikan rumus pemecahan ZONA_NOVAK untuk tipe data MC.
    """
    if file_type == 'mc':
        for _, row in df.iterrows():
            # Mengambil ZONA_NOVAK dari baris data (Contoh: 350960217)
            # Menghapus desimal .0 jika terbaca sebagai float oleh pandas
            zona = str(row.get('ZONA_NOVAK', '')).split('.')[0]
            
            # Rumus Pemecahan String sesuai spesifikasi user:
            # Contoh: 350960217
            rayon = zona[0:2]          # Karakter 1-2: '35'
            pc    = zona[3:6]          # Karakter 4-6: '096'
            ez    = zona[6:8]          # Karakter 7-8: '02'
            pcez  = f"{pc}/{ez}"       # Gabungan PC/EZ: '096/02'
            block = zona[7:9]          # Karakter 8-9: '17'

            # Simpan data ke tabel master_pelanggan
            db.execute("""
                INSERT INTO master_pelanggan 
                (nomen, nama, pcez, rayon, pc, ez, block, periode_bulan, periode_tahun, nominal) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row.get('NOMEN')), 
                row.get('NAMA_PEL'), 
                pcez, 
                rayon, 
                pc, 
                ez, 
                block, 
                bulan, 
                tahun, 
                row.get('NOMINAL')
            ))
            
    elif file_type == 'collection':
        for _, row in df.iterrows():
            db.execute("""
                INSERT INTO collection_harian (nomen, periode_bulan, periode_tahun, pay_dt)
                VALUES (?, ?, ?, ?)
            """, (str(row.get('NOMEN')), bulan, tahun, row.get('PAY_DT')))

    elif file_type == 'rute':
        # Logika khusus untuk mengunggah file pemetaan petugas (Rute RL JS.xlsx)
        for _, row in df.iterrows():
            db.execute("""
                INSERT OR REPLACE INTO rute_petugas (pcez, petugas) 
                VALUES (?, ?)
            """, (row.get('PCEZ'), row.get('PETUGAS')))

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """Endpoint utama untuk menangani unggahan file besar (hingga 10GB)"""
    file = request.files.get('file')
    file_type = request.form.get('file_type') # 'mc', 'collection', 'rute', dll
    
    if not file or not file_type:
        return jsonify({"error": "File atau tipe file tidak ditemukan"}), 400

    # Menggunakan path absolut untuk folder sementara
    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir, exist_ok=True)
        
    temp_path = os.path.join(temp_dir, file.filename)
    file.save(temp_path)

    db = get_db_connection()
    
    try:
        # 1. Penanganan khusus untuk file Rute (Mapping Petugas)
        if file_type == 'rute':
            df = pd.read_excel(temp_path) if not temp_path.endswith('.csv') else pd.read_csv(temp_path)
            save_chunk_to_db(df, 'rute', None, None, db)
        else:
            # 2. Deteksi Periode otomatis berdasarkan field acuan (SOP)
            # Membaca contoh baris pertama untuk deteksi cepat
            sample = pd.read_excel(temp_path, nrows=5) if not temp_path.endswith('.csv') else pd.read_csv(temp_path, nrows=5)
            bulan, tahun = detect_file_period(sample, file_type)
            
            if not bulan:
                return jsonify({"error": "Field acuan tanggal tidak ditemukan dalam file"}), 400

            # 3. Proses File dengan metode Chunking untuk efisiensi RAM
            if temp_path.endswith('.csv'):
                for chunk in pd.read_csv(temp_path, chunksize=10000):
                    save_chunk_to_db(chunk, file_type, bulan, tahun, db)
            else:
                df = pd.read_excel(temp_path)
                save_chunk_to_db(df, file_type, bulan, tahun, db)
        
        # Simpan perubahan dan catat ke riwayat (history)
        db.execute("""
            INSERT INTO upload_history (filename, file_type, periode, status)
            VALUES (?, ?, ?, ?)
        """, (file.filename, file_type, f"{bulan}/{tahun}" if bulan else "-", "Berhasil"))
        
        db.commit()
        
        # Bersihkan file sementara
        if os.path.exists(temp_path):
            os.remove(temp_path)

        return jsonify({
            "status": "success",
            "message": f"Data {file_type.upper()} berhasil diintegrasikan ke sistem"
        })

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": str(e)}), 500
