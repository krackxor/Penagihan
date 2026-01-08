import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def clean_pcez(val):
    """Menyeragamkan format PCEZ menjadi standar XXX/XX secara ketat."""
    if pd.isna(val) or str(val).strip().upper() in ('NAN', 'NULL', ''):
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
    """Endpoint untuk memproses unggahan file Excel dengan penanganan data kosong yang robust."""
    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # Load data sebagai string dan bersihkan nilai NaN agar tidak kosong saat diproses
        df = pd.read_excel(file, dtype=str)
        df = df.fillna('') 
        
        file_type = identify_file_type(df)
        if not file_type:
            return jsonify({"error": "Format kolom file tidak dikenali. Pastikan kolom sesuai template."}), 400

        bulan, tahun = detect_file_period(df, file_type)
        periode_str = f"{str(bulan).zfill(2)}-{tahun}" if bulan else None
        periode_info = f" ({periode_str})" if periode_str else ""

        # Standarisasi Nama Kolom
        df.columns = [str(c).upper().strip() for c in df.columns]

        # 1. PROSES RUTE PETUGAS
        if file_type == 'rute':
            for _, row in df.iterrows():
                pcez = clean_pcez(row.get('PCEZ'))
                petugas = str(row.get('PETUGAS', '')).strip().upper()
                if pcez and petugas not in ('', 'NAN', 'NULL'):
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                               (pcez, petugas))

        # 2. PROSES MASTER CATAT (MC) - Penanganan Nomet, Nominal, & Volume (KUBIK)
        elif file_type == 'mc':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                # Pastikan Nomet dan Nominal diambil dengan benar dan tidak kosong
                nomet = str(row.get('NOMET', '')).split('.')[0].strip()
                notag = str(row.get('NOTAGIHAN', '')).split('.')[0].strip()
                zona = str(row.get('ZONA_NOVAK', '')).split('.')[0].replace("'", "").strip()
                
                # Konversi angka secara aman
                nominal = float(row.get('NOMINAL', 0)) if row.get('NOMINAL') != '' else 0.0
                volume = float(row.get('KUBIK', 0)) if row.get('KUBIK') != '' else 0.0
                
                db.execute("""
                    INSERT OR REPLACE INTO master_pelanggan 
                    (nomen, notagihan, nomet, nama, pcez, nominal, volume, tipe, periode) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (
                    nomen, 
                    notag if notag != 'NAN' else None,
                    nomet if nomet != 'NAN' else None,
                    row.get('NAMA_PEL'), 
                    clean_pcez(zona), 
                    nominal, 
                    volume,
                    periode_str
                ))

        # 3. PROSES MASTER BAYAR (MB)
        elif file_type == 'mb':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, notagihan, nominal, periode) 
                    VALUES (?, ?, ?, ?)
                """, (
                    nomen, 
                    str(row.get('NOTAGIHAN', '')).split('.')[0].strip(), 
                    float(row.get('NOMINAL', 0)) if row.get('NOMINAL') != '' else 0.0, 
                    periode_str
                ))

        # 4. PROSES COLLECTION HARIAN
        elif file_type == 'collection':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, notag, nominal, periode) 
                    VALUES (?, ?, ?, ?)
                """, (
                    nomen, 
                    str(row.get('NOTAG', '')).split('.')[0].strip(), 
                    float(row.get('NOMINAL', 0)) if row.get('NOMINAL') != '' else 0.0, 
                    periode_str
                ))

        # 5. PROSES ARDEBT (TUNGGAKAN BEREKOR)
        elif file_type == 'ardebt':
            db.execute("DELETE FROM ardebt")
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                db.execute("""
                    INSERT INTO ardebt (nomen, jumlah, volume, periode_bill) 
                    VALUES (?, ?, ?, ?)
                """, (
                    nomen, 
                    float(row.get('JUMLAH', 0)) if row.get('JUMLAH') != '' else 0.0, 
                    float(row.get('VOLUME', 0)) if row.get('VOLUME') != '' else 0.0, 
                    str(row.get('PERIODE_BILL', '')).strip()
                ))

        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Data {file_type.upper()} berhasil diproses{periode_info}",
            "type": file_type
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": f"Gagal memproses file: {str(e)}"}), 500
    finally:
        if db: db.close()

@upload_bp.route('/data-status', methods=['GET'])
def get_data_status():
    """Endpoint Health Check dengan rincian jumlah data."""
    db = get_db_connection()
    status = {}
    tables = {'MC': 'master_pelanggan', 'MB': 'master_bayar', 'Collection': 'collection_harian', 'Ardebt': 'ardebt'}
    try:
        for label, table in tables.items():
            res = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            status[label] = {"exists": True if res[0] > 0 else False, "count": res[0]}
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
