"""
Smart Integration Engine - Sunter Dashboard Pro (V12.68 Stable)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Column Integrity Fix: Menyelaraskan parameter INSERT dengan skema DB V12.68.
2. Row-Level Shield: Menjamin upload tidak terhenti total jika ada data baris yang cacat.
3. System Log Integration: Mencatat jejak audit upload ke tabel 'system_logs'.
4. Connection Stability: Penanganan eksplisit untuk mencegah 'Database is Locked'.
"""

import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, log_action

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    @staticmethod
    def cast_to_float(value):
        """Konversi angka cerdas: Menangani format ribuan (.) dan desimal (,) Indonesia."""
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
        """Mencari nama kolom secara fleksibel untuk mendukung berbagai format Excel."""
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols:
                return cols[name.upper()]
        return None

@upload_bp.route('/upload', methods=['POST'])
def handle_smart_upload():
    # 1. AUTHENTICATION CHECK
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Akses Ditolak"}), 403

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak dideteksi"}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona
        
        # 2. FILE TYPE & PERIOD DETECTION
        df = pd.read_csv(file, dtype=str).fillna('') if file_name.endswith('.csv') else pd.read_excel(file, dtype=str).fillna('')
        data_type = identify_file_type(df)
        
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        # Mapping Kolom Universal
        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG', 'SALDO'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])

        # Penentuan Periode Target
        if data_type in ['ARDEBT', 'RUTE']:
            target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
        else:
            month_ref, year_ref = detect_file_period(df, data_type)
            if not month_ref: return jsonify({"status": "error", "message": "Gagal deteksi periode file"}), 400
            target_period = f"{month_ref}-{year_ref}"

        row_count = 0
        error_rows = 0

        # 3. PROCESSING LOOP (ROW-LEVEL SHIELD)
        for index, row in df.iterrows():
            try:
                # A. MODUL RUTE (Normalisasi PCEZ)
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

                # B. MODUL MASTER PELANGGAN (MC)
                if data_type == 'MC':
                    c_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ', 'RUTE'])
                    z = autopilot_extract_zona(row.get(c_zona))
                    if z:
                        # Sinkronisasi 9 Parameter sesuai DB V12.68
                        db.execute("""
                            INSERT OR REPLACE INTO master_pelanggan 
                            (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, status_lunas)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """, (nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), z['pcez'], z['rayon'], 
                              UploadEngine.cast_to_float(row.get(col_nom)), row.get('NOMET', ''), target_period))
                        row_count += 1

                # C. MODUL ARDEBT (TUNGGAKAN)
                elif data_type == 'ARDEBT':
                    val_ardebt = UploadEngine.cast_to_float(row.get(col_nom))
                    if val_ardebt > 0:
                        db.execute("""
                            INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, periode) 
                            VALUES (?, ?, ?, ?)
                        """, (nomen, row.get('PERIODE_BILL', '-'), val_ardebt, target_period))
                        row_count += 1

                # D. MODUL MB & COLLECTION (PEMBAYARAN)
                elif data_type in ['MB', 'COLLECTION']:
                    tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
                    dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                    db.execute(f"INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode) VALUES (?, ?, ?, ?)", 
                               (nomen, row.get(col_pay, ''), UploadEngine.cast_to_float(row.get(col_nom)), target_period))
                    row_count += 1
            
            except Exception as row_err:
                error_rows += 1
                # Cetak error baris ke terminal tanpa menghentikan proses upload
                print(f"⚠️ Baris {index} Sync Error: {str(row_err)}")

        # 4. FINALISASI & LOGGING
        log_action(
            user_id=session.get('username', 'Admin'), 
            action='UPLOAD_SUCCESS', 
            data_type=data_type, 
            details=f"File: {file_name} | Success: {row_count} | Fail: {error_rows}", 
            ip=request.remote_addr
        )
        
        # Catat Riwayat Upload
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, data_type, target_period, row_count, 'SUCCESS'))
        
        db.commit()
        return jsonify({"status": "success", "message": f"Integrasi selesai. {row_count} sukses, {error_rows} baris dilewati."})

    except Exception as e:
        if db: db.rollback()
        print(f"❌ FATAL ERROR: {str(e)}")
        return jsonify({"status": "error", "message": f"Sistem Error: {str(e)}"}), 500
    finally:
        db.close()
