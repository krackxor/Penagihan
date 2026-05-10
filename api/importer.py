import pandas as pd
import numpy as np  # Penanganan NaN untuk validasi JSONB
import os
import gc
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy.dialects.postgresql import insert
from models import db, MasterPelanggan, TransaksiTagihan, DataSBRS

importer_bp = Blueprint('importer', __name__)

def clean_nomen(val):
    """Pembersihan Nomen agar seragam 8 digit."""
    if not val or pd.isna(val): return None
    s = str(val).strip().split('.')[0]
    return s[-8:].zfill(8)

def extract_periode(val):
    """Konversi format 042026 (MMYYYY) ke 202604 (YYYYMM)."""
    try:
        val = str(val).strip()
        if len(val) == 6 and val[2:].startswith('20'):
            return val[2:] + val[:2]
        return val[:6]
    except:
        return "202605"

def process_mega_file(file, logic_func, chunk_size=20000):
    """Mesin Turbo Chunking: Hemat RAM untuk file raksasa (Diturunkan ke 20k agar RAM stabil)."""
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    file.save(temp_path)

    try:
        # Menggunakan low_memory=False dan memory_map untuk efisiensi RAM
        reader = pd.read_csv(
            temp_path, sep=';', dtype=str, chunksize=chunk_size, 
            low_memory=False, memory_map=True
        )
        total = 0
        for chunk in reader:
            chunk.columns = chunk.columns.str.strip().str.upper()
            chunk = chunk.replace({np.nan: None})
            
            # Panggil fungsi logika yang me-return jumlah data tersimpan
            added_count = logic_func(chunk)
            if added_count:
                total += added_count
                
            db.session.commit()
            db.session.expunge_all() 
            gc.collect() # Bersihkan sisa RAM Pandas
            
        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@importer_bp.route('/sbrs-combined', methods=['POST'])
