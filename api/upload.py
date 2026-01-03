import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from processors.auto_detect import detect_file_period
from core.database import get_db_connection

upload_bp = Blueprint('upload', __name__)

def identify_file_type(df):
    """
    Mendeteksi jenis file berdasarkan 'Fingerprint' kolom unik.
    Logika ini memastikan MB dan MC tidak tertukar meski keduanya punya ZONA_NOVAK.
    """
    cols = [c.upper() for c in df.columns]
    
    # 1. MB (Master Bayar) - Ciri khas: TGL_BAYAR & LKS_BAYAR
    if 'TGL_BAYAR' in cols and 'LKS_BAYAR' in cols:
        return 'mb'
    
    # 2. MC (Master Catat) - Ciri khas: ZONA_NOVAK & TGL_CATAT
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols:
        return 'mc'
    
    # 3. COLLECTION (Daily) - Ciri khas: PAY_DT & AMT_COLLECT
    if 'PAY_DT' in cols or 'AMT_COLLECT' in cols:
        return 'collection'
    
    # 4. ARDEBT (Tunggakan) - Ciri khas: PERIODE_BILL
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    # 5. RUTE JS (Mapping) - Ciri khas: PETUGAS & PCEZ
    if 'PETUGAS' in cols and 'PCEZ' in cols:
        return 'rute'
    
    return None

def save_chunk_to_db(df, file_type, bulan, tahun, db):
    """Logika penyimpanan data sesuai kategori file"""
    
    if file_type == 'mc':
        for _, row in df.iterrows():
            # Rumus Pecahan ZONA_NOVAK (Contoh: 350960217)
            zona = str(row.get('ZONA_NOVAK', '')).split('.')[0]
            if len(zona) >= 9:
                rayon = zona[0:2]          # '35'
                pc    = zona[3:6]          # '096'
                ez    = zona[6:8]          # '02'
                pcez  = f"{pc}/{ez}"       # '096/02'
                block = zona[7:9]          # '17'
            else:
                rayon = pc = ez = pcez = block = "Format Salah"

            db.execute("""
                INSERT INTO master_pelanggan 
                (nomen, nama, pcez, rayon, pc, ez, block, periode_bulan, periode_tahun, nominal) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(row.get('NOMEN')), row.get('NAMA_PEL'), pcez, rayon, pc, ez, block, bulan, tahun, row.get('NOMINAL')))
            
    elif file_type == 'collection':
        for _, row in df.iterrows():
            db.execute("""
                INSERT INTO collection_harian (nomen, pay_dt, nominal, periode_bulan, periode_tahun)
                VALUES (?, ?, ?, ?, ?)
            """, (str(row.get('NOMEN')), row.get('PAY_DT'), row.get('AMT_COLLECT'), bulan, tahun))

    elif file_type == 'ardebt':
        for _, row in df.iterrows():
            db.execute("""
                INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume)
                VALUES (?, ?, ?, ?)
            """, (str(row.get('NOMEN')), row.get('PERIODE_BILL'), row.get('JUMLAH'), row.get('VOLUME')))

    elif file_type == 'rute':
        for _, row in df.iterrows():
            db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)",
                       (row.get('PCEZ'), row.get('PETUGAS')))

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "File tidak ditemukan"}), 400

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, file.filename)
    file.save(temp_path)

    db = get_db_connection()
    
    try:
        # 1. Identifikasi Jenis File (Gunakan 10 baris pertama sebagai sample)
        if temp_path.endswith('.csv'):
            df_sample = pd.read_csv(temp_path, nrows=10)
        else:
            df_sample = pd.read_excel(temp_path, nrows=10)

        file_type = identify_file_type(df_sample)
        
        if not file_type:
            return jsonify({"error": "Sistem tidak mengenali header file ini. Pastikan kolom sesuai SOP."}), 400

        # 2. Deteksi Periode
        bulan, tahun = detect_file_period(df_sample, file_type)

        # 3. Proses Data secara penuh (Chunking untuk CSV)
        if temp_path.endswith('.csv'):
            for chunk in pd.read_csv(temp_path, chunksize=10000):
                save_chunk_to_db(chunk, file_type, bulan, tahun, db)
        else:
            df_full = pd.read_excel(temp_path)
            save_chunk_to_db(df_full, file_type, bulan, tahun, db)

        # 4. Catat ke History
        db.execute("""
            INSERT INTO upload_history (filename, file_type, periode, status)
            VALUES (?, ?, ?, ?)
        """, (file.filename, file_type.upper(), f"{bulan}/{tahun}" if bulan else "-", "Berhasil"))

        db.commit()
        
        if os.path.exists(temp_path):
            os.remove(temp_path)

        return jsonify({
            "status": "success", 
            "detected": file_type.upper(),
            "message": f"Data {file_type.upper()} Berhasil diproses otomatis."
        })

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": str(e)}), 500
