import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from core.helpers import APIResponse
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def clean_pcez(val):
    """Menyeragamkan format PCEZ menjadi standar XXX/XX secara ketat."""
    if pd.isna(val) or str(val).strip().upper() in ('NAN', 'NULL', ''):
        return None
    
    val_str = str(val).strip().replace(" ", "")
    
    # Deteksi Rayon dari awal string sebelum dibersihkan lebih lanjut
    # Biasanya Rayon adalah 2 angka pertama (34 atau 35)
    rayon_hint = val_str[:2] if val_str[:2] in ('34', '35') else None
    
    if '/' in val_str:
        parts = val_str.split('/')
        if len(parts) == 2:
            p1 = ''.join(filter(str.isdigit, parts[0])).zfill(3)
            p2 = ''.join(filter(str.isdigit, parts[1])).zfill(2)
            return f"{p1}/{p2}", rayon_hint
    
    s = ''.join(filter(str.isdigit, val_str))
    formatted_pcez = val_str
    if len(s) == 4:
        formatted_pcez = f"0{s[:2]}/{s[2:]}"
    elif len(s) == 5:
        formatted_pcez = f"{s[:3]}/{s[3:]}"
    elif len(s) >= 7: 
        formatted_pcez = f"{s[2:5]}/{s[5:7]}"
            
    return formatted_pcez, rayon_hint

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """Endpoint unggahan file dengan fitur Auto-Rayon Mapping."""
    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    row_count = 0
    
    try:
        # Load data sebagai string untuk mencegah hilangnya angka nol di depan (IDPEL)
        df = pd.read_excel(file, dtype=str)
        df = df.fillna('') 
        
        file_type = identify_file_type(df)
        if not file_type:
            return jsonify({"error": "Format kolom file tidak dikenali. Gunakan template resmi."}), 400

        bulan, tahun = detect_file_period(df, file_type)
        periode_str = f"{str(bulan).zfill(2)}-{tahun}" if bulan else None
        
        df.columns = [str(c).upper().strip() for c in df.columns]
        row_count = len(df)

        # 1. PROSES RUTE PETUGAS
        if file_type == 'rute':
            for _, row in df.iterrows():
                pcez, _ = clean_pcez(row.get('PCEZ'))
                petugas = str(row.get('PETUGAS', '')).strip().upper()
                if pcez and petugas not in ('', 'NAN', 'NULL'):
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                               (pcez, petugas))

        # 2. PROSES MASTER CATAT (MC) - Includes Auto-Rayon Logic
        elif file_type == 'mc':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                notag = str(row.get('NOTAGIHAN', '')).split('.')[0].strip()
                nomet = str(row.get('NOMET', '')).split('.')[0].strip()
                zona_raw = str(row.get('ZONA_NOVAK', '')).split('.')[0].replace("'", "").strip()
                
                # Standarisasi PCEZ dan ambil kode Rayon
                pcez_fixed, rayon = clean_pcez(zona_raw)
                
                nominal = float(str(row.get('NOMINAL', 0)).replace(',', '')) if row.get('NOMINAL') != '' else 0.0
                volume = float(str(row.get('KUBIK', 0)).replace(',', '')) if row.get('KUBIK') != '' else 0.0
                
                db.execute("""
                    INSERT OR REPLACE INTO master_pelanggan 
                    (nomen, notagihan, nomet, nama, pcez, rayon, nominal, volume, tipe, periode) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (
                    nomen, notag, nomet, row.get('NAMA_PEL'), 
                    pcez_fixed, rayon, nominal, volume, periode_str
                ))

        # 3. PROSES MASTER BAYAR (MB)
        elif file_type == 'mb':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                nominal = float(str(row.get('NOMINAL', 0)).replace(',', '')) if row.get('NOMINAL') != '' else 0.0
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, notagihan, nominal, periode) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, str(row.get('NOTAGIHAN', '')).split('.')[0].strip(), nominal, periode_str))

        # 4. PROSES COLLECTION HARIAN (Untuk Monitoring Harian)
        elif file_type == 'collection':
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                # Ambil tanggal bayar jika ada di file, jika tidak pakai tanggal hari ini
                pay_dt = row.get('PAY_DT') or datetime.now().strftime('%Y-%m-%d')
                
                nominal = float(str(row.get('NOMINAL', 0)).replace(',', '')) if row.get('NOMINAL') != '' else 0.0
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, notag, nominal, pay_dt, periode) 
                    VALUES (?, ?, ?, ?, ?)
                """, (nomen, str(row.get('NOTAG', '')).split('.')[0].strip(), nominal, pay_dt, periode_str))

        # 5. PROSES ARDEBT (TUNGGAKAN BEREKOR)
        elif file_type == 'ardebt':
            db.execute("DELETE FROM ardebt") # Refresh data ardebt terbaru
            for _, row in df.iterrows():
                nomen = str(row.get('NOMEN', '')).split('.')[0].strip()
                if not nomen or nomen in ('NAN', ''): continue
                
                jumlah = float(str(row.get('JUMLAH', 0)).replace(',', '')) if row.get('JUMLAH') != '' else 0.0
                volume = float(str(row.get('VOLUME', 0)).replace(',', '')) if row.get('VOLUME') != '' else 0.0
                
                db.execute("""
                    INSERT INTO ardebt (nomen, jumlah, volume, periode_bill) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, jumlah, volume, str(row.get('PERIODE_BILL', '')).strip()))

        # Catat Riwayat ke Database
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status)
            VALUES (?, ?, ?, ?, ?)
        """, (file.filename, file_type.upper(), periode_str, row_count, 'SUCCESS'))

        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Data {file_type.upper()} berhasil disinkronisasi",
            "type": file_type,
            "rows": row_count
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": f"Gagal memproses file: {str(e)}"}), 500
    finally:
        if db: db.close()
