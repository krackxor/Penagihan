import pandas as pd
import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from models import db, MasterPelanggan, MasterPetugas, TransaksiTagihan, DataSBRS

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
    Mesin utama untuk memproses file raksasa tanpa membuat RAM VPS meledak.
    """
    # 1. Simpan file fisik ke disk (Streaming) agar RAM tidak penuh
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    file.save(temp_path)

    try:
        # 2. Baca file per 10.000 baris (Chunking)
        # memory_map=True mempercepat akses file besar langsung dari disk
        reader = pd.read_csv(
            temp_path, 
            sep=';', 
            dtype=str, 
            chunksize=10000, 
            low_memory=False, 
            memory_map=True
        )
        
        total_processed = 0
        for chunk in reader:
            chunk.columns = chunk.columns.str.strip().str.upper()
            processed_count = logic_func(chunk)
            total_processed += processed_count
            
            # 3. Kosongkan session SQLAlchemy setiap kloter agar RAM tetap enteng
            db.session.commit()
            db.session.expunge_all() 

        return total_processed
    finally:
        # Hapus file sementara setelah selesai
        if os.path.exists(temp_path):
            os.remove(temp_path)

@importer_bp.route('/cid', methods=['POST'])
def import_cid():
    file = request.files.get('file')
    if not file: return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    try:
        def cid_logic(df):
            count = 0
            for _, row in df.iterrows():
                nomen = row.get('NOMEN')
                if not nomen: continue
                
                p = MasterPelanggan(
                    nomen=str(nomen).strip()[:8],
                    nama=row.get('JENIS_PELANGGAN', 'Pelanggan'),
                    pcez=row.get('PCEZBK'),
                    ab=row.get('CC', 'AB Sunter'),
                    tarif=row.get('TARIF'),
                    kelurahan=row.get('KELURAHAN') or row.get('KEL')
                )
                db.session.merge(p) # Merge: Update jika ada, Insert jika baru
                count += 1
            return count

        total = process_mega_file(file, cid_logic)
        return jsonify({"status": "success", "message": f"{total} Pelanggan Berhasil Disinkronkan"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    file = request.files.get('file')
    sumber = request.form.get('sumber', 'MC')
    
    try:
        def tagihan_logic(df):
            count = 0
            for _, row in df.iterrows():
                nomen = row.get('NOMEN')
                if not nomen: continue
                
                t = TransaksiTagihan(
                    nomen=str(nomen).strip()[:8],
                    nominal=float(row.get('TOTAL_TAGIHAN', 0)),
                    periode=extract_periode(row.get('PERIODE_DTTM')),
                    sumber=sumber
                )
                db.session.add(t)
                count += 1
            return count

        total = process_mega_file(file, tagihan_logic)
        return jsonify({"status": "success", "message": f"{total} Tagihan {sumber} Masuk Database"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/sbrs', methods=['POST'])
def import_sbrs():
    file = request.files.get('file')
    try:
        def sbrs_logic(df):
            count = 0
            for _, row in df.iterrows():
                nomen = row.get('NOMEN')
                if not nomen: continue
                
                m3 = int(row.get('KONSUMSI', 0))
                rata = 15 # Bisa disesuaikan logikanya
                kat = "NORMAL"
                if m3 == 0: kat = "ZERO"
                elif m3 > (rata * 2): kat = "EKSTREM"
                
                s = DataSBRS(
                    nomen=str(nomen).strip()[:8],
                    bulan_ini=m3,
                    rata_rata=rata,
                    stand_meter=int(row.get('END_READ_STAN', 0)),
                    kategori_anomali=kat
                )
                db.session.add(s)
                count += 1
            return count

        total = process_mega_file(file, sbrs_logic)
        return jsonify({"status": "success", "message": f"{total} Data SBRS Berhasil Dianalisa"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
