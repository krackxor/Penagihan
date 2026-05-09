import os
import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from models import db, MasterPelanggan, MasterPetugas, TransaksiTagihan

# Inisialisasi Blueprint untuk modul Importer
importer_bp = Blueprint('importer', __name__)

def clean_nomen(val):
    """Pastikan Nomen selalu string 8 digit bersih."""
    if pd.isna(val): return None
    s = str(val).strip()
    return s[:8]

@importer_bp.route('/cid', methods=['POST'])
def import_cid():
    """
    Fungsi Import Data Master Pelanggan (CID).
    Menangkap: NOMEN, NAMA, AB, RAYON, KELURAHAN, PCEZ, ALAMAT, TARIF, HP, WA, LAT, LONG.
    """
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    file = request.files['file']
    try:
        # Baca semua kolom sebagai string untuk keamanan data Nomen & PCEZ
        df = pd.read_excel(file, dtype=str)
        df.columns = df.columns.str.strip().str.upper() # Standarisasi Header

        count = 0
        for _, row in df.iterrows():
            nomen_bersih = clean_nomen(row.get('NOMEN'))
            if not nomen_bersih: continue

            # Gunakan db.session.merge agar data lama ter-update otomatis
            pelanggan = MasterPelanggan(
                nomen=nomen_bersih,
                nama=row.get('NAMA'),
                ab=row.get('AB', 'AB Sunter'),
                rayon=row.get('RAYON'),
                kelurahan=row.get('KELURAHAN') or row.get('KEL'),
                pcez=row.get('PCEZ'),
                alamat=row.get('ALAMAT'),
                tarif=row.get('TARIF'),
                hp=row.get('HP'),
                wa=row.get('WA'),
                latitude=float(row['LATITUDE']) if row.get('LATITUDE') else None,
                longitude=float(row['LONGITUDE']) if row.get('LONGITUDE') else None
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
    """
    Fungsi Import Master Petugas Berdasarkan Peran.
    Menghubungkan Kode PCEZ ke Nama Petugas (Tagihan/Catat/Anomali).
    Header: PCEZ, PETUGAS.
    """
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    # 1. Tangkap peran apa yang sedang di-upload oleh Admin
    peran_input = request.form.get('peran')
    if not peran_input:
        return jsonify({"status": "error", "message": "Peran petugas (TAGIHAN/CATAT/ANOMALI) harus dipilih!"}), 400

    file = request.files['file']
    try:
        df = pd.read_excel(file, dtype=str)
        df.columns = df.columns.str.strip().str.upper()

        count = 0
        for _, row in df.iterrows():
            kode_pcez = str(row.get('PCEZ', '')).strip()
            nama_petugas = row.get('PETUGAS') or row.get('NAMA_PETUGAS')
            
            if not kode_pcez or pd.isna(nama_petugas): continue

            # 2. Cek apakah PCEZ dengan PERAN tersebut sudah ada di database
            petugas = MasterPetugas.query.filter_by(pcez=kode_pcez, peran=peran_input).first()
            
            if petugas:
                # Jika sudah ada, cukup update namanya (misal Wahyu diganti Budi)
                petugas.nama_petugas = nama_petugas
            else:
                # Jika belum ada sama sekali, buat data baru
                petugas = MasterPetugas(
                    pcez=kode_pcez,
                    nama_petugas=nama_petugas,
                    peran=peran_input
                )
                db.session.add(petugas)
            
            count += 1

        db.session.commit()
        return jsonify({"status": "success", "message": f"{count} Data Petugas {peran_input} berhasil diperbarui"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    """
    Fungsi Import File Tagihan (MC atau ARDEBT).
    Header: NOMEN, NOMINAL, PERIODE.
    """
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    sumber = request.form.get('sumber', 'MC') # Default MC jika tidak dipilih
    file = request.files['file']
    
    try:
        df = pd.read_excel(file, dtype={'NOMEN': str})
        df.columns = df.columns.str.strip().str.upper()

        count = 0
        for _, row in df.iterrows():
            nomen_bersih = clean_nomen(row.get('NOMEN'))
            if not nomen_bersih: continue

            tagihan = TransaksiTagihan(
                nomen=nomen_bersih,
                nominal=float(row.get('NOMINAL', 0)),
                periode=str(row.get('PERIODE', '')),
                sumber=sumber,
                status_lunas=0
            )
            db.session.add(tagihan)
            count += 1

        db.session.commit()
        return jsonify({"status": "success", "message": f"{count} Data Tagihan {sumber} berhasil masuk"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
