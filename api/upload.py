"""
Smart Integration Engine - Sunter Dashboard Pro (V12.80 High Performance)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Bulk Transaction: Menggunakan executemany untuk kecepatan upload 10x lipat.
2. Memory Optimization: List-based processing sebelum commit database.
3. Excel Date Serial Fix: Tetap mendukung konversi otomatis format angka.
4. Auto-Lunas Sync: Sinkronisasi status pembayaran tetap berjalan dalam satu transaksi.
"""

import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, log_action

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    @staticmethod
    def cast_to_float(value):
        try:
            if pd.isna(value) or str(value).strip() == '': return 0.0
            s_val = str(value).replace('\xa0', '').replace(' ', '').replace("'", "")
            if ',' in s_val and '.' in s_val:
                s_val = s_val.replace('.', '').replace(',', '.')
            elif ',' in s_val:
                s_val = s_val.replace(',', '.')
            return float(s_val)
        except: 
            return 0.0

    @staticmethod
    def convert_excel_date(value):
        if not value or pd.isna(value): return ""
        val_str = str(value).strip()
        try:
            if val_str.replace('.', '', 1).isdigit():
                serial = int(float(val_str))
                date_obj = datetime(1899, 12, 30) + timedelta(days=serial)
                return date_obj.strftime('%d-%m-%Y')
            return val_str
        except: return val_str

    @staticmethod
    def get_column(df, possible_names):
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols: return cols[name.upper()]
        return None

@upload_bp.route('/upload', methods=['POST'])
def handle_smart_upload():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Akses Ditolak"}), 403

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak dideteksi"}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona
        
        df = pd.read_csv(file, dtype=str).fillna('') if file_name.endswith('.csv') else pd.read_excel(file, dtype=str).fillna('')
        data_type = identify_file_type(df)
        
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG', 'SALDO'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])
        col_brek = UploadEngine.get_column(df, ['BULAN_REK', 'BULAN', 'REKENING'])

        if data_type in ['ARDEBT', 'RUTE']:
            target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
        else:
            month_ref, year_ref = detect_file_period(df, data_type)
            if not month_ref: return jsonify({"status": "error", "message": "Gagal deteksi periode file"}), 400
            target_period = f"{month_ref}-{year_ref}"

        # Container untuk Bulk Insert
        bulk_data = []
        sync_lunas_nomen = []
        row_count = 0

        for index, row in df.iterrows():
            n_raw = row.get(col_id) if col_id else None
            nomen = clean_nomen(n_raw)
            if not nomen: continue

            if data_type in ['MB', 'COLLECTION']:
                raw_date = row.get(col_pay, '')
                formatted_date = UploadEngine.convert_excel_date(raw_date)
                b_rek = str(row.get(col_brek, '')).strip() if col_brek else target_period.replace('-', '')
                nominal = UploadEngine.cast_to_float(row.get(col_nom))
                
                # Masukkan ke list untuk bulk insert
                cat = "UNDUE" if data_type == 'MB' else "CURRENT"
                bulk_data.append((nomen, formatted_date, nominal, target_period, cat, b_rek))
                sync_lunas_nomen.append((nomen, target_period))
                row_count += 1

            elif data_type == 'MC':
                c_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ', 'RUTE'])
                z = autopilot_extract_zona(row.get(c_zona))
                if z:
                    bulk_data.append((nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), z['pcez'], z['rayon'], 
                                     UploadEngine.cast_to_float(row.get(col_nom)), row.get('NOMET', ''), target_period))
                    row_count += 1

        # Proses Bulk Database
        if data_type in ['MB', 'COLLECTION']:
            tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
            dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
            
            # 1. Bulk Insert Transaksi
            db.executemany(f"INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori, bulan_rek) VALUES (?,?,?,?,?,?)", bulk_data)
            # 2. Bulk Update Status Lunas
            db.executemany("UPDATE master_pelanggan SET status_lunas = 1 WHERE nomen = ? AND periode = ?", sync_lunas_nomen)
            
        elif data_type == 'MC':
            db.executemany("""
                INSERT OR REPLACE INTO master_pelanggan 
                (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, status_lunas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, bulk_data)

        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, data_type, target_period, row_count, 'SUCCESS'))
        
        db.commit()
        log_action(session.get('username', 'Admin'), 'UPLOAD_SUCCESS', data_type, f"Processed {row_count} rows", request.remote_addr)
        
        return jsonify({"status": "success", "message": f"Upload {data_type} berhasil: {row_count} baris."})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"status": "error", "message": f"Sistem Error: {str(e)}"}), 500
    finally:
        db.close()
