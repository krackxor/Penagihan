import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def clean_pcez(val):
    """Menyeragamkan format PCEZ menjadi standar XXX/XX secara ketat."""
    if pd.isna(val) or str(val).strip().upper() == 'NAN' or str(val).strip() == '':
        return None
    
    val_str = str(val).strip()
    
    if '/' in val_str:
        parts = val_str.split('/')
        if len(parts) == 2:
            p1 = ''.join(filter(str.isdigit, parts[0])).zfill(3)
            p2 = ''.join(filter(str.isdigit, parts[1])).zfill(2)
            return f"{p1}/{p2}"
    
    s = ''.join(filter(str.isdigit, val_str))
    if len(s) == 4:
        return f"0{s[:2]}/{s[2:]}"
    if len(s) == 5:
        return f"{s[:3]}/{s[3:]}"
            
    return val_str

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # Load data sebagai string untuk mencegah perubahan format ID (IDPEL/NOTAG)
        df = pd.read_excel(file, dtype=str)
        file_type = identify_file_type(df)
        
        if not file_type:
            return jsonify({"error": "Format kolom file tidak dikenali"}), 400

        # DETEKSI PERIODE OTOMATIS DARI ISI FILE
        bulan, tahun = detect_file_period(df, file_type)
        # Format periode standar: MM-YYYY (Digunakan sebagai kunci Pintu Ganda 2)
        periode_str = f"{str(bulan).zfill(2)}-{tahun}" if bulan else None
        periode_info = f" ({periode_str})" if periode_str else ""

        df.columns = [str(c).upper().strip() for c in df.columns]

        if file_type == 'rute':
            count = 0
            for _, row in df.iterrows():
                pcez = clean_pcez(row.get('PCEZ'))
                petugas_raw = str(row.get('PETUGAS', '')).strip().upper()
                
                if (pcez and petugas_raw and 
                    petugas_raw not in ('', 'NAN', 'NONE', 'NULL', '-', 'N/A', 'NA') and
                    len(petugas_raw) >= 2):
                    
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                               (pcez, petugas_raw))
                    count += 1
            print(f"✅ Berhasil sinkronisasi {count} rute petugas.")

        elif file_type == 'mc':
            count_mc = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                nomet = str(row.get('NOMET', '')).split('.')[0].strip()
                notag = str(row.get('NOTAGIHAN', '')).split('.')[0].strip() # Pintu Ganda 1
                
                if not nomen or nomen == 'NAN': continue
                
                zona = str(row.get('ZONA_NOVAK', '')).split('.')[0].replace("'", "").strip()
                pcez_val = clean_pcez(f"{zona[2:5]}/{zona[5:7]}" if len(zona) >= 7 else "000/00")
                
                # INSERT MC sebagai target utama
                db.execute("""
                    INSERT INTO master_pelanggan (nomen, notagihan, nomet, nama, pcez, rayon, block, nominal, tipe, periode) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (
                    nomen,
                    notag if notag != 'NAN' else None,
                    nomet if nomet != 'NAN' else None,
                    row.get('NAMA_PEL'), 
                    pcez_val, 
                    str(row.get('PC', row.get('RAYON', ''))).split('.')[0], 
                    zona[7:9] if len(zona) >= 9 else '00', 
                    row.get('NOMINAL'),
                    periode_str
                ))
                count_mc += 1
            print(f"✅ Berhasil memproses {count_mc} pelanggan MC periode {periode_str}.")

        elif file_type == 'mb':
            count_mb = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                notag = str(row.get('NOTAGIHAN', '')).split('.')[0].strip() # Pintu Ganda 1
                
                if nomen and nomen != 'NAN':
                    # INSERT MB (Status: UNDUE jika periode MB = periode MC)
                    db.execute("""
                        INSERT INTO master_bayar (nomen, notagihan, nominal, tgl_bayar, periode) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        nomen, 
                        notag if notag != 'NAN' else None,
                        row.get('NOMINAL'),
                        row.get('TGL_BAYAR'),
                        periode_str
                    ))
                    count_mb += 1
            print(f"✅ Berhasil memproses {count_mb} data MB periode {periode_str}.")

        elif file_type == 'collection':
            count_coll = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                notag = str(row.get('NOTAG', '')).split('.')[0].strip() # Pintu Ganda 1 (Field file: NOTAG)
                
                if nomen and nomen != 'NAN':
                    # INSERT Collection (Status: CURRENT jika periode Coll > periode MC)
                    db.execute("""
                        INSERT INTO collection_harian (nomen, notagihan, nominal, pay_dt, periode) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        nomen,
                        notag if notag != 'NAN' else None,
                        row.get('NOMINAL'),
                        row.get('PAY_DT'),
                        periode_str
                    ))
                    count_coll += 1
            print(f"✅ Berhasil memproses {count_coll} data Collection periode {periode_str}.")

        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Data {file_type.upper()} Berhasil Diperbarui{periode_info}"
        })

    except Exception as e:
        if db: db.rollback()
        print(f"❌ Error Upload: {str(e)}")
        return jsonify({"error": f"Gagal memproses file: {str(e)}"}), 500
    finally:
        if db: db.close()
