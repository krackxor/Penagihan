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
        
        # 1. ULTIMATE DATABASE TUNING
        # Menggunakan mode memori dan menonaktifkan sinkronisasi disk selama proses upload
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA synchronous = OFF")
        db.execute("PRAGMA cache_size = -64000") # 64MB Cache
        db.execute("PRAGMA temp_store = MEMORY")

        # 2. FAST READ
        if file_name.endswith('.csv'):
            df = pd.read_csv(file, dtype=str, engine='c').fillna('')
        else:
            df = pd.read_excel(file, dtype=str).fillna('')
            
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Format tidak dikenali"}), 400

        # Mapping Kolom Utama (Sekali saja di luar loop)
        col_map = {
            'id': UploadEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID']),
            'nom': UploadEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR', 'PIUTANG', 'SALDO']),
            'pay': UploadEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS', 'DATE_PAID']),
            'brek': UploadEngine.get_column(df, ['BULAN_REK', 'BULAN', 'REKENING']),
            'mc_z': UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ', 'RUTE']),
            'rt_p': UploadEngine.get_column(df, ['PCEZ', 'ZONA', 'ZONA_NOVAK', 'RUTE']),
            'rt_n': UploadEngine.get_column(df, ['PETUGAS', 'NAMA_PETUGAS'])
        }

        # Penentuan Periode
        target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
        if data_type not in ['ARDEBT', 'RUTE']:
            month_ref, year_ref = detect_file_period(df, data_type)
            if month_ref: target_period = f"{month_ref}-{year_ref}"

        # 3. FAST ITERATION & BATCH PREPARATION
        records = df.to_dict('records')
        batch_inserts = []
        batch_sync_lunas = []
        row_count = 0

        # Gunakan 'BEGIN IMMEDIATE' untuk mengunci DB sejak awal agar tidak ada antrean
        db.execute("BEGIN IMMEDIATE")

        for row in records:
            try:
                # MODUL RUTE (Sekarang menggunakan Batching)
                if data_type == 'RUTE':
                    raw_pcez = str(row.get(col_map['rt_p'], '')).strip()
                    p_name = str(row.get(col_map['rt_n'], '')).strip()
                    if raw_pcez and p_name:
                        clean_pcez = raw_pcez.replace('/', '').replace('.', '').replace('-', '')
                        batch_inserts.append((clean_pcez, p_name))
                        row_count += 1
                    continue

                # Sanitasi Nomen
                nomen = clean_nomen(row.get(col_map['id']))
                if not nomen: continue

                if data_type == 'MC':
                    z = autopilot_extract_zona(row.get(col_map['mc_z']))
                    if z:
                        batch_inserts.append((nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), z['pcez'], z['rayon'], 
                                              UploadEngine.cast_to_float(row.get(col_map['nom'])), row.get('NOMET', ''), target_period))
                
                elif data_type == 'ARDEBT':
                    val = UploadEngine.cast_to_float(row.get(col_map['nom']))
                    if val > 0:
                        batch_inserts.append((nomen, row.get('PERIODE_BILL', '-'), val, target_period))

                elif data_type in ['MB', 'COLLECTION']:
                    cat = "UNDUE" if data_type == 'MB' else "CURRENT"
                    b_rek = str(row.get(col_map['brek'], '')).strip() or target_period.replace('-', '')
                    batch_inserts.append((nomen, row.get(col_map['pay'], ''), UploadEngine.cast_to_float(row.get(col_map['nom'])), target_period, cat, b_rek))
                    batch_sync_lunas.append((nomen, target_period))
                
                row_count += 1
            except: continue

        # 4. EXECUTE MANY (Inti dari Kecepatan)
        if data_type == 'RUTE':
            db.executemany("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", batch_inserts)
        elif data_type == 'MC':
            db.executemany("INSERT OR REPLACE INTO master_pelanggan VALUES (?,?,?,?,?,?,?,?,0)", batch_inserts)
        elif data_type == 'ARDEBT':
            db.executemany("INSERT OR REPLACE INTO ardebt VALUES (?,?,?,?)", batch_inserts)
        elif data_type in ['MB', 'COLLECTION']:
            tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
            tgl_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
            db.executemany(f"INSERT OR REPLACE INTO {tbl} (nomen,{tgl_col},nominal,periode,kategori,bulan_rek) VALUES (?,?,?,?,?,?)", batch_inserts)
            # Batch Update Status Lunas
            if batch_sync_lunas:
                db.executemany("UPDATE master_pelanggan SET status_lunas = 1 WHERE nomen = ? AND periode = ?", batch_sync_lunas)

        # 5. FINALISASI
        db.commit() # Tulis semua ke disk dalam satu transaksi tunggal

        log_action(user_id=session.get('username', 'Admin'), action='UPLOAD_SUCCESS', module=data_type, 
                   details=f"File: {file_name} | Sukses: {row_count}", ip=request.remote_addr)
        
        return jsonify({"status": "success", "message": f"Integrasi {data_type} Berhasil: {row_count} baris."})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"status": "error", "message": f"Gagal: {str(e)}"}), 500
    finally:
        db.close()
