"""
Upload API - Sunter Dashboard Pro
Sinergi:
1. Smart Cleaning: Perbaikan otomatis format ilmiah (3.5E+08) dan leading zero pada NOMEN/PCEZ.
2. Auto-Logic: Mapping Rayon & PCEZ secara cerdas dari kolom ZONA_NOVAK.
3. Database Integrity: Menjamin relasi data antara MC, MB, dan Ardebt melalui normalisasi String.
"""

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, validate_periode
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def smart_clean_pcez(val):
    """
    SISTEM CERDAS:
    Mengambil kode PCEZ dari input acak dan menstandarisasi format (XXX/XX).
    Contoh: 350960217 (ZONA_NOVAK) -> PCEZ: 096/02, Rayon: 35
    """
    if pd.isna(val) or str(val).strip().upper() in ('NAN', 'NULL', ''):
        return None, None
    
    # Ambil angka saja untuk membuang karakter sampah
    digits = ''.join(filter(str.isdigit, str(val).strip()))
    
    if len(digits) < 4:
        return str(val), '35' # Fallback

    # Logika Ekstraksi dari ZONA_NOVAK (Format: RR-PPP-EE-XXX)
    # RR = Rayon, PPP = PCE, EE = EZ
    if len(digits) >= 7:
        rayon = digits[:2]
        pce = digits[2:5]
        ez = digits[5:7]
        formatted_pcez = f"{pce}/{ez}"
    else:
        # Fallback jika format pendek (misal 3401 -> 034/01)
        rayon = digits[:2] if digits[:2] in ('34', '35') else '35'
        formatted_pcez = f"0{digits[:2]}/{digits[2:]}" if len(digits) == 4 else str(val)
            
    return formatted_pcez, rayon

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """Endpoint unggahan tunggal dengan Smart-Cleaning (Admin Only)."""
    if session.get('role') != 'admin':
        return jsonify({"error": "Akses Ditolak"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "File tidak ditemukan"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # SMART LOAD: Paksa semua kolom jadi string untuk mencegah format ilmiah di awal
        df = pd.read_excel(file, dtype=str).fillna('')
        file_type = identify_file_type(df)
        
        if not file_type:
            return jsonify({"error": "Struktur kolom tidak dikenali"}), 400

        bulan, tahun = detect_file_period(df, file_type)
        periode_str = f"{str(bulan).zfill(2)}-{tahun}" if bulan else datetime.now().strftime('%m-%Y')
        
        df.columns = [str(c).upper().strip() for c in df.columns]

        # 1. PROSES MAPPING RUTE
        if file_type == 'rute':
            for _, row in df.iterrows():
                # Bersihkan PCEZ agar link ke MC tidak putus
                pcez, _ = smart_clean_pcez(row.get('PCEZ'))
                petugas = str(row.get('PETUGAS', '')).strip().upper()
                no_admin = str(row.get('NO_ADMIN', '628123456789')).replace(".0", "").strip()
                
                if pcez and petugas:
                    db.execute("""
                        INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, (pcez, petugas, no_admin))

        # 2. PROSES MASTER TAGIHAN (MC) - SMART SYNC
        elif file_type == 'mc':
            db.execute("DELETE FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'", (periode_str,))
            for _, row in df.iterrows():
                # Gunakan clean_nomen (helper) untuk perbaiki format ilmiah 3.5E+08
                nomen = clean_nomen(row.get('NOMEN'))
                if not nomen: continue
                
                # Ekstraksi otomatis PCEZ dan Rayon dari kolom ZONA_NOVAK
                pcez_fixed, rayon = smart_clean_pcez(row.get('ZONA_NOVAK'))
                
                # Normalisasi nominal uang (hilangkan koma/titik)
                nominal = float(str(row.get('NOMINAL', 0)).replace(',', ''))
                
                db.execute("""
                    INSERT INTO master_pelanggan 
                    (nomen, notagihan, nomet, nama, pcez, rayon, nominal, volume, tipe, periode) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (nomen, clean_nomen(row.get('NOTAGIHAN')), clean_nomen(row.get('NOMET')), 
                      row.get('NAMA_PEL'), pcez_fixed, rayon, nominal, row.get('KUBIK', 0), periode_str))

        # 3. PROSES DATA ARDEBT (AUTO-LINK)
        elif file_type == 'ardebt':
            db.execute("DELETE FROM ardebt")
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                if not nomen: continue
                
                jumlah = float(str(row.get('JUMLAH', 0)).replace(',', ''))
                db.execute("""
                    INSERT INTO ardebt (nomen, jumlah, volume, periode_bill) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, jumlah, row.get('VOLUME', 0), str(row.get('PERIODE_BILL', '')).strip()))

        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file.filename, file_type.upper(), periode_str, len(df), 'SUCCESS'))
        
        db.commit()
        return jsonify({"status": "success", "message": f"Sinergi {file_type.upper()} Berhasil", "rows": len(df)})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": f"Sistem Gagal Sinkron: {str(e)}"}), 500
    finally:
        if db: db.close()
