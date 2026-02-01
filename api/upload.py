"""
Smart Integration Engine - Sunter Dashboard Pro (V13.05 History Patch)
Update: 2026-02-01
---------------------------------------------------------------------------
Teknologi Unggulan:
1. ✅ MULTI-UPLOAD: Mendukung request.files.getlist() untuk proses banyak file.
2. ✅ BACKDATE SUPPORT: Prioritas periode kustom dari input form untuk history data.
3. Anti-Timeout: Pemanfaatan executemany() dan penonaktifan PRAGMA synchronous sementara.
4. Memory Buffering: Validasi dan pembersihan data dilakukan di RAM sebelum injeksi.
5. Trigger Sync: Mengandalkan Trigger Database V12.97 untuk sinkronisasi lunas otomatis.
"""

import pandas as pd
import os
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
        except: 
            return 0.0

    @staticmethod
    def get_column(df, possible_names):
        """Mencari nama kolom secara fleksibel."""
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols:
                return cols[name.upper()]
        return None

    @staticmethod
    def clean_bulan_rek(value):
        """Membersihkan format bulan rekening menjadi MMYYYY."""
        if not value or pd.isna(value): return ""
        clean_val = ''.join(filter(str.isdigit, str(value)))
        if len(clean_val) == 6:
            return clean_val
        elif len(clean_val) == 5:
            return "0" + clean_val
        return clean_val

@upload_bp.route('/upload', methods=['POST'])
def handle_smart_upload():
    """Engine Upload Massal dengan Dukungan History Periode."""
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Akses Ditolak"}), 403

    # 1. AMBIL LIST FILE & PERIODE KUSTOM
    # Mendukung input 'files' (jamak) dan 'periode_input' (format YYYY-MM dari HTML5)
    files = request.files.getlist('file') # Menggunakan 'file' agar tetap kompatibel dengan dropzone/form lama
    custom_period = request.form.get('periode_input') 
    
    if not files:
        return jsonify({"status": "error", "message": "File tidak dideteksi"}), 400
    
    db = get_db_connection()
    total_processed = 0
    results = []

    try:
        from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona
        
        # Optimasi Kecepatan Database (Injeksi Tanpa Jeda)
        db.execute("PRAGMA synchronous = OFF")
        db.execute("PRAGMA journal_mode = WAL")

        for file in files:
            file_name = file.filename
            if file_name == '': continue

            # Membaca Data ke Dataframe
            if file_name.lower().endswith('.csv'):
                df = pd.read_csv(file, dtype=str, engine='c', low_memory=False).fillna('')
            else:
                df = pd.read_excel(file, dtype=str).fillna('')
            
            data_type = identify_file_type(df)
            if not data_type: continue

            # Penentuan Periode Target (Prioritas: Form Input -> Auto Detect)
            if custom_period:
                # Konversi YYYY-MM ke MM-YYYY
                p_parts = custom_period.split('-')
                target_period = f"{p_parts[1]}-{p_parts[0]}" if len(p_parts) == 2 else custom_period
            elif data_type in ['ARDEBT', 'RUTE']:
                target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
            else:
                month_ref, year_ref = detect_file_period(df, data_type)
                target_period = f"{month_ref}-{year_ref}" if month_ref else datetime.now().strftime('%m-%Y')

            # --- BUFFERING DATA KE RAM ---
            bulk_main = []
            bulk_rute = []
            
            col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN'])
            col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'PIUTANG'])
            col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS'])
            col_brek = UploadEngine.get_column(df, ['BULAN_REK', 'BULAN', 'PERIODE'])
            col_hp = UploadEngine.get_column(df, ['NO_HP', 'PHONE', 'WA'])

            records = df.to_dict('records')
            for row in records:
                if data_type == 'RUTE':
                    c_pcez = UploadEngine.get_column(df, ['PCEZ', 'RUTE', 'ZONA'])
                    c_name = UploadEngine.get_column(df, ['PETUGAS', 'NAMA_PETUGAS'])
                    z_rute = autopilot_extract_zona(str(row.get(c_pcez, '')).strip())
                    if z_rute and row.get(c_name):
                        bulk_rute.append((z_rute['pcez'], str(row.get(c_name)).strip().upper()))
                    continue

                nomen = clean_nomen(row.get(col_id))
                if not nomen: continue
                nominal = UploadEngine.cast_to_float(row.get(col_nom))

                if data_type == 'MC':
                    c_zona = UploadEngine.get_column(df, ['PCEZ', 'RUTE', 'ZONA'])
                    z = autopilot_extract_zona(row.get(c_zona))
                    if z:
                        bulk_main.append((nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), 
                                         z['pcez'], z['rayon'], nominal, row.get('NOMET', ''), 
                                         target_period, row.get(col_hp, '-'), 'MC', 0))
                
                elif data_type in ['MB', 'COLLECTION']:
                    b_rek = UploadEngine.clean_bulan_rek(str(row.get(col_brek, '')))
                    cat = "UNDUE" if data_type == 'MB' else "CURRENT"
                    bulk_main.append((nomen, str(row.get(col_pay, '')), nominal, target_period, cat, b_rek))

                elif data_type == 'ARDEBT':
                    if nominal > 0:
                        bulk_main.append((nomen, row.get('PERIODE_BILL', '-'), nominal, target_period))

            # --- EKSEKUSI DATABASE PER FILE ---
            if data_type == 'RUTE':
                db.executemany("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", bulk_rute)
            elif data_type == 'MC':
                db.executemany("INSERT OR REPLACE INTO master_pelanggan (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, no_hp, tipe, status_lunas) VALUES (?,?,?,?,?,?,?,?,?,?,?)", bulk_main)
            elif data_type in ['MB', 'COLLECTION']:
                tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
                dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                db.executemany(f"INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori, bulan_rek) VALUES (?,?,?,?,?,?)", bulk_main)
            elif data_type == 'ARDEBT':
                db.executemany("INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, periode) VALUES (?,?,?,?)", bulk_main)

            total_processed += len(bulk_main) if data_type != 'RUTE' else len(bulk_rute)
            db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?,?,?,?,?)",
                       (file_name, data_type, target_period, len(bulk_main), 'SUCCESS'))
            results.append(f"{file_name} ({data_type})")

        db.commit()
        db.execute("PRAGMA synchronous = NORMAL")
        log_action(session.get('username', 'Admin'), 'MULTI_UPLOAD_SUCCESS', 'CORE', f"Processed {len(files)} files, {total_processed} rows.")
        
        return jsonify({
            "status": "success", 
            "message": f"Integrasi Berhasil! {len(files)} file diproses ({total_processed} baris).",
            "details": results
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"status": "error", "message": f"Koneksi terhenti atau data korup: {str(e)}"}), 500
    finally:
        db.close()

@upload_bp.route('/last-session', methods=['GET'])
def get_last_upload_data():
    db = get_db_connection()
    try:
        data = db.execute("""
            SELECT nomen, nama, nominal, no_hp, pcez 
            FROM master_pelanggan 
            WHERE status_lunas = 0 AND tipe = 'MC'
            ORDER BY id DESC LIMIT 1000
        """).fetchall()
        return jsonify([dict(row) for row in data])
    finally:
        db.close()
