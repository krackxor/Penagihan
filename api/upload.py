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
    
    val_str = str(val).strip().replace(" ", "")
    
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
    if len(s) >= 7: 
        return f"{s[2:5]}/{s[5:7]}"
            
    return val_str

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # Load data sebagai string untuk menjaga keaslian ID
        df = pd.read_excel(file, dtype=str)
        file_type = identify_file_type(df)
        
        if not file_type:
            return jsonify({"error": "Format kolom file tidak dikenali"}), 400

        # detect_file_period otomatis melakukan +1 bulan untuk MC, MB, dan Ardebt
        bulan, tahun = detect_file_period(df, file_type)
        periode_str = f"{str(bulan).zfill(2)}-{tahun}" if bulan else None
        periode_info = f" ({periode_str})" if periode_str else ""

        df.columns = [str(c).upper().strip() for c in df.columns]

        if file_type == 'rute':
            count = 0
            for _, row in df.iterrows():
                pcez = clean_pcez(row.get('PCEZ'))
                petugas_raw = str(row.get('PETUGAS', '')).strip().upper()
                
                if pcez and petugas_raw and petugas_raw not in ('', 'NAN', 'NULL'):
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                               (pcez, petugas_raw))
                    count += 1

        elif file_type == 'mc':
            count_mc = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                nomet = str(row.get('NOMET', '')).split('.')[0].strip()
                notag = str(row.get('NOTAGIHAN', '')).split('.')[0].strip()
                
                if not nomen or nomen == 'NAN': continue
                
                zona = str(row.get('ZONA_NOVAK', '')).split('.')[0].replace("'", "").strip()
                pcez_val = clean_pcez(zona) 
                
                db.execute("""
                    INSERT INTO master_pelanggan (nomen, notagihan, nomet, nama, pcez, nominal, tipe, periode) 
                    VALUES (?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (
                    nomen, notag if notag != 'NAN' else None,
                    nomet if nomet != 'NAN' else None,
                    row.get('NAMA_PEL'), pcez_val, row.get('NOMINAL'), periode_str
                ))
                count_mc += 1

        elif file_type == 'mb':
            count_mb = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                notag = str(row.get('NOTAGIHAN', '')).split('.')[0].strip()
                if nomen and nomen != 'NAN':
                    db.execute("""
                        INSERT INTO master_bayar (nomen, notagihan, nominal, periode) 
                        VALUES (?, ?, ?, ?)
                    """, (nomen, notag if notag != 'NAN' else None, row.get('NOMINAL'), periode_str))
                    count_mb += 1

        elif file_type == 'collection':
            count_coll = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                # PERBAIKAN: Menggunakan field 'notag' sesuai skema DB terbaru
                notag = str(row.get('NOTAG', '')).split('.')[0].strip() 
                
                if nomen and nomen != 'NAN':
                    db.execute("""
                        INSERT INTO collection_harian (nomen, notag, nominal, periode) 
                        VALUES (?, ?, ?, ?)
                    """, (nomen, notag if notag != 'NAN' else None, row.get('NOMINAL'), periode_str))
                    count_coll += 1

        elif file_type == 'ardebt':
            # Kosongkan tabel ardebt lama agar data selalu aktual
            db.execute("DELETE FROM ardebt")
            count_ard = 0
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                jumlah = row.get('JUMLAH')
                volume = row.get('VOLUME')
                per_bill = str(row.get('PERIODE_BILL', '')).strip()
                
                if nomen and nomen != 'NAN':
                    db.execute("""
                        INSERT INTO ardebt (nomen, jumlah, volume, periode_bill) 
                        VALUES (?, ?, ?, ?)
                    """, (nomen, jumlah, volume, per_bill))
                    count_ard += 1

        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Data {file_type.upper()} Berhasil Diperbarui{periode_info}",
            "type": file_type
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if db: db.close()

@upload_bp.route('/data-status', methods=['GET'])
def get_data_status():
    """Endpoint untuk dashboard Health Check: mengecek ketersediaan data."""
    db = get_db_connection()
    status = {}
    tables = {
        'MC': 'master_pelanggan',
        'MB': 'master_bayar',
        'Collection': 'collection_harian',
        'Ardebt': 'ardebt'
    }
    
    try:
        for label, table in tables.items():
            # Menggunakan updated_at untuk Ardebt dan periode untuk lainnya
            if label == 'Ardebt':
                res = db.execute(f"SELECT updated_at FROM {table} LIMIT 1").fetchone()
            else:
                res = db.execute(f"SELECT periode FROM {table} LIMIT 1").fetchone()
            
            status[label] = {"exists": True if res else False}
            
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
