import pandas as pd  # <-- DIPERBAIKI: Harus lengkap agar tidak ModuleNotFoundError
import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy.dialects.postgresql import insert
from models import db, MasterPelanggan, TransaksiTagihan, DataSBRS

importer_bp = Blueprint('importer', __name__)

def extract_periode(val):
    """Konversi format tanggal sistem ke YYYYMM."""
    try:
        if not val or pd.isna(val): return "202601"
        return pd.to_datetime(val).strftime('%Y%m')
    except:
        return str(val)[:6]

def process_mega_file(file, logic_func):
    """
    Mesin Turbo untuk memproses file raksasa (1GB+) dengan teknik Chunking.
    """
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    file.save(temp_path)

    try:
        # 1. Chunksize 50.000: Memproses 50rb baris sekaligus per putaran
        reader = pd.read_csv(
            temp_path, 
            sep=';', 
            dtype=str, 
            chunksize=50000, 
            low_memory=False, 
            memory_map=True
        )
        
        total_processed = 0
        for chunk in reader:
            chunk.columns = chunk.columns.str.strip().str.upper()
            processed_count = logic_func(chunk)
            total_processed += processed_count
            
            # 2. Kirim ke database dan kosongkan RAM
            db.session.commit()
            db.session.expunge_all() 

        return total_processed
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@importer_bp.route('/cid', methods=['POST'])
def import_cid():
    file = request.files.get('file')
    if not file: return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    try:
        def cid_logic(df):
            data_list = []
            for _, row in df.iterrows():
                nomen = row.get('NOMEN')
                if not nomen: continue
                data_list.append({
                    "nomen": str(nomen).strip()[:8],
                    "nama": row.get('JENIS_PELANGGAN', 'Pelanggan'),
                    "pcez": row.get('PCEZBK'),
                    "ab": row.get('CC', 'AB Sunter'),
                    "tarif": row.get('TARIF'),
                    "kelurahan": row.get('KELURAHAN') or row.get('KEL')
                })

            if data_list:
                # 3. PostgreSQL UPSERT: Update data lama, masukkan data baru (Turbo)
                stmt = insert(MasterPelanggan).values(data_list)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=['nomen'],
                    set_={
                        "nama": stmt.excluded.nama,
                        "pcez": stmt.excluded.pcez,
                        "ab": stmt.excluded.ab,
                        "tarif": stmt.excluded.tarif,
                        "kelurahan": stmt.excluded.kelurahan
                    }
                )
                db.session.execute(upsert_stmt)
                return len(data_list)
            return 0

        total = process_mega_file(file, cid_logic)
        return jsonify({"status": "success", "message": f"{total} Pelanggan Disinkronkan (Turbo Mode)"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    file = request.files.get('file')
    sumber = request.form.get('sumber', 'MC')
    
    try:
        def tagihan_logic(df):
            data_list = []
            for _, row in df.iterrows():
                nomen = row.get('NOMEN')
                if not nomen: continue
                data_list.append({
                    "nomen": str(nomen).strip()[:8],
                    "nominal": float(row.get('TOTAL_TAGIHAN', 0)),
                    "periode": extract_periode(row.get('PERIODE_DTTM')),
                    "sumber": sumber
                })
            
            if data_list:
                # 4. Bulk Insert: Masukkan data dalam jumlah besar sekaligus
                db.session.bulk_insert_mappings(TransaksiTagihan, data_list)
                return len(data_list)
            return 0

        total = process_mega_file(file, tagihan_logic)
        return jsonify({"status": "success", "message": f"{total} Tagihan {sumber} Berhasil Diimport"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/sbrs', methods=['POST'])
def import_sbrs():
    file = request.files.get('file')
    try:
        def sbrs_logic(df):
            data_list = []
            for _, row in df.iterrows():
                nomen = row.get('NOMEN')
                if not nomen: continue
                
                m3 = int(row.get('KONSUMSI', 0))
                rata = 15
                kat = "NORMAL"
                if m3 == 0: kat = "ZERO"
                elif m3 > (rata * 2): kat = "EKSTREM"
                
                data_list.append({
                    "nomen": str(nomen).strip()[:8],
                    "bulan_ini": m3,
                    "rata_rata": rata,
                    "stand_meter": int(row.get('END_READ_STAN', 0)),
                    "kategori_anomali": kat
                })
            
            if data_list:
                db.session.bulk_insert_mappings(DataSBRS, data_list)
                return len(data_list)
            return 0

        total = process_mega_file(file, sbrs_logic)
        return jsonify({"status": "success", "message": f"{total} Data SBRS Berhasil Dianalisa"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
