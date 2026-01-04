import os
import pandas as pd
from flask import Blueprint, request, jsonify
from core.database import get_db_connection
from processors.auto_detect import identify_file_type

upload_bp = Blueprint('upload', __name__)

def clean_nomen(val):
    if pd.isna(val) or val == "": return None
    return str(val).split('.')[0].strip()

def save_to_db(df, file_type, db):
    if file_type == 'mc':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            zona = str(row.get('ZONA_NOVAK', '000000000')).split('.')[0]
            pcez_val = f"{zona[2:5]}/{zona[5:7]}" if len(zona) >= 7 else "000/00"
            # PC di file Excel Anda adalah Rayon
            rayon_val = str(row.get('PC', '')).split('.')[0]
            db.execute("""
                INSERT INTO master_pelanggan (nomen, nama, pcez, rayon, block, nominal) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nomen, row.get('NAMA_PEL'), pcez_val, rayon_val, zona[7:9], row.get('NOMINAL')))

    elif file_type == 'rute':
        # Fitur Upload Rute: Menambah/Update petugas berdasarkan file Excel
        for _, row in df.iterrows():
            pcez = str(row.get('PCEZ', '')).strip()
            petugas = str(row.get('PETUGAS', '')).strip().upper()
            if pcez and petugas:
                db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", (pcez, petugas))

    elif file_type == 'mb':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if nomen:
                db.execute("INSERT OR REPLACE INTO master_bayar (nomen, nominal) VALUES (?, ?)", (nomen, row.get('NOMINAL')))

    elif file_type == 'collection':
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if nomen:
                db.execute("INSERT OR REPLACE INTO collection_harian (nomen, notag, nominal) VALUES (?, ?, ?)", 
                           (nomen, row.get('NOTAG'), row.get('AMT_COLLECT')))

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    db = get_db_connection()
    try:
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        file_type = identify_file_type(df)
        if not file_type: return jsonify({"error": "Format tidak dikenal"}), 400
        save_to_db(df, file_type, db)
        db.commit()
        return jsonify({"status": "success", "message": f"Berhasil upload {file_type.upper()}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
