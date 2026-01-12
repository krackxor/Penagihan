"""
Smart Integration Engine - Sunter Dashboard Pro (V9.5 Sinergi Global Sync)
Last Updated: 2026-01-12
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Rute Autonomous Logic: Bypass deteksi periode otomatis untuk modul RUTE.
2. CSV & Excel Compatibility: Mendukung pemrosesan cerdas untuk berbagai format file.
3. Multi-Layer Integrity: Validasi data di level engine sebelum masuk ke database.
4. Standardized API Response: Menjamin sinkronisasi UI tanpa 'undefined' errors.
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
    """Mesin pengolah data dengan validasi tipe data cerdas."""
    
    @staticmethod
    def cast_to_float(value):
        try:
            if pd.isna(value) or str(value).strip() == '':
                return 0.0
            return float(str(value).replace(',', '.'))
        except (ValueError, TypeError):
            return 0.0

@upload_bp.route('/upload', methods=['POST'])
def handle_smart_upload():
    """Endpoint integrasi masal dengan proteksi kegagalan sinkronisasi rute."""
    
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Access Denied: Admin Level Required"}), 403

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file stream detected"}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        # 1. CERDAS: Deteksi Format (CSV vs Excel)
        if file_name.endswith('.csv'):
            df = pd.read_csv(file, dtype=str).fillna('')
        else:
            df = pd.read_excel(file, dtype=str).fillna('')
            
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # 2. IDENTIFIKASI MODUL
        data_type = identify_file_type(df)
        if not data_type:
            return jsonify({"status": "error", "message": "Format Excel/CSV tidak dikenali"}), 400

        # 3. SMART PERIOD LOCKING (Fix: Gagal mendeteksi periode file)
        if data_type == 'RUTE':
            # Rute RL JS tidak mengandung tanggal, gunakan periode berjalan secara otomatis
            target_period = datetime.now().strftime('%m-%Y')
        else:
            # Modul transaksi (MC/MB/COLL) wajib deteksi dari isi file
            month, year = detect_file_period(df, data_type)
            if not month:
                return jsonify({"status": "error", "message": "Kegagalan deteksi periode operasional"}), 400
            target_period = f"{month}-{year}"

        row_count = 0

        # 4. BATCH PROCESSING (ATOMIC TRANSACTION)
        for _, row in df.iterrows():
            
            # Case RUTE: Mapping Administrasi (PCEZ -> PETUGAS)
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

            # Case TRANSACTIONAL: (MC, MB, COLL, ARDEBT)
            nomen = clean_nomen(row.get('NOMEN') or row.get('IDPEL'))
            if not nomen:
                continue

            if data_type == 'MC':
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
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, tgl_bayar, nominal, periode)
                    VALUES (?, ?, ?, ?)
                """, (nomen, row.get('TGL_BAYAR'), UploadEngine.cast_to_float(row['NOMINAL']), target_period))

            elif data_type == 'COLLECTION':
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, pay_dt, nominal, periode)
                    VALUES (?, ?, ?, ?)
                """, (nomen, row.get('PAY_DT'), UploadEngine.cast_to_float(row['NOMINAL']), target_period))

            elif data_type == 'ARDEBT':
                db.execute("""
                    INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, row['PERIODE_BILL'], UploadEngine.cast_to_float(row['JUMLAH']), 
                      UploadEngine.cast_to_float(row.get('VOLUME', 0))))

            row_count += 1

        # 5. AUDIT & LOGGING
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, data_type, target_period, row_count, 'SUCCESS'))

        db.commit()
        
        # 6. RESPONSE PROFESIONAL (Mencegah Undefined)
        return jsonify({
            "status": "success",
            "message": f"Sinkronisasi Modul {data_type} Berhasil",
            "metadata": {
                "rows": row_count,
                "period": target_period,
                "module": data_type
            }
        })

    except Exception as e:
        if db:
            db.rollback()
        current_app.logger.error(f"Integrity Error: {str(e)}")
        return jsonify({"status": "error", "message": f"Sistem Error: {str(e)}"}), 500
    finally:
        db.close()
