import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection

upload_bp = Blueprint('upload', __name__)

def identify_file_type(df):
    cols = [c.upper() for c in df.columns]
    if 'ZONA_NOVAK' in cols and 'NAMA_PEL' in cols: return 'mc'
    if 'TGL_BAYAR' in cols and 'BEATETAP' in cols: return 'mb'
    if 'AMT_COLLECT' in cols or 'NOTAG' in cols: return 'collection'
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols: return 'ardebt'
    if 'PCEZ' in cols and 'PETUGAS' in cols: return 'rute'
    return None

def save_chunk_to_db(df, file_type, db):
    if file_type == 'mc':
        for _, row in df.iterrows():
            zona = str(row.get('ZONA_NOVAK', '000000000')).split('.')[0]
            pcez = f"{zona[2:5]}/{zona[5:7]}" if len(zona) >= 7 else "000/00"
            db.execute("""INSERT INTO master_pelanggan (nomen, nama, pcez, rayon, block, nominal) 
                          VALUES (?, ?, ?, ?, ?, ?)""", 
                       (str(row.get('NOMEN')).split('.')[0], row.get('NAMA_PEL'), pcez, row.get('PC'), zona[7:9], row.get('NOMINAL')))
    
    elif file_type == 'mb':
        for _, row in df.iterrows():
            db.execute("INSERT INTO master_bayar (nomen, nominal) VALUES (?, ?)", 
                       (str(row.get('NOMEN')).split('.')[0], row.get('NOMINAL')))
            
    elif file_type == 'collection':
        for _, row in df.iterrows():
            db.execute("INSERT INTO collection_harian (nomen, notag, nominal) VALUES (?, ?, ?)", 
                       (str(row.get('NOMEN')).split('.')[0], row.get('NOTAG'), row.get('AMT_COLLECT')))

    elif file_type == 'ardebt':
        for _, row in df.iterrows():
            db.execute("INSERT OR REPLACE INTO ardebt (nomen, jumlah, volume, periode_bill) VALUES (?, ?, ?, ?)", 
                       (str(row.get('NOMEN')).split('.')[0], row.get('JUMLAH'), row.get('VOLUME'), row.get('PERIODE_BILL')))

    elif file_type == 'rute':
        for _, row in df.iterrows():
            db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                       (str(row.get('PCEZ')).strip(), str(row.get('PETUGAS')).strip()))

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400

    db = get_db_connection()
    try:
        # Gunakan Engine Openpyxl untuk .xlsx dan .xls
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, dtype=str)
        else:
            df = pd.read_excel(file, dtype=str)

        file_type = identify_file_type(df)
        if not file_type: return jsonify({"error": "Format kolom tidak dikenali"}), 400

        save_chunk_to_db(df, file_type, db)
        db.commit()
        
        return jsonify({"status": "success", "detected": file_type.upper()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
