"""
Smart Integration Engine - Sunter Dashboard Pro (V12.32 Autopilot)
Update: 2026-01-19
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ARDEBT Robust Mapping: Mendukung kolom 'JUMLAH', 'PIUTANG', dan 'SALDO'.
2. Zero-Row Fix: Validasi kolom nominal lebih luas untuk mencegah '0 baris mendarat'.
3. Shift Logic (N+1): Mengunci realisasi bulan N ke Dashboard periode N+1.
4. Precision Recovery: Memastikan kategori ARDEBT masuk ke GLOBAL-HISTORY secara tepat.
"""

import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from core.helpers import clean_nomen
from processors.auto_detect import (
    identify_file_type, 
    detect_file_period, 
    autopilot_extract_zona, 
    parse_billing_date,
    parse_flexible_date,
    clean_val 
)

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    @staticmethod
    def cast_to_float(value):
        """Konversi angka cerdas: Menangani format ribuan (.) dan desimal (,) Indonesia."""
        try:
            if pd.isna(value) or str(value).strip() == '': return 0.0
            s_val = str(value).replace('\xa0', '').replace(' ', '').replace("'", "")
            # Transformasi: 1.283.710,00 -> 1283710.00
            if ',' in s_val and '.' in s_val:
                s_val = s_val.replace('.', '').replace(',', '.')
            elif ',' in s_val:
                s_val = s_val.replace(',', '.')
            return float(s_val)
        except: return 0.0

    @staticmethod
    def get_column(df, possible_names):
        """Mencari nama kolom secara fleksibel tanpa perlu edit manual di Excel."""
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols:
                return cols[name.upper()]
        return None

    @staticmethod
    def determine_strict_logic(billing_val, payment_date_str, file_type, target_period):
        """LOGIKA AUDIT KETAT (SHIFT N+1)"""
        try:
            billing_dt = parse_billing_date(billing_val, file_type)
            pay_dt = parse_flexible_date(payment_date_str)
            if not billing_dt or not pay_dt: return 'HISTORY'

            diff = (pay_dt.year - billing_dt.year) * 12 + (pay_dt.month - billing_dt.month)

            if file_type == 'MB':
                if diff == 0: return 'UNDUE'
            elif file_type == 'COLLECTION':
                if diff == 1: return 'CURRENT'
            
            return 'HISTORY'
        except:
            return 'HISTORY'

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
        # [1] Load Data
        if file_name.endswith('.csv'):
            df = pd.read_csv(file, dtype=str).fillna('')
        else:
            df = pd.read_excel(file, dtype=str).fillna('')

        # [2] Identifikasi Tipe & Mapping Kolom Cerdas
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        # Tambahkan 'JUMLAH' dan 'PIUTANG' untuk mendukung file ARDEBT
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG', 'SALDO'])
        col_bill = UploadEngine.get_column(df, ['BULAN_REK', 'BILL_PERIOD', 'PERIODE_REK'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])

        # [3] Penentuan Periode Dashboard
        if data_type == 'ARDEBT':
            target_period = "GLOBAL-HISTORY"
        elif data_type == 'RUTE':
            target_period = datetime.now().strftime('%m-%Y')
        else:
            month, year = detect_file_period(df, data_type)
            if not month:
                return jsonify({"status": "error", "message": "Gagal deteksi periode file"}), 400
            target_period = f"{month}-{year}"

        row_count = 0

        # [4] Processing Loop
        for _, row in df.iterrows():
            n_raw = row.get(col_id) if col_id else None
            nomen = clean_nomen(n_raw)
            if not nomen: continue

            # A. MODUL RUTE
            if data_type == 'RUTE':
                p_pcez = str(row.get('PCEZ', row.get('ZONA', ''))).strip()
                p_name = str(row.get('PETUGAS', '')).strip()
                if p_pcez and p_name:
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (p_pcez, p_name))
                    row_count += 1
                continue

            # B. MODUL MC
            if data_type == 'MC':
                c_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ'])
                z = autopilot_extract_zona(row.get(c_zona))
                if z:
                    db.execute("""
                        INSERT OR REPLACE INTO master_pelanggan 
                        (nomen, nama, alamat, pcez, rayon, pc, ez, blok, nominal, nomet, periode, status_lunas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (nomen, row.get('NAMA_PEL'), row.get('ALM1_PEL'), z['pcez'], z['rayon'], 
                          z['pc'], z['ez'], z['blok'], UploadEngine.cast_to_float(row.get(col_nom)), 
                          row.get('NOMET'), target_period))
                    row_count += 1

            # C. MODUL MB & COLLECTION
            elif data_type in ['MB', 'COLLECTION']:
                b_val = row.get(col_bill) if col_bill else ""
                p_val = row.get(col_pay) if col_pay else ""
                cat = UploadEngine.determine_strict_logic(b_val, p_val, data_type, target_period)
                tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
                dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                
                db.execute(f"INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori) VALUES (?, ?, ?, ?, ?)", 
                           (nomen, p_val, UploadEngine.cast_to_float(row.get(col_nom)), target_period, cat))
                row_count += 1

            # D. MODUL ARDEBT (FIX 0 ROWS)
            elif data_type == 'ARDEBT':
                p_bill = str(row.get('PERIODE_BILL', row.get('PERIODE', '-'))).strip()
                val_ardebt = UploadEngine.cast_to_float(row.get(col_nom))
                if val_ardebt > 0:
                    db.execute("INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume) VALUES (?, ?, ?, ?)", 
                               (nomen, p_bill, val_ardebt, UploadEngine.cast_to_float(row.get('VOLUME', 0))))
                    row_count += 1

        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)", 
                   (file_name, data_type, target_period, row_count, 'SUCCESS'))
        db.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Sinkronisasi Sukses: {row_count} baris mendarat di Dashboard {target_period}.",
            "metadata": {"rows": row_count, "period": target_period}
        })

    except Exception as e:
        if db: db.rollback()
        current_app.logger.error(f"Upload Failure: {str(e)}")
        return jsonify({"status": "error", "message": f"Gagal: {str(e)}"}), 500
    finally:
        db.close()
