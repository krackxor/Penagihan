"""
Upload API - Sunter Dashboard Pro (V8.5 Sinergi Global Sync)
Update: 2026-01-12
- Global Locking: Mengunci satu periode untuk seluruh isi file (Anti-Januari).
- N+1 Logic: MC/MB/Ardebt bulan N -> Periode N+1.
- Collection Sync: Collection bulan N -> Periode N.
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, clean_notag
# Menggunakan auto_detect yang sudah diperbaiki
from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona

upload_bp = Blueprint('upload', __name__)

# Konfigurasi kolom wajib
REQUIRED_COLS = {
    'MC': ['NOMEN', 'NAMA_PEL', 'ZONA_NOVAK', 'TGL_CATAT', 'NOMINAL'],
    'MB': ['NOMEN', 'TGL_BAYAR', 'NOMINAL'],
    'ARDEBT': ['NOMEN', 'PERIODE_BILL', 'JUMLAH'],
    'COLLECTION': ['NOMEN', 'PAY_DT', 'NOMINAL'],
    'RUTE': ['PCEZ', 'PETUGAS']
}

def safe_float(val):
    """Data Guard: Memastikan angka desimal Excel terbaca benar."""
    try:
        if pd.isna(val) or str(val).strip() == '': return 0.0
        return float(str(val).replace(',', '.'))
    except: return 0.0

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if session.get('role') != 'admin':
        return jsonify({"error": "Access Denied"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "No file detected"}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        # Membaca data dengan tipe string untuk menjaga integritas Nomen
        df = pd.read_excel(file, dtype=str).fillna('')
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # 1. Identifikasi Tipe & DETEKSI PERIODE GLOBAL (Kunci Anti-Januari)
        file_type = identify_file_type(df) #
        if not file_type:
            return jsonify({"error": "Format Excel tidak dikenali"}), 400

        # KUNCI PERIODE DI SINI (Hanya 1x deteksi untuk seluruh file)
        t_month, t_year = detect_file_period(df, file_type) #
        if not t_month:
            return jsonify({"error": "Gagal mendeteksi periode file"}), 400
            
        periode_fix = f"{t_month}-{t_year}" # Contoh: 12-2025
        row_count = 0

        # 2. PROSES INSERT (Menggunakan periode_fix untuk SEMUA baris)
        for _, r in df.iterrows():
            nomen = clean_nomen(r.get('NOMEN') or r.get('IDPEL')) #
            if not nomen: continue

            if file_type == 'MC':
                z = autopilot_extract_zona(r['ZONA_NOVAK']) #
                if not z: continue
                
                db.execute("""
                    INSERT OR REPLACE INTO master_pelanggan 
                    (nomen, nama, alamat, pcez, rayon, pc, ez, blok, nominal, nomet, periode, status_lunas)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,0)
                """, (nomen, r.get('NAMA_PEL'), r.get('ALM1_PEL'), z['pcez'], z['rayon'], 
                      z['pc'], z['ez'], z['blok'], safe_float(r['NOMINAL']), 
                      r.get('NOMET'), periode_fix))

            elif file_type == 'MB':
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, tgl_bayar, nominal, periode)
                    VALUES (?, ?, ?, ?)
                """, (nomen, r.get('TGL_BAYAR'), safe_float(r['NOMINAL']), periode_fix))

            elif file_type == 'COLLECTION':
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, pay_dt, nominal, periode)
                    VALUES (?, ?, ?, ?)
                """, (nomen, r.get('PAY_DT'), safe_float(r['NOMINAL']), periode_fix))

            elif file_type == 'ARDEBT':
                db.execute("""
                    INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, r['PERIODE_BILL'], safe_float(r['JUMLAH']), safe_float(r.get('VOLUME', 0))))

            row_count += 1

        # 3. AUDIT HISTORY
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, file_type, periode_fix, row_count, 'SUCCESS'))

        db.commit()
        return jsonify({"status": "success", "rows": row_count, "period": periode_fix})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
