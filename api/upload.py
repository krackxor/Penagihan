import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from processors.auto_detect import identify_file_type

upload_bp = Blueprint('upload', __name__)

def clean_nomen(val):
    """Membersihkan format nomen dari Excel agar tidak ada desimal .0"""
    if pd.isna(val) or val == "":
        return None
    # Mengonversi ke string dan membuang desimal (misal 3001.0 -> 3001)
    return str(val).split('.')[0].strip()

def save_to_db(df, file_type, db):
    """Menyimpan data ke tabel yang sesuai berdasarkan tipe file yang terdeteksi"""
    
    if file_type == 'mc':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            # Logika pecah ZONA_NOVAK menjadi PCEZ (Contoh: 350960217 -> 096/02)
            zona = str(row.get('ZONA_NOVAK', '000000000')).split('.')[0]
            pcez = f"{zona[2:5]}/{zona[5:7]}" if len(zona) >= 7 else "000/00"
            
            db.execute("""
                INSERT INTO master_pelanggan (nomen, nama, pcez, rayon, block, nominal) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nomen, row.get('NAMA_PEL'), pcez, row.get('PC'), zona[7:9], row.get('NOMINAL')))

    elif file_type == 'mb':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            db.execute("INSERT INTO master_bayar (nomen, nominal) VALUES (?, ?)", 
                       (nomen, row.get('NOMINAL')))
            
    elif file_type == 'collection':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            # Menggunakan AMT_COLLECT sesuai file Collection Anda
            db.execute("INSERT INTO collection_harian (nomen, notag, nominal) VALUES (?, ?, ?)", 
                       (nomen, row.get('NOTAG'), row.get('AMT_COLLECT')))

    elif file_type == 'ardebt':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            db.execute("""
                INSERT OR REPLACE INTO ardebt (nomen, jumlah, volume, periode_bill) 
                VALUES (?, ?, ?, ?)
            """, (nomen, row.get('JUMLAH'), row.get('VOLUME'), row.get('PERIODE_BILL')))

    elif file_type == 'rute':
        for _, row in df.iterrows():
            pcez = str(row.get('PCEZ', '')).strip()
            petugas = str(row.get('PETUGAS', '')).strip()
            if pcez and petugas:
                db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                           (pcez, petugas))

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Tidak ada file yang dipilih"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nama file kosong"}), 400

    try:
        # Membaca file (mendukung .xls, .xlsx, dan .csv)
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # 1. Identifikasi Tipe File
        file_type = identify_file_type(df)
        if not file_type:
            return jsonify({"error": "Format kolom tidak dikenali oleh sistem"}), 400

        # 2. Simpan ke Database
        db = get_db_connection()
        try:
            # Hapus data lama jika itu file Rute agar tidak duplikat
            if file_type == 'rute':
                db.execute("DELETE FROM rute_petugas")
            
            save_to_db(df, file_type, db)
            db.commit()
            
            return jsonify({
                "status": "success", 
                "detected": file_type.upper(),
                "message": f"Berhasil mengunggah data {file_type.upper()}"
            })
        except Exception as db_error:
            db.rollback()
            return jsonify({"error": f"Gagal simpan ke database: {str(db_error)}"}), 500
        finally:
            db.close()

    except Exception as e:
        return jsonify({"error": f"Gagal membaca file: {str(e)}"}), 500
