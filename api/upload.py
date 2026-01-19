"""
Smart Integration Engine - Sunter Dashboard Pro (V12.66 Optimized Sync)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Column Integrity Fix: Menyelaraskan jumlah kolom INSERT dengan database V12.63.
2. Robust Mapping: Memastikan kolom 'JUMLAH' dan 'PIUTANG' terdeteksi otomatis.
3. Silent Error Guard: Menjamin upload tetap berjalan meski ada baris Excel yang cacat.
4. Audit Trail: Pencatatan otomatis ke system_logs untuk setiap file yang masuk.
"""

import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask import Blueprint, request, jsonify, session, current_app
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
        except: return 0.0

    @staticmethod
    def get_column(df, possible_names):
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols:
                return cols[name.upper()]
        return None

    @staticmethod
    def determine_strict_logic(billing_val, payment_date_str, file_type, target_period):
        try:
            from processors.auto_detect import parse_billing_date, parse_flexible_date
            billing_dt = parse_billing_date(billing_val, file_type)
            pay_dt = parse_flexible_date(payment_date_str)
            if not billing_dt or not pay_dt: return 'HISTORY'
            diff = (pay_dt.year - billing_dt.year) * 12 + (pay_dt.month - billing_dt.month)
            if file_type == 'MB' and diff == 0: return 'UNDUE'
            if file_type == 'COLLECTION' and diff == 1: return 'CURRENT'
            return 'HISTORY'
        except: return 'HISTORY'

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
        from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona, parse_flexible_date
        
        df = pd.read_csv(file, dtype=str).fillna('') if file_name.endswith('.csv') else pd.read_excel(file, dtype=str).fillna('')
        data_type = identify_file_type(df)
        
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG', 'SALDO'])
        col_bill = UploadEngine.get_column(df, ['BULAN_REK', 'BILL_PERIOD', 'PERIODE_REK'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])

        if data_type == 'ARDEBT':
            target_period, month_ref = "GLOBAL-HISTORY", None
        elif data_type == 'RUTE':
            target_period, month_ref = datetime.now().strftime('%m-%Y'), None
        else:
            month_ref, year_ref = detect_file_period(df, data_type)
            if not month_ref: return jsonify({"status": "error", "message": "Gagal deteksi periode file"}), 400
            target_period = f"{month_ref}-{year_ref}"

        row_count = 0
        error_rows = 0

        for index, row in df.iterrows():
            try:
                # A. MODUL RUTE (FIXED)
                if data_type == 'RUTE':
                    c_pcez = UploadEngine.get_column(df, ['PCEZ', 'ZONA', 'ZONA_NOVAK', 'RUTE'])
                    c_name = UploadEngine.get_column(df, ['PETUGAS', 'NAMA_PETUGAS'])
                    raw_pcez = str(row.get(c_pcez, '')).strip()
                    p_name = str(row.get(c_name, '')).strip()
                    if raw_pcez and p_name:
                        clean_pcez = raw_pcez.replace('/', '').replace('.', '').replace('-', '')
                        db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (clean_pcez, p_name))
                        row_count += 1
                    continue

                n_raw = row.get(col_id) if col_id else None
                nomen = clean_nomen(n_raw)
                if not nomen: continue

                # B. MODUL MC (FIXED COLUMN MAPPING)
                if data_type == 'MC':
                    c_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ', 'RUTE'])
                    z = autopilot_extract_zona(row.get(c_zona))
                    if z:
                        # Perbaikan: Kolom harus pas (9 kolom di tabel = 9 parameter di VALUES)
                        db.execute("""
                            INSERT OR REPLACE INTO master_pelanggan 
                            (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, status_lunas)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """, (nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), z['pcez'], z['rayon'], 
                              UploadEngine.cast_to_float(row.get(col_nom)), row.get('NOMET', ''), target_period))
                        row_count += 1

                # C. MODUL ARDEBT
                elif data_type == 'ARDEBT':
                    val_ardebt = UploadEngine.cast_to_float(row.get(col_nom))
                    if val_ardebt > 0:
                        db.execute("""
                            INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume, periode) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (nomen, row.get('PERIODE_BILL', '-'), val_ardebt, 
                              UploadEngine.cast_to_float(row.get('VOLUME', 0)), target_period))
                        row_count += 1

                # D. MODUL MB & COLLECTION
                elif data_type in ['MB', 'COLLECTION']:
                    tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
                    dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                    db.execute(f"INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode) VALUES (?, ?, ?, ?)", 
                               (nomen, row.get(col_pay, ''), UploadEngine.cast_to_float(row.get(col_nom)), target_period))
                    row_count += 1
            
            except Exception as e:
                error_rows += 1
                # Log error baris ke terminal tanpa menghentikan upload
                print(f"⚠️ Row {index} Sync Error: {str(e)}")

        # FINALISASI & LOGGING
        log_action(session.get('username', 'Admin'), 'UPLOAD_SUCCESS', data_type, f"File: {file_name} | Success: {row_count} | Fail: {error_rows}", request.remote_addr)
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)", (file_name, data_type, target_period, row_count, 'SUCCESS'))
        db.commit()
        
        return jsonify({"status": "success", "message": f"Sinkronisasi selesai. {row_count} sukses, {error_rows} gagal."})

    except Exception as e:
        if db: db.rollback()
        print(f"❌ Fatal Upload Error: {str(e)}")
        return jsonify({"status": "error", "message": f"Fatal System Error: {str(e)}"}), 500
    finally:
        db.close()
