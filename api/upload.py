"""
Upload API - Sunter Dashboard Pro (V8.6 Sinergi Global Sync)
Update: 2026-01-12
- Global Locking: Mengunci satu periode untuk seluruh isi file (Anti-Januari).
- N+1 Logic: MC/MB/Ardebt bulan N -> Periode N+1.
- Collection Sync: Collection bulan N -> Periode N.
- UI Fix: Mengirimkan identitas modul untuk menghilangkan pesan 'undefined'.
- Rute Fix: Bypass deteksi periode untuk file RUTE agar tidak gagal sinkronisasi.
"""

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen
from processors.auto_detect import identify_file_type, detect_file_period, autopilot_extract_zona

upload_bp = Blueprint('upload', __name__)

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
        
        # 1. Identifikasi Tipe File
        file_type = identify_file_type(df)
        if not file_type:
            return jsonify({"error": "Format Excel tidak dikenali"}), 400

        # 2. DETEKSI PERIODE GLOBAL (Bypass untuk RUTE)
        if file_type == 'RUTE':
            # Rute tidak memiliki kolom tanggal, gunakan periode sistem saat ini
            t_month = datetime.now().strftime('%m')
            t_year = datetime.now().strftime('%Y')
        else:
            t_month, t_year = detect_file_period(df, file_type)
            if not t_month:
                return jsonify({"error": "Gagal mendeteksi periode file"}), 400
            
        periode_fix = f"{t_month}-{t_year}"
        row_count = 0

        # 3. PROSES INSERT
        for _, r in df.iterrows():
            # Khusus RUTE, menggunakan join key PCEZ (bukan NOMEN)
            if file_type == 'RUTE':
                pcez_val = str(r.get('PCEZ', '')).strip()
                petugas_val = str(r.get('PETUGAS', '')).strip()
                if pcez_val and petugas_val:
                    db.execute("""
                        INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (pcez_val, petugas_val))
                    row_count += 1
                continue

            # Proses untuk tipe data transaksional (MC, MB, COLL, ARDEBT)
            nomen = clean_nomen(r.get('NOMEN') or r.get('IDPEL'))
            if not nomen: continue

            if file_type == 'MC':
                z = autopilot_extract_zona(r['ZONA_NOVAK'])
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

        # 4. AUDIT HISTORY
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, file_type, periode_fix, row_count, 'SUCCESS'))

        db.commit()
        
        return jsonify({
            "status": "success", 
            "rows": row_count, 
            "period": periode_fix,
            "module": file_type 
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
