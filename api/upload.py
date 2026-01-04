import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from processors.auto_detect import identify_file_type

upload_bp = Blueprint('upload', __name__)

def clean_nomen(val):
    """
    Menghilangkan .0 dari Nomen jika terbaca sebagai float oleh Excel.
    Contoh: 30013845.0 menjadi '30013845'
    """
    if pd.isna(val) or val == "":
        return None
    return str(val).split('.')[0].strip()

def save_to_db(df, file_type, db):
    """Logika penyimpanan berdasarkan jenis file yang terdeteksi secara otomatis"""
    
    if file_type == 'mc':
        # Membersihkan data MC lama bisa diaktifkan jika ingin refresh data total
        # db.execute("DELETE FROM master_pelanggan")
        
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            # Olah ZONA_NOVAK (Contoh: 350960217 -> 096/02)
            zona = str(row.get('ZONA_NOVAK', '000000000')).split('.')[0]
            pcez_val = f"{zona[2:5]}/{zona[5:7]}" if len(zona) >= 7 else "000/00"
            
            # Sesuai file Anda: PC adalah Rayon
            rayon_val = str(row.get('PC', '')).split('.')[0]
            block_val = zona[7:9] if len(zona) >= 9 else ""

            db.execute("""
                INSERT INTO master_pelanggan (nomen, nama, pcez, rayon, block, nominal) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                nomen, 
                row.get('NAMA_PEL'), 
                pcez_val, 
                rayon_val, 
                block_val, 
                row.get('NOMINAL')
            ))

    elif file_type == 'rute':
        # Upload Rute: Petugas & PCEZ (Contoh: 096/02 | PIAN)
        for _, row in df.iterrows():
            pcez = str(row.get('PCEZ', '')).strip()
            petugas = str(row.get('PETUGAS', '')).strip().upper()
            if pcez and petugas:
                db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                           (pcez, petugas))

    elif file_type == 'mb':
        # Upload Master Bayar
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if nomen:
                db.execute("INSERT OR REPLACE INTO master_bayar (nomen, nominal) VALUES (?, ?)", 
                           (nomen, row.get('NOMINAL')))

    elif file_type == 'collection':
        # Upload Collection Harian (Gunakan AMT_COLLECT sesuai file Anda)
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if nomen:
                db.execute("INSERT OR REPLACE INTO collection_harian (nomen, notag, nominal) VALUES (?, ?, ?)", 
                           (nomen, row.get('NOTAG'), row.get('AMT_COLLECT')))

    elif file_type == 'ardebt':
        # Upload Tunggakan Ardebt
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if nomen:
                db.execute("""
                    INSERT OR REPLACE INTO ardebt (nomen, jumlah, volume, periode_bill) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, row.get('JUMLAH'), row.get('VOLUME'), row.get('PERIODE_BILL')))

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Tidak ada file yang dipilih"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nama file kosong"}), 400

    db = get_db_connection()
    try:
        # Membaca format .xls (MC lama) atau .xlsx (Rute/Collection)
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # 1. Deteksi Jenis File berdasarkan Header Kolom
        file_type = identify_file_type(df)
        if not file_type:
            return jsonify({"error": "Format kolom tidak dikenali oleh sistem"}), 400

        # 2. Proses Simpan
        save_to_db(df, file_type, db)
        db.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Berhasil mengunggah data {file_type.upper()}"
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Gagal membaca file: {str(e)}"}), 500
    finally:
        db.close()
