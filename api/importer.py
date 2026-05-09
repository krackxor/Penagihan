import pandas as pd
import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy.dialects.postgresql import insert
from models import db, MasterPelanggan, TransaksiTagihan, DataSBRS

importer_bp = Blueprint('importer', __name__)

def clean_nomen(val):
    """Membersihkan nomen agar seragam 8 digit."""
    if not val or pd.isna(val): return None
    return str(val).strip().split('.')[0][-8:].zfill(8)

def extract_periode(val):
    """Konversi format 042026 (MMYYYY) ke 202604 (YYYYMM)."""
    try:
        val = str(val).strip()
        if len(val) == 6:
            return val[2:] + val[:2] # 042026 -> 202604
        return val[:6]
    except:
        return "202605"

def process_mega_file(file, logic_func):
    """Mesin Turbo: Memproses 50.000 baris per putaran untuk hemat RAM."""
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
            total += logic_func(chunk)
            db.session.commit()
            db.session.expunge_all() # Kosongkan RAM setelah commit
        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@importer_bp.route('/cid', methods=['POST'])
def import_cid():
    """Import Master Pelanggan dengan PostgreSQL UPSERT."""
    file = request.files.get('file')
    if not file: return jsonify({"status": "error", "message": "File CID kosong"}), 400
    
    def cid_logic(df):
        data_list = []
        for _, row in df.iterrows():
            nomen = clean_nomen(row.get('NOMEN') or row.get('CMR_ACCOUNT'))
            if not nomen: continue
            data_list.append({
                "nomen": nomen,
                "nama": row.get('CMR_NAME', 'Pelanggan'),
                "pcez": row.get('PCEZBK') or row.get('PC', '') + row.get('EZ', ''),
                "ab": row.get('CC') or row.get('AB', 'AB Sunter'),
                "kelurahan": row.get('KELURAHAN') or row.get('KEL', ''),
                "tarif": row.get('TARIF') or row.get('CMR_TARIFF', '')
            })
        if data_list:
            stmt = insert(MasterPelanggan).values(data_list)
            # Update jika Nomen sudah ada (Sinergi Upsert)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['nomen'],
                set_={k: getattr(stmt.excluded, k) for k in data_list[0].keys() if k != 'nomen'}
            )
            db.session.execute(upsert_stmt)
            return len(data_list)
        return 0

    total = process_mega_file(file, cid_logic)
    return jsonify({"status": "success", "message": f"{total} Master Pelanggan Berhasil Disinkronkan"})

@importer_bp.route('/sbrs-combined', methods=['POST'])
def import_sbrs():
    """
    Turbo Join: Menggabungkan Customer & Spotbill untuk SBRS.
    Mengisi kolom Denormalisasi (ab, kelurahan) agar Dashboard kencang.
    """
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')
    
    if not file_cust or not file_spot:
        return jsonify({"status": "error", "message": "File Customer & Spotbill wajib ada"}), 400

    try:
        # Load Customer ke Memory (Biasanya tidak sebesar file transaksi)
        df_cust = pd.read_csv(file_cust, sep=';', dtype=str).rename(columns=str.upper)
        df_cust['NOMEN_KEY'] = df_cust['CMR_ACCOUNT'].apply(clean_nomen)

        def sbrs_logic(df_spot):
            data_list = []
            # Join Spotbill dengan Customer Data di tingkat RAM
            df_merged = pd.merge(df_spot, df_cust, left_on='NOMEN', right_on='NOMEN_KEY', how='left')
            
            for _, row in df_merged.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                if not nomen: continue
                
                m3 = int(row.get('CMR_DIAL_DIFFERENCE', 0))
                rata = 15
                kat = "NORMAL"
                if m3 == 0: kat = "ZERO"
                elif m3 > (rata * 2): kat = "EKSTREM"
                elif m3 < (rata * 0.5): kat = "TURUN"

                data_list.append({
                    "nomen": nomen,
                    "periode": extract_periode(row.get('BILL_PERIOD', '052026')),
                    "nama": row.get('CMR_NAME'),
                    "ab": row.get('AB', 'AB Sunter'),
                    "kelurahan": row.get('KEL', ''),
                    "pcez": row.get('PC', '') + row.get('EZ', ''),
                    "bulan_ini": m3,
                    "rata_rata": rata,
                    "stand_meter": int(row.get('CURR_READ_1', 0)),
                    "kategori_anomali": kat
                })

            if data_list:
                stmt = insert(DataSBRS).values(data_list)
                # Upsert agar tidak error UNIQUE(nomen, periode)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=['nomen', 'periode'],
                    set_={k: getattr(stmt.excluded, k) for k in data_list[0].keys() if k not in ['nomen', 'periode']}
                )
                db.session.execute(upsert_stmt)
                return len(data_list)
            return 0

        total = process_mega_file(file_spot, sbrs_logic)
        return jsonify({"status": "success", "message": f"{total} Data SBRS Gabungan Berhasil Dianalisa"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
