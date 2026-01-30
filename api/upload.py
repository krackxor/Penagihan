"""
Smart Integration Engine - Sunter Dashboard Pro (V12.86 Ultimate High-Speed)
Update: 2026-01-30
---------------------------------------------------------------------------
Pembaruan Strategis:
1. High-Speed Batch Processing: Menggunakan transaksi tunggal (BEGIN TRANSACTION) 
   untuk memproses ribuan baris sekaligus tanpa mengunci database berulang kali.
2. Force Identification: Mendeteksi kolom 'BULAN_REK' atau 'TGL_BAYAR' untuk 
   memaksa tipe data menjadi MB/UNDUE (Mencegah target MC bertambah liar).
3. Target Lock Mechanism: Menggunakan query UPDATE untuk status lunas agar 
   Total Nomen & Target Nominal terkunci hanya dari file MC awal.
4. Connection Stability: Mengurangi overhead I/O yang mencegah "Gagal Terhubung".
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
        
        # Baca File ke Dataframe (Optimasi Read)
        if file_name.endswith('.csv'):
            df = pd.read_csv(file, dtype=str).fillna('')
        else:
            df = pd.read_excel(file, dtype=str).fillna('')
            
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        # Mapping Kolom Utama
        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])
        col_brek = UploadEngine.get_column(df, ['BULAN_REK', 'BULAN', 'REKENING', 'PERIODE'])
        col_hp = UploadEngine.get_column(df, ['NO_HP', 'PHONE', 'TELEPON', 'WA'])

        # Proteksi Tipe: Jika file MC punya kolom transaksi, paksa jadi MB
        if data_type == 'MC' and (col_brek or col_pay):
            data_type = 'MB'

        # Penentuan Periode Target
        if data_type in ['ARDEBT', 'RUTE']:
            target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
        else:
            month_ref, year_ref = detect_file_period(df, data_type)
            if not month_ref: return jsonify({"status": "error", "message": "Gagal deteksi periode file"}), 400
            target_period = f"{month_ref}-{year_ref}"

        # --- HIGH SPEED SYNC: ATOMIC TRANSACTION START ---
        db.execute("PRAGMA synchronous = OFF") # Mode turbo sementara
        db.execute("BEGIN TRANSACTION")
        
        row_count = 0
        error_rows = 0

        for index, row in df.iterrows():
            try:
                # Modul Mapping Petugas
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

                # Modul Target (MC)
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

                # Modul Realisasi (MB & COLLECTION)
                elif data_type in ['MB', 'COLLECTION']:
                    tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
                    dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                    cat = "UNDUE" if data_type == 'MB' else "CURRENT"
                    
                    b_rek = UploadEngine.clean_bulan_rek(str(row.get(col_brek, '')))
                    if not b_rek:
                        dt_obj = datetime.strptime(target_period, '%m-%Y')
                        b_rek = (dt_obj.replace(day=1) - timedelta(days=1)).strftime('%m%Y')
                    
                    # 1. Simpan Transaksi
                    db.execute(f"""
                        INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori, bulan_rek) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (nomen, row.get(col_pay, ''), UploadEngine.cast_to_float(row.get(col_nom)), target_period, cat, b_rek))
                    
                    # 2. Update status lunas pada MC (Target Lock Mechanism)
                    db.execute("""
                        UPDATE master_pelanggan SET status_lunas = 1, tgl_lunas = ?
                        WHERE nomen = ? AND periode = ? AND tipe = 'MC'
                    """, (str(row.get(col_pay, '')), nomen, target_period))
                    
                    row_count += 1

                elif data_type == 'ARDEBT':
                    val_ardebt = UploadEngine.cast_to_float(row.get(col_nom))
                    if val_ardebt > 0:
                        db.execute("INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah) VALUES (?, ?, ?)",
                                   (nomen, row.get('PERIODE_BILL', '-'), val_ardebt))
                        row_count += 1
            
            except:
                error_rows += 1
                continue

        # COMMIT SEMUA DATA SEKALIGUS KE DISK
        db.commit() 
        # --- HIGH SPEED SYNC: END ---

        log_action(session.get('username', 'Admin'), 'UPLOAD_SUCCESS', data_type, f"HighSpeed: {row_count} rows. File: {file_name}")
        
        # Log History Upload
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)",
                   (file_name, data_type, target_period, row_count, 'SUCCESS'))
        db.commit()

        return jsonify({"status": "success", "message": f"Integrasi {data_type} Berhasil. {row_count} baris diproses dalam hitungan detik."})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"status": "error", "message": f"Integrasi Gagal: {str(e)}"}), 500
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
