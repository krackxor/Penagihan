import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def clean_pcez(val):
    """
    Menyeragamkan format PCEZ menjadi standar XXX/XX.
    Contoh: 
    - 9602    -> 096/02
    - 09602   -> 096/02
    - 096/02  -> 096/02
    - 96/2    -> 096/02
    """
    if pd.isna(val) or str(val).strip().upper() == 'NAN':
        return None
    
    # Ambil angka saja
    s = ''.join(filter(str.isdigit, str(val)))
    
    if len(s) == 4: # Kasus 9602
        s = "0" + s
    
    if len(s) == 5: # Kasus 09602
        return f"{s[:3]}/{s[3:]}"
    
    # Jika format tidak standar, coba bersihkan manual jika ada '/'
    if '/' in str(val):
        parts = str(val).split('/')
        if len(parts) == 2:
            p1 = parts[0].strip().zfill(3)
            p2 = parts[1].strip().zfill(2)
            return f"{p1}/{p2}"
            
    return str(val).strip()

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # Membaca excel dengan konversi string untuk menghindari angka dibaca float (.0)
        df = pd.read_excel(file, dtype=str)
        file_type = identify_file_type(df)
        
        if not file_type:
            return jsonify({"error": "Format kolom file tidak dikenali"}), 400

        bulan, tahun = detect_file_period(df, file_type)
        periode_info = f" ({bulan}/{tahun})" if bulan else ""

        # Normalisasi Header
        df.columns = [str(c).upper().strip() for c in df.columns]

        if file_type == 'rute':
            # Opsional: Hapus rute lama agar data petugas selalu fresh
            # db.execute("DELETE FROM rute_petugas") 
            
            count = 0
            for _, row in df.iterrows():
                pcez = clean_pcez(row.get('PCEZ'))
                petugas = str(row.get('PETUGAS', '')).strip().upper()
                
                if pcez and petugas and petugas != 'NAN':
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", (pcez, petugas))
                    count += 1
            print(f"Berhasil memproses {count} data rute.")

        elif file_type == 'mc':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                # Ekstrak PCEZ dari ZONA_NOVAK secara konsisten
                zona = str(row.get('ZONA_NOVAK', '')).split('.')[0].replace("'", "")
                
                # Format ZONA_NOVAK biasanya: 350960217 -> 096/02
                if len(zona) >= 7:
                    raw_pcez = f"{zona[2:5]}/{zona[5:7]}"
                else:
                    raw_pcez = "000/00"
                
                pcez_val = clean_pcez(raw_pcez)
                
                db.execute("""
                    INSERT OR REPLACE INTO master_pelanggan (nomen, nama, pcez, rayon, block, nominal, tipe) 
                    VALUES (?, ?, ?, ?, ?, ?, 'MC')
                """, (
                    nomen, 
                    row.get('NAMA_PEL'), 
                    pcez_val, 
                    str(row.get('PC', row.get('RAYON', ''))).split('.')[0], 
                    zona[7:9] if len(zona) >= 9 else '00', 
                    row.get('NOMINAL')
                ))

        elif file_type == 'mb':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if nomen and nomen != 'NAN':
                    db.execute("INSERT OR REPLACE INTO master_bayar (nomen, nominal) VALUES (?, ?)", 
                              (nomen, row.get('NOMINAL')))

        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Data {file_type.upper()} Berhasil Diperbarui{periode_info}"
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Gagal memproses file: {str(e)}"}), 500
    finally:
        db.close()
