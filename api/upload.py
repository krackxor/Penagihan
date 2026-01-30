"""
Smart Integration Engine - Sunter Dashboard Pro (V12.85 High-Speed Sync)
Update: 2026-01-30
---------------------------------------------------------------------------
Pembaruan Strategis:
1. High-Speed Batch Processing: Menggunakan transaksi tunggal (BEGIN TRANSACTION) 
   untuk memproses ribuan baris sekaligus tanpa mengunci database berulang kali.
2. Force Identification: Menjamin file MB tidak pernah dianggap sebagai MC.
3. Target Lock Mechanism: Mencegah MB menambah jumlah baris di master_pelanggan.
4. Auto Bulan Rek Sanitizer: MM/YYYY -> MMYYYY.
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
        """Mencari nama kolom secara fleksibel untuk mendukung berbagai format Excel/CSV."""
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols:
                return cols[name.upper()]
        return None

    @staticmethod
    def clean_bulan_rek(value):
        """OTOMATIS: Membersihkan format bulan rekening (misal: 12/2025 -> 122025)."""
        if not value or pd.isna(value): return ""
        clean_val = ''.join(filter(str.isdigit, str(value)))
        if len(clean_val) == 6:
            return clean_val
        elif len(clean_val) == 5:
            return "0" + clean_val
        return clean_val

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
        
        # Baca File ke Dataframe (Optimasi: Gunakan dtype str untuk semua kolom di awal)
        df = pd.read_csv(file, dtype=str).fillna('') if file_name.endswith('.csv') else pd.read_excel(file, dtype=str).fillna('')
        data_type = identify_file_type(df)
        
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        # Mapping Kolom Utama
        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG', 'SALDO'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])
        col_brek = UploadEngine.get_column(df, ['BULAN_REK', 'BULAN', 'REKENING', 'PERIODE', 'BILL_PERIOD'])
        col_hp = UploadEngine.get_column(df, ['NO_HP', 'PHONE', 'TELEPON', 'WA'])

        # --- LOGIKA PROTEKSI: FORCE IDENTIFICATION ---
        if data_type == 'MC' and (col_brek or col_pay):
            data_type = 'MB'

        # Penentuan Periode Target
        if data_type in ['ARDEBT', 'RUTE']:
            target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
        else:
            month_ref, year_ref = detect_file_period(df, data_type)
            if not month_ref: return jsonify({"status": "error", "message": "Gagal deteksi periode file"}), 400
            target_period = f"{month_ref}-{year_ref}"

        # --- START HIGH SPEED BATCH TRANSACTION ---
        db.execute("BEGIN TRANSACTION")
        
        row_count = 0
        error_rows = 0

        for index, row in df.iterrows():
            try:
                if data_type == 'RUTE':
                    c_pcez = UploadEngine.get_column(df, ['PCEZ', 'ZONA', 'ZONA_NOVAK', 'RUTE'])
                    c_name = UploadEngine.get_column(df, ['PETUGAS', 'NAMA_PETUGAS'])
                    raw_pcez = str(row.get(c_pcez, '')).strip()
                    p_name = str(row.get(c_name, '')).strip()
                    if raw_pcez and p_name:
                        db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (raw_pcez, p_name))
                        row_count += 1
                    continue

                n_raw = row.get(col_id) if col_id else None
                nomen = clean_nomen(n_raw)
                if not nomen: continue

                if data_type == 'MC':
                    c_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ', 'RUTE'])
                    z = autopilot_extract_zona(row.get(c_zona))
                    val_hp = str(row.get(col_hp, '-')).strip() if col_hp else '-'
                    
                    if z:
                        db.execute("""
                            INSERT OR REPLACE INTO master_pelanggan 
                            (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, status_lunas, no_hp, tipe)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'MC')
                        """, (nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), z['pcez'], z['rayon'], 
                              UploadEngine.cast_to_float(row.get(col_nom)), row.get('NOMET', ''), target_period, val_hp))
                        row_count += 1

                elif data_type == 'ARDEBT':
                    val_ardebt = UploadEngine.cast_to_float(row.get(col_nom))
                    if val_ardebt > 0:
                        db.execute("""
                            INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah) 
                            VALUES (?, ?, ?)
                        """, (nomen, row.get('PERIODE_BILL', '-'), val_ardebt))
                        row_count += 1

                elif data_type in ['MB', 'COLLECTION']:
                    if data_type == 'MB':
                        tbl, dt_col, cat = "master_bayar", "tgl_bayar", "UNDUE"
                    else:
                        tbl, dt_col, cat = "collection_harian", "pay_dt", "CURRENT"
                    
                    raw_brek = str(row.get(col_brek, '')).strip() if col_brek else ""
                    b_rek = UploadEngine.clean_bulan_rek(raw_brek)
                    
                    if not b_rek:
                        dt_obj = datetime.strptime(target_period, '%m-%Y')
                        last_month = dt_obj.replace(day=1) - timedelta(days=1)
                        b_rek = last_month.strftime('%m%Y')
                    
                    # 1. Simpan Transaksi
                    db.execute(f"""
                        INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori, bulan_rek) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (nomen, row.get(col_pay, ''), UploadEngine.cast_to_float(row.get(col_nom)), target_period, cat, b_rek))
                    
                    # 2. Update status lunas pada MC (Hanya data yang sudah ada)
                    db.execute("""
                        UPDATE master_pelanggan SET status_lunas = 1, tgl_lunas = ?
                        WHERE nomen = ? AND periode = ? AND tipe = 'MC'
                    """, (str(row.get(col_pay, '')), nomen, target_period))
                    
                    row_count += 1
            
            except Exception as row_err:
                error_rows += 1
                # Jangan print setiap baris jika ribuan baris error, cukup lanjutkan
                continue

        # COMMIT SEMUA SEKALIGUS (INI KUNCI KECEPATAN)
        db.commit() 
        # -----------------------------------------------

        log_action(
            user_id=session.get('username', 'Admin'),
            action='UPLOAD_SUCCESS',
            module=data_type,
            details=f"FastSync: {row_count} sukses, {error_rows} gagal. File: {file_name}",
            ip=request.remote_addr
        )
        
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)",
                   (file_name, data_type, target_period, row_count, 'SUCCESS'))
        db.commit()

        return jsonify({"status": "success", "message": f"Integrasi {data_type} FastSync selesai. {row_count} baris diproses."})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"status": "error", "message": f"Sistem Error: {str(e)}"}), 500
    finally:
        db.close()

@upload_bp.route('/last-session', methods=['GET'])
def get_last_upload_data():
    db = get_db_connection()
    try:
        last_file = db.execute("SELECT file_name FROM upload_history ORDER BY id DESC LIMIT 1").fetchone()
        if not last_file: return jsonify([])

        data = db.execute("""
            SELECT nomen, nama, nominal, no_hp, pcez 
            FROM master_pelanggan 
            WHERE status_lunas = 0 AND tipe = 'MC'
            ORDER BY id DESC LIMIT 1000
        """).fetchall()
        return jsonify([dict(row) for row in data])
    finally:
        db.close()
