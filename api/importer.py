import pandas as pd
import numpy as np  # Penanganan NaN untuk validasi JSONB
import os
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

def process_mega_file(file, logic_func):
    """Mesin Turbo Chunking: Hemat RAM untuk file raksasa."""
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    file.save(temp_path)

    try:
        reader = pd.read_csv(
            temp_path, sep=';', dtype=str, chunksize=50000, 
            low_memory=False, memory_map=True
        )
        total = 0
        for chunk in reader:
            chunk.columns = chunk.columns.str.strip().str.upper()
            chunk = chunk.replace({np.nan: None})
            total += logic_func(chunk)
            db.session.commit()
            db.session.expunge_all() 
        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@importer_bp.route('/sbrs-combined', methods=['POST'])
def import_sbrs():
    """
    Turbo Join V5.12: Solusi ForeignKeyViolation.
    Otomatis mendaftarkan pelanggan baru jika belum ada di Master CID.
    """
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')
    
    if not file_cust or not file_spot:
        return jsonify({"status": "error", "message": "Kedua file wajib ada"}), 400

    try:
        df_cust = pd.read_csv(file_cust, sep=';', dtype=str).rename(columns=str.upper)
        col_key_c = 'CMR_ACCOUNT' if 'CMR_ACCOUNT' in df_cust.columns else 'NOMEN'
        df_cust['NOMEN_KEY'] = df_cust[col_key_c].apply(clean_nomen)

        def sbrs_logic(df_spot):
            col_key_s = 'NOMEN' if 'NOMEN' in df_spot.columns else 'CMR_ACCOUNT'
            df_merged = pd.merge(df_spot, df_cust, left_on=col_key_s, right_on='NOMEN_KEY', how='left')
            df_merged = df_merged.replace({np.nan: None})
            
            master_provision = [] # Wadah untuk pendaftaran pelanggan baru otomatis
            sbrs_entries = []

            for _, row in df_merged.iterrows():
                nomen = clean_nomen(row.get(col_key_s))
                if not nomen: continue
                
                # 1. AUTO-PROVISION MASTER (Mencegah ForeignKeyViolation)
                master_provision.append({
                    "nomen": nomen,
                    "nama": row.get('CMR_NAME') or row.get('NAMA', 'Pelanggan Baru'),
                    "ab": row.get('AB') or 'AB Sunter',
                    "pcez": row.get('PCEZBK') or (str(row.get('PC','') or '') + str(row.get('EZ','') or ''))
                })

                # 2. LOGIKA SBRS (VERSI DETEKTIF FRAUD & CASE INSENSITIVE)
                all_headers = row.to_dict()
                
                # Fungsi kebal huruf besar/kecil untuk mencari nama kolom
                def get_val(key):
                    key_l = key.lower()
                    for k, v in all_headers.items():
                        if str(k).lower() == key_l: return v
                    return None

                try:
                    curr = float(get_val('CURR_READ_1') or get_val('END_READ_STAN') or 0)
                    prev = float(get_val('PREV_READ_1') or get_val('CMR_PREV_READ') or 0)
                    
                    # Cari nilai rata-rata asli dari TXT, kalau kosong baru set 15.0
                    raw_rata = get_val('Estimation_Value') or get_val('AVG_CONSUMPTION')
                    rata = float(raw_rata) if raw_rata else 15.0
                except: 
                    curr, prev, rata = 0, 0, 15.0

                m3 = curr - prev
                
                # Ekstraksi Kode Lapangan
                skip_code = str(get_val('cmr_skip_code') or '').strip().upper()
                trbl_code = str(get_val('cmr_trbl1_code') or '').strip().upper()
                metode = str(get_val('Read_Method') or get_val('cmr_read_code') or '').strip().upper()

                # A. TENTUKAN KATEGORI DASAR (Termasuk MINUS)
                kat = "NORMAL"
                if m3 < 0: kat = "MINUS"
                elif m3 == 0: kat = "ZERO"
                elif m3 > (rata * 2): kat = "EKSTREM"
                elif m3 < (rata * 0.5): kat = "TURUN"

                # B. TENTUKAN INDIKASI SPESIFIK (MESIN DETEKTIF)
                indikasi = "Aman"
                
                # 1. Cek Kenakalan / Tembak Angka Dulu
                if trbl_code in ['2D', '2E', '2F', '4E']:
                    indikasi = "FRAUD: METER DICOLOK / BYPASS / SEGEL PUTUS"
                elif metode in ['30/PE', '40/PE', '35/PS']:
                    indikasi = "WARNING: TEMBAK ANGKA (ESTIMASI)"
                elif skip_code in ['5G']:
                    indikasi = "TOLAK BACA: PELANGGAN TIDAK IZINKAN"
                
                # 2. Cek Berdasarkan Volume Jika Tidak Ada Pelanggaran Jelas
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

                # Simpan hasil detektif ke dalam raw_data
                all_headers['INDIKASI_SINERGI'] = indikasi

                sbrs_entries.append({
                    "nomen": nomen,
                    "periode": extract_periode(row.get('BILL_PERIOD') or '202605'),
                    "nama": row.get('CMR_NAME') or row.get('NAMA', 'Pelanggan'),
                    "ab": row.get('AB') or row.get('CC', 'AB Sunter'),
                    "kelurahan": row.get('KEL') or row.get('KELURAHAN', ''),
                    "pcez": row.get('PCEZBK') or (str(row.get('PC','') or '') + str(row.get('EZ','') or '')),
                    "bulan_ini": m3,
                    "rata_rata": rata,
                    "stand_meter": curr,
                    "kategori_anomali": kat,
                    "raw_data": all_headers,
                    "status_audit": 0
                })

            # --- SINKRONISASI INDUK (MASTER PELANGGAN) DULU ---
            if master_provision:
                stmt_master = insert(MasterPelanggan).values(master_provision)
                # DO NOTHING jika sudah ada, agar data master asli tidak tertimpa data minimal
                upsert_master = stmt_master.on_conflict_do_nothing(index_elements=['nomen'])
                db.session.execute(upsert_master)
                db.session.flush() # Pastikan Induk sudah eksis di DB

            # --- BARU SINKRONISASI ANAK (DATA SBRS) ---
            if sbrs_entries:
                stmt_sbrs = insert(DataSBRS).values(sbrs_entries)
                upsert_sbrs = stmt_sbrs.on_conflict_do_update(
                    index_elements=['nomen', 'periode'],
                    set_={k: getattr(stmt_sbrs.excluded, k) for k in sbrs_entries[0].keys() if k not in ['nomen', 'periode']}
                )
                db.session.execute(upsert_sbrs)
                return len(sbrs_entries)
            return 0

        total = process_mega_file(file_spot, sbrs_logic)
        return jsonify({"status": "success", "message": f"Sinergi Sukses! {total} data anomali masuk (Auto-Synced Master)."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Sinkronisasi Gagal: {str(e)}"}), 500
