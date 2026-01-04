import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def clean_pcez(val):
    """
    Menyeragamkan format PCEZ menjadi standar XXX/XX secara ketat.
    """
    if pd.isna(val) or str(val).strip().upper() == 'NAN' or str(val).strip() == '':
        return None
    
    val_str = str(val).strip()
    
    # Jika format sudah mengandung '/', pecah dan zfill
    if '/' in val_str:
        parts = val_str.split('/')
        if len(parts) == 2:
            p1 = ''.join(filter(str.isdigit, parts[0])).zfill(3)
            p2 = ''.join(filter(str.isdigit, parts[1])).zfill(2)
            return f"{p1}/{p2}"
    
    # Jika format angka rapat (9602 atau 09602)
    s = ''.join(filter(str.isdigit, val_str))
    if len(s) == 4: # 9602 -> 096/02
        return f"0{s[:2]}/{s[2:]}"
    if len(s) == 5: # 09602 -> 096/02
        return f"{s[:3]}/{s[3:]}"
            
    return val_str

def is_valid_petugas(petugas):
    """
    Validasi nama petugas - menolak nilai kosong/placeholder
    """
    if not petugas:
        return False
    
    petugas_upper = str(petugas).strip().upper()
    
    # Daftar nilai yang dianggap tidak valid
    invalid_values = ['', 'NAN', 'NONE', 'NULL', '-', 'N/A', 'NA']
    
    return petugas_upper not in invalid_values and len(petugas_upper) >= 2

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # Membaca excel sebagai string untuk menjaga integritas data Nomen & Zona
        df = pd.read_excel(file, dtype=str)
        file_type = identify_file_type(df)
        
        if not file_type:
            return jsonify({"error": "Format kolom file tidak dikenali"}), 400

        bulan, tahun = detect_file_period(df, file_type)
        periode_info = f" ({bulan}/{tahun})" if bulan else ""

        # Normalisasi Header ke Uppercase
        df.columns = [str(c).upper().strip() for c in df.columns]

        if file_type == 'rute':
            count = 0
            skipped = 0
            for _, row in df.iterrows():
                pcez = clean_pcez(row.get('PCEZ'))
                petugas_raw = str(row.get('PETUGAS', '')).strip().upper()
                
                # ✅ VALIDASI LEBIH KETAT
                if pcez and is_valid_petugas(petugas_raw):
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                               (pcez, petugas_raw))
                    count += 1
                else:
                    skipped += 1
                    print(f"⚠️ Dilewati - PCEZ: {pcez}, Petugas: {petugas_raw}")
            
            print(f"✅ Berhasil sinkronisasi {count} rute petugas. Dilewati: {skipped}")

        elif file_type == 'mc':
            count_mc = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen == 'NAN': continue
                
                # Ekstrak Zona Novak (Contoh: 350960217)
                zona = str(row.get('ZONA_NOVAK', '')).split('.')[0].replace("'", "").strip()
                
                # Standarisasi PCEZ dari Zona Novak: Ambil digit ke 3-5 dan 6-7
                if len(zona) >= 7:
                    raw_pcez = f"{zona[2:5]}/{zona[5:7]}"
                else:
                    raw_pcez = "000/00"
                
                # Bersihkan pcez agar formatnya XXX/XX sama dengan tabel rute_petugas
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
                count_mc += 1
            print(f"✅ Berhasil memproses {count_mc} pelanggan MC.")

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
        if db: db.rollback()
        return jsonify({"error": f"Gagal memproses file: {str(e)}"}), 500
    finally:
        if db: db.close()
