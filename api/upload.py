"""
Smart Integration Engine - Sunter Dashboard Pro (V13.01 Stability Fix)
Update: 2026-02-01
---------------------------------------------------------------------------
Teknologi Unggulan:
1. executemany() Bulk Injection: Mengirim puluhan ribu baris data secara instant.
2. ✅ FIX: Anti-Timeout - Menghapus redundansi update manual di level aplikasi 
   dan mengandalkan Trigger Database (schema.sql) untuk sinkronisasi status lunas.
3. ✅ FIX: Efisiensi I/O - Menghilangkan beban transaksi ganda yang menyebabkan 
   koneksi terputus saat upload file MB/Collection yang besar.
4. Memory Buffering: Pemrosesan data sepenuhnya di RAM sebelum commit.
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
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Akses Ditolak"}), 403

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak dideteksi"}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona
        
        # 1. OPTIMASI PEMBACAAN FILE
        if file_name.lower().endswith('.csv'):
            df = pd.read_csv(file, dtype=str, engine='c', low_memory=False).fillna('')
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

        if data_type == 'MC' and (col_brek or col_pay):
            data_type = 'MB'

        if data_type in ['ARDEBT', 'RUTE']:
            target_period = datetime.now().strftime('%m-%Y') if data_type == 'RUTE' else "GLOBAL-HISTORY"
        else:
            month_ref, year_ref = detect_file_period(df, data_type)
            if not month_ref: return jsonify({"status": "error", "message": "Gagal deteksi periode file"}), 400
            target_period = f"{month_ref}-{year_ref}"

        # 2. RAM BUFFERING
        bulk_main = []
        bulk_rute = []
        
        records = df.to_dict('records') 
        for row in records:
            if data_type == 'RUTE':
                c_pcez = UploadEngine.get_column(df, ['PCEZ', 'ZONA', 'ZONA_NOVAK', 'RUTE'])
                c_name = UploadEngine.get_column(df, ['PETUGAS', 'NAMA_PETUGAS'])
                if row.get(c_pcez) and row.get(c_name):
                    bulk_rute.append((str(row.get(c_pcez)).strip(), str(row.get(c_name)).strip()))
                continue

            n_raw = row.get(col_id)
            nomen = clean_nomen(n_raw)
            if not nomen: continue

            nominal = UploadEngine.cast_to_float(row.get(col_nom))

            if data_type == 'MC':
                c_zona = UploadEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ', 'RUTE'])
                z = autopilot_extract_zona(row.get(c_zona))
                if z:
                    bulk_main.append((
                        nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), 
                        z['pcez'], z['rayon'], nominal, row.get('NOMET', ''), 
                        target_period, row.get(col_hp, '-'), 'MC'
                    ))
            
            elif data_type in ['MB', 'COLLECTION']:
                b_rek = UploadEngine.clean_bulan_rek(str(row.get(col_brek, '')))
                if not b_rek:
                    dt_obj = datetime.strptime(target_period, '%m-%Y')
                    b_rek = dt_obj.strftime('%m%Y') 
                
                cat = "UNDUE" if data_type == 'MB' else "CURRENT"
                tgl_transaksi = str(row.get(col_pay, ''))
                bulk_main.append((nomen, tgl_transaksi, nominal, target_period, cat, b_rek))

            elif data_type == 'ARDEBT':
                if nominal > 0:
                    bulk_main.append((nomen, row.get('PERIODE_BILL', '-'), nominal, target_period))

        # 3. ATOMIC INJECTION
        db.execute("PRAGMA synchronous = OFF") 
        db.execute("PRAGMA journal_mode = MEMORY") # Optimasi tambahan untuk upload besar
        db.execute("BEGIN TRANSACTION")

        if data_type == 'RUTE':
            db.executemany("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", bulk_rute)
        
        elif data_type == 'MC':
            db.executemany("""
                INSERT OR REPLACE INTO master_pelanggan 
                (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, no_hp, tipe, status_lunas) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, bulk_main)
        
        elif data_type in ['MB', 'COLLECTION']:
            tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
            dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
            
            # Hanya Insert Transaksi. 
            # Status Lunas pada tabel master_pelanggan akan diupdate otomatis oleh TRIGGER di database.
            db.executemany(f"""
                INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori, bulan_rek) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, bulk_main)

        elif data_type == 'ARDEBT':
            db.executemany("INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, periode) VALUES (?, ?, ?, ?)", bulk_main)

        row_count = len(bulk_main) if data_type != 'RUTE' else len(bulk_rute)
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)",
                   (file_name, data_type, target_period, row_count, 'SUCCESS'))
        
        db.commit()
        db.execute("PRAGMA synchronous = NORMAL")
        
        log_action(session.get('username', 'Admin'), 'UPLOAD_SUCCESS', data_type, f"BulkSync: {row_count} rows processed.")
        return jsonify({"status": "success", "message": f"Integrasi {data_type} Berhasil! {row_count} baris diproses."})

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
