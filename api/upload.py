"""
Smart Integration Engine - Sunter Dashboard Pro (V12.21)
Update: 2026-01-13
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Forced Period: Mengunci target_period agar konsisten di seluruh loop upload.
2. Audit Filter: Memastikan kategori UNDUE hanya untuk nominal pelunasan murni.
3. Fix Row Processing: Menjamin variabel periode tidak tertukar dengan data excel.
4. Transaction Integrity: Commit hanya dilakukan jika seluruh baris berhasil diproses.
"""

import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from core.helpers import clean_nomen
from processors.auto_detect import (
    identify_file_type, 
    detect_file_period, 
    autopilot_extract_zona, 
    parse_billing_date,
    parse_flexible_date
)

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    @staticmethod
    def cast_to_float(value):
        try:
            if pd.isna(value) or str(value).strip() == '': return 0.0
            return float(str(value).replace(',', '.'))
        except: return 0.0

    @staticmethod
    def determine_strict_logic(billing_val, payment_date_str, file_type):
        """
        LOGIKA AUDIT:
        - UNDUE: Bulan Bayar == Bulan Rekening (N) -> Khusus MB
        - CURRENT: Bulan Bayar == Bulan Rekening + 1 -> Khusus COLLECTION
        """
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
        # [1] Load Data
        if file_name.endswith('.csv'):
            df = pd.read_csv(file, dtype=str).fillna('')
        else:
            df = pd.read_excel(file, dtype=str).fillna('')

        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # [2] Identifikasi Modul
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        # [3] Penentuan Periode (LOGIKA N+1)
        # Menghitung target_period satu kali di awal untuk seluruh isi file
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

            # B. MODUL MC, MB, COLLECTION (Audit Entry)
            nomen = clean_nomen(row.get('NOMEN') or row.get('IDPEL'))
            if not nomen: continue

            if data_type == 'MC':
                zona = autopilot_extract_zona(row['ZONA_NOVAK'])
                if zona:
                    db.execute("""
                        INSERT OR REPLACE INTO master_pelanggan 
                        (nomen, nama, alamat, pcez, rayon, pc, ez, blok, nominal, nomet, periode, status_lunas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (nomen, row.get('NAMA_PEL'), row.get('ALM1_PEL'), zona['pcez'], zona['rayon'], 
                          zona['pc'], zona['ez'], zona['blok'], UploadEngine.cast_to_float(row['NOMINAL']), 
                          row.get('NOMET'), target_period))
                    row_count += 1

            elif data_type in ['MB', 'COLLECTION']:
                bill_col = 'BULAN_REK' if data_type == 'MB' else 'BILL_PERIOD'
                pay_col = 'TGL_BAYAR' if data_type == 'MB' else 'PAY_DT'
                
                # Filter Kategori Audit (UNDUE vs HISTORY)
                category = UploadEngine.determine_strict_logic(row.get(bill_col), row.get(pay_col), data_type)
                
                query_table = "master_bayar" if data_type == 'MB' else "collection_harian"
                date_col_db = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                
                # KUNCI: Gunakan 'target_period' yang sudah dikunci di atas
                db.execute(f"INSERT OR REPLACE INTO {query_table} (nomen, {date_col_db}, nominal, periode, kategori) VALUES (?, ?, ?, ?, ?)", 
                           (nomen, row.get(pay_col), UploadEngine.cast_to_float(row['NOMINAL']), target_period, category))
                row_count += 1

            elif data_type == 'ARDEBT':
                p_bill = str(row.get('PERIODE_BILL', row.get('PERIODE', '-'))).strip()
                db.execute("INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume) VALUES (?, ?, ?, ?)", 
                           (nomen, p_bill, UploadEngine.cast_to_float(row.get('JUMLAH', row.get('NOMINAL'))), 
                            UploadEngine.cast_to_float(row.get('VOLUME', 0))))
                row_count += 1

        # [5] Finalize Upload History
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)", 
                   (file_name, data_type, target_period, row_count, 'SUCCESS'))
        db.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Sinkronisasi {data_type} Berhasil untuk Periode {target_period}", 
            "metadata": {"rows": row_count, "period": target_period}
        })

    except Exception as e:
        if db: db.rollback()
        current_app.logger.error(f"Upload Failure: {str(e)}")
        return jsonify({"status": "error", "message": f"Kegagalan Sinkronisasi: {str(e)}"}), 500
    finally:
        db.close()
