"""
Core Upload Engine - Sunter Dashboard Pro (V9.0 Global Sync & Smart Integration)
Last Updated: 2026-01-12
---------------------------------------------------------------------------
Key Features:
- Autonomous Data Detection: Identifikasi otomatis jenis data & periode.
- Sinergi N+1 Integrity: Sinkronisasi otomatis target penagihan & realisasi.
- Global Locking Mechanism: Konsistensi periode tunggal per transaksi unggah.
- Operational Guard: Bypass cerdas untuk modul RUTE & proteksi data NULL.
"""

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from core.helpers import clean_nomen
from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    """Helper class untuk manajemen validasi dan pemrosesan data."""
    
    @staticmethod
    def cast_to_float(value):
        """Mengamankan konversi angka desimal dari berbagai format Excel."""
        try:
            if pd.isna(value) or str(value).strip() == '':
                return 0.0
            return float(str(value).replace(',', '.'))
        except (ValueError, TypeError):
            return 0.0

@upload_bp.route('/upload', methods=['POST'])
def handle_smart_upload():
    """Endpoint utama untuk integrasi data masal dengan validasi cerdas."""
    
    # [1] Security Verification
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Privilege Required"}), 403

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No stream detected"}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        # [2] Pre-Processing: Load & Normalize
        # Menggunakan dtype=str untuk mencegah truncating pada ID Pelanggan (Nomen)
        df = pd.read_excel(file, dtype=str).fillna('')
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # [3] Smart Identification
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Unrecognized Excel Schema"}), 400

        # [4] Temporal Synchronization (Global Period Locking)
        if data_type == 'RUTE':
            # Modul administratif (RUTE) menggunakan periode server berjalan
            target_period = datetime.now().strftime('%m-%Y')
        else:
            # Modul transaksional diekstraksi berdasarkan data baris pertama
            month, year = detect_file_period(df, data_type)
            if not month:
                return jsonify({"status": "error", "message": "Temporal Detection Failed"}), 400
            target_period = f"{month}-{year}"

        row_count = 0

        # [5] Batch Atomic Operation (Transaction)
        for _, row in df.iterrows():
            
            # Case A: Administrative Mapping (RUTE)
            if data_type == 'RUTE':
                pcez = str(row.get('PCEZ', '')).strip()
                petugas = str(row.get('PETUGAS', '')).strip()
                if pcez and petugas:
                    db.execute("""
                        INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (pcez, petugas))
                    row_count += 1
                continue

            # Case B: Transactional Data (Nomen-Based)
            nomen = clean_nomen(row.get('NOMEN') or row.get('IDPEL'))
            if not nomen:
                continue

            if data_type == 'MC':
                # Sinergi N+1: Master Pelanggan Target
                zona = autopilot_extract_zona(row['ZONA_NOVAK'])
                if zona:
                    db.execute("""
                        INSERT OR REPLACE INTO master_pelanggan 
                        (nomen, nama, alamat, pcez, rayon, pc, ez, blok, nominal, nomet, periode, status_lunas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (nomen, row.get('NAMA_PEL'), row.get('ALM1_PEL'), zona['pcez'], zona['rayon'], 
                          zona['pc'], zona['ez'], zona['blok'], UploadEngine.cast_to_float(row['NOMINAL']), 
                          row.get('NOMET'), target_period))

            elif data_type == 'MB':
                # Sinergi Realisasi: Master Bayar (Bank/Kantor)
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, tgl_bayar, nominal, periode)
                    VALUES (?, ?, ?, ?)
                """, (nomen, row.get('TGL_BAYAR'), UploadEngine.cast_to_float(row['NOMINAL']), target_period))

            elif data_type == 'COLLECTION':
                # Sinergi Realisasi: Collection Lapangan (Current)
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, pay_dt, nominal, periode)
                    VALUES (?, ?, ?, ?)
                """, (nomen, row.get('PAY_DT'), UploadEngine.cast_to_float(row['NOMINAL']), target_period))

            elif data_type == 'ARDEBT':
                # Legacy Data: Penanganan Tunggakan Berekor
                db.execute("""
                    INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, row['PERIODE_BILL'], UploadEngine.cast_to_float(row['JUMLAH']), 
                      UploadEngine.cast_to_float(row.get('VOLUME', 0))))

            row_count += 1

        # [6] Operational Audit Trail
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, data_type, target_period, row_count, 'SUCCESS'))

        db.commit()
        
        # [7] Standardized Response Object
        return jsonify({
            "status": "success",
            "message": f"Integration Complete: {data_type} synchronized",
            "metadata": {
                "rows_processed": row_count,
                "target_period": target_period,
                "module": data_type
            }
        })

    except Exception as e:
        if db:
            db.rollback()
        current_app.logger.error(f"Integrity Error during upload: {str(e)}")
        return jsonify({"status": "error", "message": "Database Integrity Violation"}), 500
    finally:
        db.close()
