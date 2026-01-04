import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def format_pcez(val):
    """Memastikan PCEZ rute sinkron dengan MC (Contoh: 09602 -> 096/02)"""
    s = str(val).strip().replace('.', '').replace(' ', '')
    if '/' in s: return s
    if len(s) == 5: return f"{s[:3]}/{s[3:]}"
    if len(s) == 4: return f"0{s[:2]}/{s[2:]}"
    return s

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        df = pd.read_excel(file)
        file_type = identify_file_type(df)
        
        if not file_type:
            return jsonify({"error": "Kolom tidak sesuai standar"}), 400

        # Panggil fungsi deteksi periode milik Anda
        bulan, tahun = detect_file_period(df, file_type)
        periode_info = f" ({bulan}/{tahun})" if bulan else ""

        # Normalisasi Kolom ke Uppercase
        df.columns = [str(c).upper().strip() for c in df.columns]

        if file_type == 'rute':
            for _, row in df.iterrows():
                pcez = format_pcez(row.get('PCEZ'))
                petugas = str(row.get('PETUGAS', '')).strip().upper()
                if pcez and petugas:
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", (pcez, petugas))

        elif file_type == 'mc':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                zona = str(row.get('ZONA_NOVAK', '000000000')).split('.')[0]
                pcez_val = f"{zona[2:5]}/{zona[5:7]}" if len(zona) >= 7 else "000/00"
                
                db.execute("""
                    INSERT OR REPLACE INTO master_pelanggan (nomen, nama, pcez, rayon, block, nominal, tipe) 
                    VALUES (?, ?, ?, ?, ?, ?, 'MC')
                """, (nomen, row.get('NAMA_PEL'), pcez_val, str(row.get('PC')).split('.')[0], zona[7:9], row.get('NOMINAL')))

        elif file_type == 'mb':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if nomen:
                    db.execute("INSERT OR REPLACE INTO master_bayar (nomen, nominal) VALUES (?, ?)", (nomen, row.get('NOMINAL')))

        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Data {file_type.upper()} Berhasil Diperbarui{periode_info}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
