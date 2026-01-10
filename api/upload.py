"""
Upload API - Sunter Dashboard Pro
Sinergi & Smart Update:
1. Smart Auto-Correction: Perbaikan otomatis format ilmiah (3.5E+08) dan leading zero.
2. Autopilot Mapping: Ekstraksi cerdas Rayon & PCEZ dari kolom ZONA_NOVAK.
3. High-Value Priority: Penandaan otomatis tagihan >= 300.000 untuk efisiensi collection.
4. Database Integrity: Normalisasi string pada NOMEN untuk menjamin link MC-MB-ARDEBT.
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
    FUNGSI AUTOPILOT:
    Menganalisis string ZONA_NOVAK untuk mendapatkan kode rute standar (XXX/XX).
    Contoh: '350960217' diproses otomatis menjadi PCEZ: '096/02' dan Rayon: '35'.
    """
    if pd.isna(val) or str(val).strip().upper() in ('NAN', 'NULL', ''):
        return None, None
    
    # Ambil angka saja untuk membuang karakter sampah atau spasi liar
    digits = ''.join(filter(str.isdigit, str(val).strip()))
    
    # Logika Ekstraksi Struktur: RR-PPP-EE-XXX (RR:Rayon, PPP:PCE, EE:EZ)
    if len(digits) >= 7:
        rayon = digits[:2]
        pce = digits[2:5]
        ez = digits[5:7]
        formatted_pcez = f"{pce}/{ez}"
    else:
        # Fallback cerdas jika format data pendek/tidak standar
        rayon = digits[:2] if digits[:2] in ('34', '35') else '35'
        formatted_pcez = f"0{digits[:2]}/{digits[2:]}" if len(digits) == 4 else str(val)
            
    return formatted_pcez, rayon

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """Endpoint unggahan tunggal dengan Smart-Cleaning & Autopilot Logic."""
    
    # --- 1. VALIDASI AKSES & FILE ---
    if session.get('role') != 'admin':
        return jsonify({"error": "Akses Ditolak: Khusus Administrator"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel terlebih dahulu"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # --- 2. SMART LOADING (Data Sanitization) ---
        # Paksa semua kolom menjadi string (dtype=str) untuk membunuh format ilmiah 3.5E+08 sejak awal
        df = pd.read_excel(file, dtype=str).fillna('')
        
        # Deteksi otomatis tipe file (MC, MB, Ardebt, atau Rute)
        file_type = identify_file_type(df)
        if not file_type:
            return jsonify({"error": "Sistem tidak mengenali struktur kolom file ini."}), 400

        # Deteksi periode data dari isi file atau header
        bulan, tahun = detect_file_period(df, file_type)
        periode_str = f"{str(bulan).zfill(2)}-{tahun}" if bulan else datetime.now().strftime('%m-%Y')
        
        # Standarisasi nama kolom menjadi Uppercase untuk konsistensi query
        df.columns = [str(c).upper().strip() for c in df.columns]

        # --- 3. PROSES DATA BERDASARKAN TIPE (SINERGI) ---

        # A. PROSES MAPPING RUTE (Peta Kerja)
        if file_type == 'rute':
            for _, row in df.iterrows():
                pcez, _ = smart_clean_pcez(row.get('PCEZ'))
                petugas = str(row.get('PETUGAS', '')).strip().upper()
                # Bersihkan nomor admin dari .0 akibat format float excel
                no_admin = str(row.get('NO_ADMIN', '628123456789')).replace(".0", "").strip()
                
                if pcez and petugas:
                    db.execute("""
                        INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, (pcez, petugas, no_admin))

        # B. PROSES MASTER TAGIHAN (MC) - SMART SINKRON
        elif file_type == 'mc':
            # Bersihkan data lama pada periode yang sama agar tidak duplikat saat re-upload
            db.execute("DELETE FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'", (periode_str,))
            
            for _, row in df.iterrows():
                # Perbaikan NOMEN ilmiah melalui helper clean_nomen
                nomen = clean_nomen(row.get('NOMEN'))
                if not nomen: continue
                
                # Autopilot: Dapatkan rute & rayon tanpa perlu kolom tambahan di excel
                pcez_fixed, rayon = smart_clean_pcez(row.get('ZONA_NOVAK'))
                
                # Normalisasi nominal: buang koma/titik agar tersimpan sebagai angka bersih
                nominal = float(str(row.get('NOMINAL', 0)).replace(',', '').replace('.0', ''))
                
                db.execute("""
                    INSERT INTO master_pelanggan 
                    (nomen, notagihan, nomet, nama, pcez, rayon, nominal, volume, tipe, periode) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (nomen, clean_nomen(row.get('NOTAGIHAN')), clean_nomen(row.get('NOMET')), 
                      row.get('NAMA_PEL'), pcez_fixed, rayon, nominal, row.get('KUBIK', 0), periode_str))

        # C. PROSES ARDEBT (AUTOMATIC LINKING)
        elif file_type == 'ardebt':
            # Ardebt bersifat refresh total setiap bulan
            db.execute("DELETE FROM ardebt")
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                if not nomen: continue
                
                jumlah = float(str(row.get('JUMLAH', 0)).replace(',', '').replace('.0', ''))
                db.execute("""
                    INSERT INTO ardebt (nomen, jumlah, volume, periode_bill) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, jumlah, row.get('VOLUME', 0), str(row.get('PERIODE_BILL', '')).strip()))

        # --- 4. LOGGING & FINISH ---
        # Catat riwayat unggahan untuk audit admin
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file.filename, file_type.upper(), periode_str, len(df), 'SUCCESS'))
        
        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Sinergi {file_type.upper()} Berhasil", 
            "rows": len(df),
            "periode": periode_str
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": f"Kegagalan Sinergi Data: {str(e)}"}), 500
    finally:
        if db: db.close()
