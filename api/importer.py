import pandas as pd
import io
from flask import Blueprint, request, jsonify
from models import db, MasterPelanggan, MasterPetugas, TransaksiTagihan, DataSBRS

importer_bp = Blueprint('importer', __name__)

def read_any_file(file):
    """
    Fungsi cerdas untuk membaca Excel atau Teks (Semicolon ;).
    Mendukung format export sistem PAM Jaya.
    """
    filename = file.filename.lower()
    file_bytes = file.read() # Baca file ke memori
    
    try:
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            return pd.read_excel(io.BytesIO(file_bytes), dtype=str)
        else:
            # Otomatis deteksi Semicolon (;) untuk file .txt / .csv
            return pd.read_csv(io.BytesIO(file_bytes), sep=';', dtype=str, quotechar='"')
    except Exception as e:
        raise ValueError(f"Gagal membaca file: {str(e)}")

def extract_periode(val):
    """Konversi format '01-Apr-26' menjadi '202604'"""
    try:
        if not val or pd.isna(val): return "202601"
        dt = pd.to_datetime(val)
        return dt.strftime('%Y%m')
    except:
        return str(val)[:6]

@importer_bp.route('/cid', methods=['POST'])
def import_cid():
    file = request.files.get('file')
    if not file: return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    try:
        df = read_any_file(file)
        df.columns = df.columns.str.strip().str.upper()
        count = 0
        for _, row in df.iterrows():
            nomen = row.get('NOMEN')
            if not nomen: continue

            # Mapping khusus format file Bos (PCEZBK -> pcez)
            pelanggan = MasterPelanggan(
                nomen=str(nomen).strip()[:8],
                nama=row.get('JENIS_PELANGGAN', 'Pelanggan'),
                pcez=row.get('PCEZBK'),
                ab=row.get('CC', 'AB Sunter'),
                tarif=row.get('TARIF'),
                kelurahan=row.get('KELURAHAN') or row.get('KEL')
            )
            db.session.merge(pelanggan)
            count += 1
        
        db.session.commit()
        return jsonify({"status": "success", "message": f"{count} Data CID berhasil disinkronisasi"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/petugas', methods=['POST'])
def import_petugas():
    peran_input = request.form.get('peran')
    if not peran_input:
        return jsonify({"status": "error", "message": "Pilih peran petugas!"}), 400

    file = request.files.get('file')
    try:
        df = read_any_file(file)
        df.columns = df.columns.str.strip().str.upper()
        count = 0
        for _, row in df.iterrows():
            kode_pcez = str(row.get('PCEZ', row.get('PCEZBK', ''))).strip()
            nama = row.get('PETUGAS') or row.get('NAMA_PETUGAS')
            
            if not kode_pcez or not nama: continue

            petugas = MasterPetugas.query.filter_by(pcez=kode_pcez, peran=peran_input).first()
            if petugas:
                petugas.nama_petugas = nama
            else:
                petugas = MasterPetugas(pcez=kode_pcez, nama_petugas=nama, peran=peran_input)
                db.session.add(petugas)
            count += 1

        db.session.commit()
        return jsonify({"status": "success", "message": f"{count} Petugas {peran_input} diperbarui"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    """Import untuk MC (Berjalan) dan MB (Ekor/Tunggakan)"""
    file = request.files.get('file')
    sumber = request.form.get('sumber', 'MC')
    
    try:
        df = read_any_file(file)
        df.columns = df.columns.str.strip().str.upper()
        count = 0
        for _, row in df.iterrows():
            nomen = row.get('NOMEN')
            if not nomen: continue

            # Ambil nominal dari TOTAL_TAGIHAN (format file Bos)
            tagihan = TransaksiTagihan(
                nomen=str(nomen).strip()[:8],
                nominal=float(row.get('TOTAL_TAGIHAN', 0)),
                periode=extract_periode(row.get('PERIODE_DTTM')),
                sumber=sumber
            )
            db.session.add(tagihan)
            count += 1

        db.session.commit()
        return jsonify({"status": "success", "message": f"{count} Tagihan {sumber} berhasil masuk"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/sbrs', methods=['POST'])
def import_sbrs():
    """Import untuk Analisa SBRS"""
    file = request.files.get('file')
    try:
        df = read_any_file(file)
        df.columns = df.columns.str.strip().str.upper()
        count = 0
        for _, row in df.iterrows():
            nomen = row.get('NOMEN')
            if not nomen: continue

            m3_ini = int(row.get('KONSUMSI', 0))
            rata = 15 # Default rata-rata, bisa diganti sesuai file

            kat = "NORMAL"
            if m3_ini == 0: kat = "ZERO"
            elif m3_ini > (rata * 2): kat = "EKSTREM"
            elif m3_ini < (rata * 0.5): kat = "TURUN"

            sbrs = DataSBRS(
                nomen=str(nomen).strip()[:8],
                bulan_ini=m3_ini,
                rata_rata=rata,
                stand_meter=int(row.get('END_READ_STAN', 0)),
                kategori_anomali=kat
            )
            db.session.add(sbrs)
            count += 1

        db.session.commit()
        return jsonify({"status": "success", "message": f"{count} Data SBRS berhasil dianalisa"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
