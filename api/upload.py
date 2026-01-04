import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from processors.auto_detect import detect_file_period
from core.database import get_db_connection

upload_bp = Blueprint('upload', __name__)

def identify_file_type(df):
    """
    Mendeteksi jenis file berdasarkan kolom unik (Fingerprint).
    """
    cols = [c.upper() for c in df.columns]
    
    # 1. MB (Master Bayar) - Ciri: TGL_BAYAR & BEATETAP
    if 'TGL_BAYAR' in cols and 'BEATETAP' in cols:
        return 'mb'
    
    # 2. MC (Master Catat) - Ciri: ZONA_NOVAK & TGL_CATAT
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols:
        return 'mc'
    
    # 3. COLLECTION (Daily) - Ciri: PAY_DT atau NOTAG
    if 'PAY_DT' in cols or 'NOTAG' in cols:
        return 'collection'
    
    # 4. ARDEBT (Tunggakan) - Ciri: PERIODE_BILL
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    # 5. RUTE JS (Mapping) - Ciri: PETUGAS & PCEZ
    if 'PETUGAS' in cols and 'PCEZ' in cols:
        return 'rute'
    
    return None

def save_chunk_to_db(df, file_type, bulan, tahun, db):
    """
    Logika penyimpanan data: MC ke master_pelanggan, MB ke master_bayar.
    """
    
    if file_type == 'mc':
        # Simpan ke master_pelanggan sebagai INDUK target
        for _, row in df.iterrows():
            zona = str(row.get('ZONA_NOVAK', '')).split('.')[0].strip()
            notagihan = str(row.get('NOTAGIHAN', '')).split('.')[0].strip()
            
            if len(zona) >= 9:
                # Rumus pemecahan ZONA_NOVAK
                rayon = zona[0:2]             
                pc    = zona[2:5]             
                ez    = zona[5:7]             
                pcez  = f"{pc}/{ez}".strip()  
                block = zona[7:9]             
            else:
                rayon = pc = ez = pcez = block = "Format Salah"

            db.execute("""
                INSERT INTO master_pelanggan 
                (nomen, nama, pcez, rayon, pc, ez, block, periode_bulan, periode_tahun, nominal, tipe) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MC')
            """, (
                notagihan, 
                row.get('NAMA_PEL', '-'), 
                pcez, rayon, pc, ez, block, bulan, tahun, 
                pd.to_numeric(row.get('NOMINAL'), errors='coerce') or 0
            ))
            
    elif file_type == 'mb':
        # Simpan ke tabel master_bayar khusus untuk pelunasan
        for _, row in df.iterrows():
            notagihan = str(row.get('NOTAGIHAN', '')).split('.')[0].strip()
            db.execute("""
                INSERT INTO master_bayar (nomen, nama, nominal, periode_bulan, periode_tahun)
                VALUES (?, ?, ?, ?, ?)
            """, (
                notagihan, 
                'MASTER BAYAR', 
                pd.to_numeric(row.get('NOMINAL'), errors='coerce') or 0,
                bulan, 
                tahun
            ))
            
    elif file_type == 'collection':
        for _, row in df.iterrows():
            notag = str(row.get('NOTAG', '')).split('.')[0].strip()
            db.execute("""
                INSERT INTO collection_harian (nomen, pay_dt, nominal, periode_bulan, periode_tahun)
                VALUES (?, ?, ?, ?, ?)
            """, (notag, row.get('PAY_DT'), row.get('AMT_COLLECT'), bulan, tahun))

    elif file_type == 'ardebt':
        for _, row in df.iterrows():
            db.execute("""
                INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume)
                VALUES (?, ?, ?, ?)
            """, (str(row.get('NOMEN')).split('.')[0], row.get('PERIODE_BILL'), row.get('JUMLAH'), row.get('VOLUME')))

    elif file_type == 'rute':
        for _, row in df.iterrows():
            pcez_val = str(row.get('PCEZ', '')).strip()
            petugas_val = str(row.get('PETUGAS', '')).strip()
            db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)",
                       (pcez_val, petugas_val))

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
        if temp_path.endswith('.csv'):
            df_sample = pd.read_csv(temp_path, nrows=10, dtype=str)
        else:
            df_sample = pd.read_excel(temp_path, nrows=10, dtype=str)

        file_type = identify_file_type(df_sample)
        if not file_type:
            return jsonify({"error": "Sistem tidak mengenali format kolom file ini."}), 400

        bulan, tahun = detect_file_period(df_sample, file_type)

        if temp_path.endswith('.csv'):
            for chunk in pd.read_csv(temp_path, chunksize=10000, dtype=str):
                save_chunk_to_db(chunk, file_type, bulan, tahun, db)
        else:
            df_full = pd.read_excel(temp_path, dtype=str)
            save_chunk_to_db(df_full, file_type, bulan, tahun, db)

        db.execute("INSERT INTO upload_history (filename, file_type, periode, status) VALUES (?, ?, ?, ?)",
                   (file.filename, file_type.upper(), f"{bulan}/{tahun}" if bulan else "-", "Berhasil"))
        db.commit()
        
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"status": "success", "detected": file_type.upper(), "message": "Proses selesai!"})

    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"error": str(e)}), 500
