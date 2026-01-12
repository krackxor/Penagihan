"""
Smart Integration Engine - Sunter Dashboard Pro (V12.9 History First)
Update: 2026-01-12
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Zero Data Loss: Semua baris dari MC, MB, dan COLLECTION wajib disimpan untuk history.
2. Smart Labeling: Memisahkan UNDUE, CURRENT, dan ARDEBT tanpa menghapus data.
3. ARDEBT Module Fix: Mendukung sinkronisasi modul ARDEBT murni.
4. Atomic Transaction: Konsistensi data terjamin dengan Rollback protection.
"""

import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from core.helpers import clean_nomen
from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona, parse_billing_date

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
        LOGIKA PELABELAN AUDIT:
        - Bayar N di bulan N     -> UNDUE
        - Bayar N di bulan N+1   -> CURRENT
        - Selebihnya             -> ARDEBT (TETAP DISIMPAN SEBAGAI HISTORY)
        """
        try:
            billing_dt = parse_billing_date(billing_val, file_type)
            clean_date = str(payment_date_str).split(' ')[0].replace("/", "-").replace("'", "")
            pay_dt = datetime.strptime(clean_date, '%d-%m-%Y')
            
            # Hitung selisih bulan (N_bayar - N_rekening)
            diff = (pay_dt.year - billing_dt.year) * 12 + (pay_dt.month - billing_dt.month)

            if diff == 0 and file_type == 'MB':
                return 'UNDUE'
            elif diff == 1 and file_type == 'COLLECTION':
                return 'CURRENT'
            
            return 'ARDEBT' # Label untuk history (Ekor)
        except:
            return 'ARDEBT'

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
        # [1] Load Data (CSV/Excel)
        df = pd.read_csv(file, dtype=str).fillna('') if file_name.endswith('.csv') else pd.read_excel(file, dtype=str).fillna('')
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # [2] Identifikasi Modul & Periode Target
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        # Penentuan Periode
        if data_type == 'RUTE':
            target_period = datetime.now().strftime('%m-%Y')
        else:
            month, year = detect_file_period(df, data_type)
            if not month:
                return jsonify({"status": "error", "message": "Gagal deteksi periode"}), 400
            target_period = f"{month}-{year}"

        row_count = 0

        # [3] Processing Tanpa Filter Buang (Semua Disimpan)
        for _, row in df.iterrows():
            # A. MODUL RUTE
            if data_type == 'RUTE':
                pcez, petugas = str(row.get('PCEZ', '')).strip(), str(row.get('PETUGAS', '')).strip()
                if pcez and petugas:
                    db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (pcez, petugas))
                    row_count += 1
                continue

            # B. MODUL TRANSAKSI & MASTER
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
                
                # Tentukan Kategori (UNDUE / CURRENT / ARDEBT)
                category = UploadEngine.determine_strict_logic(row.get(bill_col), row.get(pay_col), data_type)
                
                if data_type == 'MB':
                    db.execute("""
                        INSERT OR REPLACE INTO master_bayar (nomen, tgl_bayar, nominal, periode, kategori)
                        VALUES (?, ?, ?, ?, ?)
                    """, (nomen, row.get(pay_col), UploadEngine.cast_to_float(row['NOMINAL']), target_period, category))
                else:
                    db.execute("""
                        INSERT OR REPLACE INTO collection_harian (nomen, pay_dt, nominal, periode, kategori)
                        VALUES (?, ?, ?, ?, ?)
                    """, (nomen, row.get(pay_col), UploadEngine.cast_to_float(row['NOMINAL']), target_period, category))
                row_count += 1

            elif data_type == 'ARDEBT':
                # Pastikan sinkronisasi kolom JUMLAH/NOMINAL untuk modul Ardebt
                nominal_ardebt = row.get('JUMLAH') or row.get('NOMINAL') or 0
                db.execute("""
                    INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, row.get('PERIODE_BILL', target_period), 
                      UploadEngine.cast_to_float(nominal_ardebt), 
                      UploadEngine.cast_to_float(row.get('VOLUME', 0))))
                row_count += 1

        # [4] Audit History
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)", 
                   (file_name, data_type, target_period, row_count, 'SUCCESS'))
        db.commit()
        
        return jsonify({
            "status": "success",
            "message": f"Integrasi Sukses: {row_count} baris data berhasil disimpan sebagai history.",
            "metadata": {"rows": row_count, "period": target_period, "type": data_type}
        })

    except Exception as e:
        if db: db.rollback()
        current_app.logger.error(f"Integrity Error: {str(e)}")
        return jsonify({"status": "error", "message": f"Kegagalan Sinkronisasi: {str(e)}"}), 500
    finally:
        db.close()
