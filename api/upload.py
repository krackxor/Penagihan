import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, log_action

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    @staticmethod
    def cast_to_float(value):
        """Konversi angka cerdas dengan performa tinggi."""
        if not value or pd.isna(value): return 0.0
        try:
            s_val = str(value).replace('\xa0', '').replace(' ', '').replace("'", "")
            if ',' in s_val:
                if '.' in s_val: s_val = s_val.replace('.', '')
                s_val = s_val.replace(',', '.')
            return float(s_val)
        except: return 0.0

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
        
        # 1. DATABASE TUNING (Pragma untuk kecepatan maksimal)
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA synchronous = OFF")
        db.execute("PRAGMA cache_size = -10000") # 10MB cache

        # 2. FAST READ (Hanya baca data yang diperlukan)
        df = pd.read_csv(file, dtype=str).fillna('') if file_name.endswith('.csv') else pd.read_excel(file, dtype=str).fillna('')
        data_type = identify_file_type(df)
        
        if not data_type:
            return jsonify({"status": "error", "message": "Format tidak dikenali"}), 400

        # Optimization: Mapping Kolom di luar loop
        col_id = UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG', 'SALDO'])
        col_pay = UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID'])
        col_brek = UploadEngine.get_column(df, ['BULAN_REK', 'BULAN', 'REKENING'])
        col_mc_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ', 'RUTE'])
        col_rute_pcez = UploadEngine.get_column(df, ['PCEZ', 'ZONA', 'ZONA_NOVAK', 'RUTE'])
        col_rute_name = UploadEngine.get_column(df, ['PETUGAS', 'NAMA_PETUGAS'])

        # Penentuan Periode
        if data_type in ['ARDEBT', 'RUTE']:
            target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
        else:
            month_ref, year_ref = detect_file_period(df, data_type)
            if not month_ref: return jsonify({"status": "error", "message": "Gagal deteksi periode"}), 400
            target_period = f"{month_ref}-{year_ref}"

        # 3. OPTIMIZED ITERATION (Gunakan to_dict('records') jauh lebih cepat dari iterrows)
        records = df.to_dict('records')
        batch_inserts = []
        batch_sync_lunas = []
        row_count = 0

        db.execute("BEGIN") # Mulai transaksi manual

        for row in records:
            try:
                # A. MODUL RUTE
                if data_type == 'RUTE':
                    raw_pcez = str(row.get(col_rute_pcez, '')).strip()
                    p_name = str(row.get(col_rute_name, '')).strip()
                    if raw_pcez and p_name:
                        clean_pcez = raw_pcez.replace('/', '').replace('.', '').replace('-', '')
                        db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (clean_pcez, p_name))
                        row_count += 1
                    continue

                # Sanitasi Nomen
                nomen = clean_nomen(row.get(col_id))
                if not nomen: continue

                # B. BATCH MAPPING
                if data_type == 'MC':
                    z = autopilot_extract_zona(row.get(col_mc_zona))
                    if z:
                        batch_inserts.append((nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), z['pcez'], z['rayon'], 
                                              UploadEngine.cast_to_float(row.get(col_nom)), row.get('NOMET', ''), target_period))
                
                elif data_type == 'ARDEBT':
                    val = UploadEngine.cast_to_float(row.get(col_nom))
                    if val > 0:
                        batch_inserts.append((nomen, row.get('PERIODE_BILL', '-'), val, target_period))

                elif data_type in ['MB', 'COLLECTION']:
                    cat = "UNDUE" if data_type == 'MB' else "CURRENT"
                    b_rek = str(row.get(col_brek, '')).strip() or target_period.replace('-', '')
                    batch_inserts.append((nomen, row.get(col_pay, ''), UploadEngine.cast_to_float(row.get(col_nom)), target_period, cat, b_rek))
                    batch_sync_lunas.append((nomen, target_period))
                
                row_count += 1
            except: continue

        # 4. EXECUTE MANY (Proses ribuan baris dalam milidetik)
        if data_type == 'MC':
            db.executemany("INSERT OR REPLACE INTO master_pelanggan VALUES (?,?,?,?,?,?,?,?,0)", batch_inserts)
        elif data_type == 'ARDEBT':
            db.executemany("INSERT OR REPLACE INTO ardebt VALUES (?,?,?,?)", batch_inserts)
        elif data_type in ['MB', 'COLLECTION']:
            tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
            tgl_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
            db.executemany(f"INSERT OR REPLACE INTO {tbl} (nomen,{tgl_col},nominal,periode,kategori,bulan_rek) VALUES (?,?,?,?,?,?)", batch_inserts)
            db.executemany("UPDATE master_pelanggan SET status_lunas = 1 WHERE nomen = ? AND periode = ?", batch_sync_lunas)

        # Finalisasi
        log_action(user_id=session.get('username', 'Admin'), action='UPLOAD_SUCCESS', module=data_type, 
                   details=f"File: {file_name} | Sukses: {row_count} | Periode: {target_period}", ip=request.remote_addr)
        
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?,?,?,?,'SUCCESS')", 
                   (file_name, data_type, target_period, row_count))
        
        db.commit()
        return jsonify({"status": "success", "message": f"Selesai: {row_count} baris diproses."})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()
