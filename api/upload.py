"""
Smart Integration Engine - Sunter Dashboard Pro (V12.27 Autopilot)
Update: 2026-01-19
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Column Autopilot: Mendeteksi nama kolom secara fleksibel (IDPEL/NOMEN, dll).
2. Zero-Edit Parsing: Membersihkan spasi liar, \xa0, dan karakter kutip secara otomatis.
3. Excel Serial Fixer: Konversi otomatis angka serial (46037) menjadi tanggal asli.
4. N+1 Global Alignment: Memastikan target_period terkunci konsisten (N+1 Support).
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
    clean_val  # Memastikan menggunakan cleaner dari auto_detect
)

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    @staticmethod
    def cast_to_float(value):
        """Mengonversi string/excel value ke float dengan pembersihan otomatis."""
        try:
            if pd.isna(value) or str(value).strip() == '': return 0.0
            # Menangani format ribuan Indonesia (titik) dan desimal (koma)
            s_val = str(value).replace('\xa0', '').replace(' ', '').replace("'", "")
            if ',' in s_val and '.' in s_val:
                s_val = s_val.replace('.', '').replace(',', '.')
            elif ',' in s_val:
                s_val = s_val.replace(',', '.')
            return float(s_val)
        except: return 0.0

    @staticmethod
    def get_column(df, possible_names):
        """AUTOPILOT: Mencari kolom yang ada tanpa peduli case-sensitive atau variasi nama."""
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols:
                return cols[name.upper()]
        return None

    @staticmethod
    def determine_strict_logic(billing_val, payment_date_str, file_type):
        """LOGIKA AUDIT OTOMATIS: N vs N+1 Matching."""
        try:
            billing_dt = parse_billing_date(billing_val, file_type)
            pay_dt = parse_flexible_date(payment_date_str)
            
            if not billing_dt or not pay_dt: return 'HISTORY'

            # Hitung selisih bulan (Audit Matching)
            diff = (pay_dt.year - billing_dt.year) * 12 + (pay_dt.month - billing_dt.month)

            if diff == 0 and file_type == 'MB':
                return 'UNDUE'
            elif diff == 1 and file_type == 'COLLECTION':
                return 'CURRENT'
            
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
        # [1] Load Data - Support CSV & Excel
        if file_name.endswith('.csv'):
            df = pd.read_csv(file, dtype=str).fillna('')
        else:
            df = pd.read_excel(file, dtype=str).fillna('')

        # [2] Identifikasi Modul & Mapping Kolom Cerdas
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        # Autopilot Mapping: Cari kolom tanpa perlu edit manual di Excel
        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'SUBNOMINAL'])
        col_bill = UploadEngine.get_column(df, ['BULAN_REK', 'BILL_PERIOD', 'PERIODE_REK'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])

        # [3] Penentuan Periode (LOGIKA N+1 ALIGNMENT)
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
            # A. MODUL RUTE
            if data_type == 'RUTE':
                pcez = str(row.get('PCEZ', row.get('ZONA', ''))).strip()
                petugas = str(row.get('PETUGAS', '')).strip()
                if pcez and petugas:
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (pcez, petugas))
                    row_count += 1
                continue

            # B. MODUL MC, MB, COLLECTION
            nomen_raw = row.get(col_id) if col_id else None
            nomen = clean_nomen(nomen_raw)
            if not nomen: continue

            if data_type == 'MC':
                col_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ'])
                zona = autopilot_extract_zona(row.get(col_zona))
                if zona:
                    db.execute("""
                        INSERT OR REPLACE INTO master_pelanggan 
                        (nomen, nama, alamat, pcez, rayon, pc, ez, blok, nominal, nomet, periode, status_lunas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (nomen, row.get('NAMA_PEL'), row.get('ALM1_PEL'), zona['pcez'], zona['rayon'], 
                          zona['pc'], zona['ez'], zona['blok'], UploadEngine.cast_to_float(row.get(col_nom)), 
                          row.get('NOMET'), target_period))
                    row_count += 1

            elif data_type in ['MB', 'COLLECTION']:
                # Penentuan Kategori Audit (UNDUE vs CURRENT vs HISTORY)
                bill_val = row.get(col_bill) if col_bill else ""
                pay_val = row.get(col_pay) if col_pay else ""
                
                category = UploadEngine.determine_strict_logic(bill_val, pay_val, data_type)
                
                query_table = "master_bayar" if data_type == 'MB' else "collection_harian"
                date_col_db = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                
                db.execute(f"INSERT OR REPLACE INTO {query_table} (nomen, {date_col_db}, nominal, periode, kategori) VALUES (?, ?, ?, ?, ?)", 
                           (nomen, pay_val, UploadEngine.cast_to_float(row.get(col_nom)), target_period, category))
                row_count += 1

            elif data_type == 'ARDEBT':
                p_bill = str(row.get('PERIODE_BILL', row.get('PERIODE', '-'))).strip()
                db.execute("INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume) VALUES (?, ?, ?, ?)", 
                           (nomen, p_bill, UploadEngine.cast_to_float(row.get(col_nom)), 
                            UploadEngine.cast_to_float(row.get('VOLUME', 0))))
                row_count += 1

        # [5] Finalize
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)", 
                   (file_name, data_type, target_period, row_count, 'SUCCESS'))
        db.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Autopilot: {row_count} baris diproses untuk Dashboard {target_period}.",
            "metadata": {"rows": row_count, "period": target_period}
        })

    except Exception as e:
        if db: db.rollback()
        current_app.logger.error(f"Upload Failure: {str(e)}")
        return jsonify({"status": "error", "message": f"Kegagalan Sinkronisasi: {str(e)}"}), 500
    finally:
        db.close()