def import_sbrs():
    """
    Turbo Join V5.13: Solusi Anti-RAM Jebol.
    Otomatis mendaftarkan pelanggan baru jika belum ada di Master CID.
    Mendukung upload file MC / Spotbill raksasa tanpa Timeout 502.
    """
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')
    
    if not file_cust or not file_spot:
        return jsonify({"status": "error", "message": "Kedua file wajib diupload"}), 400

    try:
        # TAHAP 1: EKSTRAKSI CUSTOMER JADI LOOKUP DICTIONARY SANGAT RINGAN
        # Daripada simpan dataframe raksasa, kita simpan dictionary Nomen -> Data Cust
        # Ini menghemat RAM hingga 80% saat merge!
        cust_filename = secure_filename(file_cust.filename)
        cust_temp_path = os.path.join('instance', cust_filename)
        file_cust.save(cust_temp_path)
        
        lookup_cust = {}
        
        # Baca Customer dengan Chunking agar aman
        cust_reader = pd.read_csv(cust_temp_path, sep=';', dtype=str, chunksize=50000, low_memory=False)
        for c_chunk in cust_reader:
            c_chunk.columns = c_chunk.columns.str.strip().str.upper()
            c_chunk = c_chunk.replace({np.nan: None})
            
            col_key_c = 'CMR_ACCOUNT' if 'CMR_ACCOUNT' in c_chunk.columns else 'NOMEN'
            if col_key_c not in c_chunk.columns: continue
            
            # Simpan data tiap baris customer ke dictionary (memory efficient)
            for _, row in c_chunk.iterrows():
                nk = clean_nomen(row.get(col_key_c))
                if nk:
                    lookup_cust[nk] = row.to_dict()
        
        # Bersihkan file temp customer
        if os.path.exists(cust_temp_path): os.remove(cust_temp_path)


        # TAHAP 2: PROSES SPOTBILL (FILE UTAMA) DENGAN TURBO CHUNKING
        def sbrs_logic(df_spot_chunk):
            col_key_s = 'NOMEN' if 'NOMEN' in df_spot_chunk.columns else 'CMR_ACCOUNT'
            if col_key_s not in df_spot_chunk.columns: return 0
            
            master_provision = [] 
            sbrs_entries = []

            for _, spot_row in df_spot_chunk.iterrows():
                nomen = clean_nomen(spot_row.get(col_key_s))
                if not nomen: continue
                
                # Manual Merge: Ambil data customer dari RAM Dictionary
                cust_data = lookup_cust.get(nomen, {})
                
                # Gabungkan data Spotbill dan Customer menjadi satu dictionary
                merged_row = spot_row.to_dict()
                merged_row.update(cust_data)
                
                # Ambil value aman
                nama_pel = merged_row.get('CMR_NAME') or merged_row.get('NAMA') or 'Pelanggan Baru'
                ab_pel = merged_row.get('AB') or merged_row.get('CC') or 'AB Sunter'
                pc_ez = merged_row.get('PCEZBK') or (str(merged_row.get('PC','') or '') + str(merged_row.get('EZ','') or ''))
                
                # 1. AUTO-PROVISION MASTER (Mencegah ForeignKeyViolation)
                master_provision.append({
                    "nomen": nomen,
                    "nama": nama_pel,
                    "ab": ab_pel,
                    "pcez": pc_ez
                })

                # 2. LOGIKA SBRS (VERSI DETEKTIF FRAUD)
                def get_val(key):
                    key_l = key.lower()
                    for k, v in merged_row.items():
                        if str(k).lower() == key_l: return v
                    return None

                try:
                    curr = float(get_val('CURR_READ_1') or get_val('END_READ_STAN') or 0)
                    prev = float(get_val('PREV_READ_1') or get_val('CMR_PREV_READ') or 0)
                    
                    raw_rata = get_val('Estimation_Value') or get_val('AVG_CONSUMPTION')
                    rata = float(raw_rata) if raw_rata else 15.0
                except: 
                    curr, prev, rata = 0, 0, 15.0

                m3 = curr - prev
                
                skip_code = str(get_val('cmr_skip_code') or '').strip().upper()
                trbl_code = str(get_val('cmr_trbl1_code') or '').strip().upper()
                metode = str(get_val('Read_Method') or get_val('cmr_read_code') or '').strip().upper()

                # A. Kategori
                kat = "NORMAL"
                if m3 < 0: kat = "MINUS"
                elif m3 == 0: kat = "ZERO"
                elif m3 > (rata * 2): kat = "EKSTREM"
                elif m3 < (rata * 0.5): kat = "TURUN"

                # B. Detektif Sinergi
                indikasi = "Aman"
                if trbl_code in ['2D', '2E', '2F', '4E']: indikasi = "FRAUD: METER DICOLOK / BYPASS / SEGEL PUTUS"
                elif metode in ['30/PE', '40/PE', '35/PS']: indikasi = "WARNING: TEMBAK ANGKA (ESTIMASI)"
                elif skip_code in ['5G']: indikasi = "TOLAK BACA: PELANGGAN TIDAK IZINKAN"
                elif kat == "MINUS":
                    if m3 < -50: indikasi = "TEKNIS: GANTI METER BELUM MUTASI"
                    else: indikasi = "HUMAN ERROR: SALAH CATAT MUNDUR"
                elif kat == "ZERO":
                    if skip_code == '3A': indikasi = "WAJAR: RUMAH KOSONG"
                    elif trbl_code == '1B': indikasi = "TEKNIS: METER MATI"
                    else: indikasi = "MENCURIGAKAN: ZERO TANPA KETERANGAN"
                elif kat == "EKSTREM":
                    if m3 > (rata * 5) and m3 > 500: indikasi = "HUMAN ERROR: FATAL SALAH KETIK"
                    else: indikasi = "INDIKASI BOCOR DALAM / USAHA BARU"
                elif kat == "TURUN":
                    indikasi = "INDIKASI METER MELAMBAT / RUSAK"

                merged_row['INDIKASI_SINERGI'] = indikasi

                sbrs_entries.append({
                    "nomen": nomen,
                    "periode": extract_periode(merged_row.get('BILL_PERIOD') or '202605'),
                    "nama": nama_pel,
                    "ab": ab_pel,
                    "kelurahan": merged_row.get('KEL') or merged_row.get('KELURAHAN', ''),
                    "pcez": pc_ez,
                    "bulan_ini": m3,
                    "rata_rata": rata,
                    "stand_meter": curr,
                    "kategori_anomali": kat,
                    "raw_data": merged_row,
                    "status_audit": 0
                })

            # SINKRONISASI DATABASE BATCHING
            if master_provision:
                # Unik-kan Nomen agar tidak error saat batch insert
                unique_master = {m['nomen']: m for m in master_provision}.values()
                stmt_master = insert(MasterPelanggan).values(list(unique_master))
                upsert_master = stmt_master.on_conflict_do_nothing(index_elements=['nomen'])
                db.session.execute(upsert_master)
                db.session.flush() 

            if sbrs_entries:
                stmt_sbrs = insert(DataSBRS).values(sbrs_entries)
                upsert_sbrs = stmt_sbrs.on_conflict_do_update(
                    index_elements=['nomen', 'periode'],
                    set_={k: getattr(stmt_sbrs.excluded, k) for k in sbrs_entries[0].keys() if k not in ['nomen', 'periode']}
                )
                db.session.execute(upsert_sbrs)
                return len(sbrs_entries)
                
            return 0

        # Eksekusi Mesin Turbo untuk Spotbill (Menyatukan dengan Dictionary Customer di Memory)
        total_anomali = process_mega_file(file_spot, sbrs_logic, chunk_size=20000)
        
        # Bersihkan Memory
        lookup_cust.clear()
        gc.collect()
        
        return jsonify({"status": "success", "message": f"Sinergi Sukses! {total_anomali} data anomali masuk (Auto-Synced Master)."})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Sinkronisasi Gagal: {str(e)}"}), 500
