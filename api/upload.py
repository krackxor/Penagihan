"""
Turbo Integration Engine - Sunter Dashboard Pro (V12.82 Full Turbo)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Full Module Batching: Mendukung RUTE dan ARDEBT dalam sistem Turbo.
2. executemany() Integration: Eksekusi massal untuk semua tipe file agar cepat.
3. Smart Ardebt Detection: Filter otomatis untuk nominal > 0 agar database bersih.
4. Transaction Guard: Keamanan commit tunggal (All or Nothing).
"""

import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, log_action

upload_bp = Blueprint('upload', __name__)

class TurboEngine:
    @staticmethod
    def cast_to_float(value):
        """Konversi angka cerdas untuk format ribuan/desimal Indonesia."""
        try:
            if pd.isna(value) or str(value).strip() == '': return 0.0
            s_val = str(value).replace('\xa0', '').replace(' ', '').replace(',', '.')
            return float(s_val)
        except: 
            return 0.0

    @staticmethod
    def get_column(df, possible_names):
        """Mencari nama kolom secara fleksibel untuk berbagai format."""
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            if name.upper() in cols:
                return cols[name.upper()]
        return None

@upload_bp.route('/upload', methods=['POST'])
def handle_turbo_upload():
    # 1. AUTHENTICATION & FILE CHECK
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Akses Ditolak"}), 403

    file = request.files.get('file')
    if not file:
        return jsonify({"status": "error", "message": "File tidak dideteksi"}), 400
    
    file_name = file.filename
    db = get_db_connection()
    
    try:
        from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona
        
        # 2. OPTIMIZED FILE LOADING
        df = pd.read_excel(file, dtype=str).fillna('') if file_name.endswith(('.xlsx', '.xls')) else pd.read_csv(file, dtype=str).fillna('')
        data_type = identify_file_type(df)
        
        if not data_type:
            return jsonify({"status": "error", "message": "Format kolom tidak dikenali"}), 400

        # Mapping Kolom Utama
        col_id = TurboEngine.get_column(df, ['NOMEN', 'IDPEL', 'ID_PELANGGAN', 'CUST_ID'])
        col_nom = TurboEngine.get_column(df, ['NOMINAL', 'JUMLAH', 'TOTAL', 'JML_BAYAR'])
        col_pay = TurboEngine.get_column(df, ['TGL_BAYAR', 'PAY_DT', 'TGL_LUNAS'])
        col_brek = TurboEngine.get_column(df, ['BULAN_REK', 'BULAN', 'REKENING'])

        # Penentuan Periode Target
        month_ref, year_ref = detect_file_period(df, data_type)
        target_period = f"{month_ref}-{year_ref}" if month_ref else "GLOBAL"

        batch_list = []
        
        # 3. MEMORY LOOP (PROSES DATA DI MEMORI)
        for index, row in df.iterrows():
            # A. MODUL RUTE (KHUSUS)
            if data_type == 'RUTE':
                c_pcez = TurboEngine.get_column(df, ['PCEZ', 'ZONA', 'ZONA_NOVAK', 'RUTE'])
                c_name = TurboEngine.get_column(df, ['PETUGAS', 'NAMA_PETUGAS'])
                raw_pcez = str(row.get(c_pcez, '')).strip()
                p_name = str(row.get(c_name, '')).strip()
                if raw_pcez and p_name:
                    clean_pcez = raw_pcez.replace('/', '').replace('.', '').replace('-', '')
                    batch_list.append((clean_pcez, p_name))
                continue

            # B. MODUL DENGAN NOMENKLATUR (MC, MB, COLL, ARDEBT)
            n_raw = row.get(col_id)
            nomen = clean_nomen(n_raw)
            if not nomen: continue

            # MODUL MC
            if data_type == 'MC':
                c_zona = TurboEngine.get_column(df, ['ZONA_NOVAK', 'ZONA', 'PCEZ'])
                z = autopilot_extract_zona(row.get(c_zona))
                if z:
                    batch_list.append((nomen, row.get('NAMA_PEL', ''), row.get('ALM1_PEL', ''), 
                                     z['pcez'], z['rayon'], TurboEngine.cast_to_float(row.get(col_nom)), 
                                     row.get('NOMET', ''), target_period))

            # MODUL ARDEBT
            elif data_type == 'ARDEBT':
                val_ardebt = TurboEngine.cast_to_float(row.get(col_nom))
                if val_ardebt > 0:
                    batch_list.append((nomen, row.get('PERIODE_BILL', '-'), val_ardebt, target_period))

            # MODUL MB & COLLECTION
            elif data_type in ['MB', 'COLLECTION']:
                b_rek = str(row.get(col_brek, '')).strip() or target_period.replace('-', '')
                cat = "UNDUE" if data_type == 'MB' else "CURRENT"
                batch_list.append((nomen, row.get(col_pay, ''), TurboEngine.cast_to_float(row.get(col_nom)), 
                                 target_period, cat, b_rek))

        # 4. EXECUTE BATCH (SANGAT CEPAT)
        if data_type == 'RUTE':
            db.executemany("""
                INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, batch_list)
        
        elif data_type == 'MC':
            db.executemany("""
                INSERT OR REPLACE INTO master_pelanggan 
                (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, status_lunas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, batch_list)

        elif data_type == 'ARDEBT':
            db.executemany("""
                INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, periode) 
                VALUES (?, ?, ?, ?)
            """, batch_list)
        
        elif data_type in ['MB', 'COLLECTION']:
            tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
            dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
            
            db.executemany(f"""
                INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori, bulan_rek) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, batch_list)

            # 5. TURBO SYNC STATUS LUNAS MASSAL
            db.execute(f"""
                UPDATE master_pelanggan SET status_lunas = 1 
                WHERE periode = ? AND nomen IN (SELECT nomen FROM {tbl} WHERE periode = ?)
            """, (target_period, target_period))

        # FINALISASI TRANSAKSI
        db.commit() 
        log_action(user_id=session.get('username'), action='UPLOAD_TURBO', module=data_type, details=f"Batch: {len(batch_list)} rows")
        
        return jsonify({"status": "success", "message": f"Turbo Sync {data_type} Selesai: {len(batch_list)} baris diproses."})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()
