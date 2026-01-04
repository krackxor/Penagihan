import os
import pandas as pd
from flask import Blueprint, request, jsonify
from core.database import get_db_connection
from processors.auto_detect import identify_file_type

upload_bp = Blueprint('upload', __name__)

def clean_nomen(val):
    """Membersihkan format nomen agar tidak ada desimal .0"""
    if pd.isna(val) or val == "":
        return None
    return str(val).split('.')[0].strip()

def save_to_db(df, file_type, db):
    """Logika penyimpanan berdasarkan identifikasi file"""
    
    if file_type == 'mc':
        # Hapus data MC lama jika ingin refresh total (Opsional)
        # db.execute("DELETE FROM master_pelanggan WHERE tipe = 'MC'")
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            # Olah ZONA_NOVAK menjadi PCEZ & Block
            zona = str(row.get('ZONA_NOVAK', '000000000')).split('.')[0]
            pcez_val = f"{zona[2:5]}/{zona[5:7]}" if len(zona) >= 7 else "000/00"
            block_val = zona[7:9] if len(zona) >= 9 else ""
            
            # Kolom PC di file Anda adalah Rayon
            rayon_val = str(row.get('PC', '')).split('.')[0]

            db.execute("""
                INSERT INTO master_pelanggan (nomen, nama, pcez, rayon, block, nominal) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nomen, row.get('NAMA_PEL'), pcez_val, rayon_val, block_val, row.get('NOMINAL')))

    elif file_type == 'mb':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            db.execute("INSERT OR REPLACE INTO master_bayar (nomen, nominal) VALUES (?, ?)", 
                       (nomen, row.get('NOMINAL')))
            
    elif file_type == 'collection':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            # Menggunakan AMT_COLLECT sesuai file Anda
            db.execute("INSERT OR REPLACE INTO collection_harian (nomen, notag, nominal) VALUES (?, ?, ?)", 
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
        db.execute("DELETE FROM rute_petugas") # Reset rute tiap upload baru
        for _, row in df.iterrows():
            pcez = str(row.get('PCEZ', '')).strip()
            petugas = str(row.get('PETUGAS', '')).strip()
            if pcez and petugas:
                db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                           (pcez, petugas))

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Tidak ada file"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # Baca Excel / CSV
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # Deteksi jenis file (MC, MB, Col, Ardebt, atau Rute)
        file_type = identify_file_type(df)
        if not file_type:
            return jsonify({"error": "Format kolom file tidak dikenali"}), 400

        save_to_db(df, file_type, db)
        db.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Berhasil mengunggah {file_type.upper()}"
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Gagal simpan: {str(e)}"}), 500
    finally:
        db.close()
