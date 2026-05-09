import pandas as pd
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
        if len(val) == 6:
            # Jika format MMYYYY (misal 042026) -> 202604
            if val[2:].startswith('20'): return val[2:] + val[:2]
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
            # Standarisasi Header menjadi Uppercase
            chunk.columns = chunk.columns.str.strip().str.upper()
            total += logic_func(chunk)
            db.session.commit()
            db.session.expunge_all() 
        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@importer_bp.route('/cid', methods=['POST'])
def import_cid():
    """Import Master Pelanggan dengan penyimpanan seluruh header asli."""
    file = request.files.get('file')
    if not file: return jsonify({"status": "error", "message": "File CID kosong"}), 400
    
    def cid_logic(df):
        data_list = []
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('CMR_ACCOUNT') or row.get('NOMEN'))
            if not nomen: continue
            
            # AMBIL SEMUA HEADER: Konversi baris ke Dictionary
            raw_data_dict = row.to_dict()

            data_list.append({
                "nomen": nomen,
                "nama": row.get('CMR_NAME') or row.get('NAMA', 'Pelanggan'),
                "pcez": row.get('PCEZBK') or (str(row.get('PC','')) + str(row.get('EZ',''))),
                "ab": row.get('CC') or row.get('AB', 'AB Sunter'),
                "kelurahan": row.get('KELURAHAN') or row.get('KEL', ''),
                "tarif": row.get('TARIF') or row.get('CMR_TARIFF', ''),
                "raw_data": raw_data_dict # Simpan semua header asli
            })

        if data_list:
            stmt = insert(MasterPelanggan).values(data_list)
            # Sinergi Upsert
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['nomen'],
                set_={k: getattr(stmt.excluded, k) for k in data_list[0].keys() if k != 'nomen'}
            )
            db.session.execute(upsert_stmt)
            return len(data_list)
        return 0

    total = process_mega_file(file, cid_logic)
    return jsonify({"status": "success", "message": f"{total} Master Pelanggan Disinkronkan (Full Header Captured)"})

@importer_bp.route('/sbrs-combined', methods=['POST'])
def import_sbrs():
    """
    Turbo Join V5.8: Menggabungkan Customer & Spotbill.
    Seluruh header dari kedua file disimpan ke dalam JSONB.
    """
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')
    
    if not file_cust or not file_spot:
        return jsonify({"status": "error", "message": "Kedua file wajib ada"}), 400

    try:
        # Load Peta Wilayah (Customer)
        df_cust = pd.read_csv(file_cust, sep=';', dtype=str).rename(columns=str.upper)
        col_key_c = 'CMR_ACCOUNT' if 'CMR_ACCOUNT' in df_cust.columns else 'NOMEN'
        df_cust['NOMEN_KEY'] = df_cust[col_key_c].apply(clean_nomen)

        def sbrs_logic(df_spot):
            # Tentukan kolom join di file spotbill
            col_key_s = 'NOMEN' if 'NOMEN' in df_spot.columns else 'CMR_ACCOUNT'
            
            # Turbo Join di RAM
            df_merged = pd.merge(df_spot, df_cust, left_on=col_key_s, right_on='NOMEN_KEY', how='left')
            
            data_list = []
            for _, row in df_merged.iterrows():
                nomen = clean_nomen(row.get(col_key_s))
                if not nomen: continue
                
                # Konversi satu baris hasil join menjadi Dictionary
                # Ini mencakup header dari spot_bill DAN customer.
                all_headers = row.to_dict()
                
                # Kalkulasi Anomali
                curr = float(row.get('CURR_READ_1') or row.get('END_READ_STAN') or 0)
                prev = float(row.get('PREV_READ_1') or row.get('CMR_PREV_READ') or 0)
                m3 = curr - prev
                rata = float(row.get('AVG_CONSUMPTION') or 15)
                
                kat = "NORMAL"
                if m3 == 0: kat = "ZERO"
                elif m3 > (rata * 2): kat = "EKSTREM"
                elif m3 < (rata * 0.5): kat = "TURUN"

                data_list.append({
                    "nomen": nomen,
                    "periode": extract_periode(row.get('BILL_PERIOD') or row.get('PERIODE') or '202605'),
                    "nama": row.get('CMR_NAME') or row.get('NAMA', 'Pelanggan'),
                    "ab": row.get('AB') or row.get('CC', 'AB Sunter'),
                    "kelurahan": row.get('KEL') or row.get('KELURAHAN', ''),
                    "pcez": row.get('PCEZBK') or (str(row.get('PC','')) + str(row.get('EZ',''))),
                    "bulan_ini": m3,
                    "rata_rata": rata,
                    "stand_meter": curr,
                    "kategori_anomali": kat,
                    "raw_data": all_headers # SELURUH HEADER MASUK SINI
                })

            if data_list:
                stmt = insert(DataSBRS).values(data_list)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=['nomen', 'periode'],
                    set_={k: getattr(stmt.excluded, k) for k in data_list[0].keys() if k not in ['nomen', 'periode']}
                )
                db.session.execute(upsert_stmt)
                return len(data_list)
            return 0

        total = process_mega_file(file_spot, sbrs_logic)
        return jsonify({"status": "success", "message": f"Sinergi Berhasil! {total} data anomali dengan header lengkap disimpan."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Fatal Error: {str(e)}"}), 500
