"""
Upload API - Sunter Dashboard Pro (V2 Smart Edition)
Sinergi & Smart Update:
1. Auto-Clean IDPEL: Menangani otomatis format ilmiah (3.5E+08) & leading zeros.
2. Autopilot Rute: Ekstraksi cerdas Rayon (34/35) dari data ZONA_NOVAK.
3. Ardebt Sinergi: Penghitungan otomatis akumulasi tunggakan lama.
4. Database Integrity: Menjamin sinkronisasi MC (Tagihan) dan MB (Lunas) via Nomen.
"""

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, validate_periode

upload_bp = Blueprint('upload', __name__)

def autopilot_extract_pcez(val):
    """
    FUNGSI AUTOPILOT:
    Menganalisis string ZONA_NOVAK untuk mendapatkan kode rute standar (XXX/XX).
    Sinergi: Otomatis memisahkan Rayon dan Rute Kerja.
    Contoh Input: '350960217' -> Output: ('096/02', '35')
    """
    if pd.isna(val) or str(val).strip() == '':
        return None, None
    
    # Buang karakter non-digit (Autopilot Cleaning)
    digits = ''.join(filter(str.isdigit, str(val).strip()))
    
    if len(digits) >= 7:
        rayon = digits[:2]      # Dua digit pertama (Rayon 34/35)
        pce = digits[2:5]        # PCE (096)
        ez = digits[5:7]         # EZ (02)
        formatted_pcez = f"{pce}/{ez}"
        return formatted_pcez, rayon
    
    # Fallback jika data tidak standar
    return str(val), "35"

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """
    Endpoint Unggahan Tunggal:
    Mendeteksi otomatis apakah file yang diupload adalah MC, MB, atau Ardebt.
    """
    
    # 1. VALIDASI KEAMANAN (Sinergi Role Admin)
    if session.get('role') != 'admin':
        return jsonify({"error": "Akses Ditolak: Perlu Hak Akses Admin"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "File tidak ditemukan"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # 2. SMART LOADING (Data Sanitization)
        # dtype=str memastikan IDPEL tidak berubah menjadi format Scientific (E+)
        df = pd.read_excel(file, dtype=str).fillna('')
        df.columns = [str(c).upper().strip() for c in df.columns]

        # Logika Autopilot: Deteksi Tipe File berdasarkan header kolom
        if 'ZONA_NOVAK' in df.columns and 'NAMA_PEL' in df.columns:
            file_type = 'MC' # Master Catat (Tagihan)
        elif 'TGL_BAYAR' in df.columns:
            file_type = 'MB' # Master Bayar (Lunas)
        elif 'JUMLAH' in df.columns and 'PERIODE_BILL' in df.columns:
            file_type = 'ARDEBT' # Tunggakan Lama
        else:
            return jsonify({"error": "Struktur Excel tidak dikenal"}), 400

        # 3. PEMROSESAN DATA (SINERGI DATABASE)
        row_count = 0
        current_month = datetime.now().strftime('%m-%Y')

        # A. PROSES MC (MASTER TAGIHAN)
        if file_type == 'MC':
            # Bersihkan periode ini sebelum timpa data baru (Autopilot Reset)
            db.execute("DELETE FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'", (current_month,))
            
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN')) # Perbaikan format IDPEL
                pcez, rayon = autopilot_extract_pcez(row.get('ZONA_NOVAK'))
                
                # Sinergi Nominal: Bersihkan format ribuan
                nom_raw = str(row.get('NOMINAL', 0)).replace(',', '').replace('.0', '')
                
                db.execute("""
                    INSERT INTO master_pelanggan 
                    (nomen, nama, pcez, rayon, nominal, volume, tipe, periode, is_high_value) 
                    VALUES (?, ?, ?, ?, ?, ?, 'MC', ?, ?)
                """, (
                    nomen, row.get('NAMA_PEL'), pcez, rayon, 
                    float(nom_raw), row.get('KUBIK', 0), 
                    current_month,
                    1 if float(nom_raw) >= 300000 else 0 # Smart High-Value Tagging
                ))
                row_count += 1

        # B. PROSES MB (MASTER BAYAR / LUNAS)
        elif file_type == 'MB':
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                if nomen:
                    # Update status lunas pada master_pelanggan (Sinergi Link)
                    db.execute("""
                        UPDATE master_pelanggan 
                        SET status_lunas = 1, tgl_lunas = ? 
                        WHERE nomen = ? AND periode = ?
                    """, (row.get('TGL_BAYAR'), nomen, current_month))
                    row_count += 1

        # C. PROSES ARDEBT (TUNGGAKAN LAMA)
        elif file_type == 'ARDEBT':
            # Ardebt direfresh total setiap kali upload
            db.execute("DELETE FROM ardebt")
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                db.execute("""
                    INSERT INTO ardebt (nomen, jumlah, volume, periode_bill) 
                    VALUES (?, ?, ?, ?)
                """, (
                    nomen, float(str(row.get('JUMLAH')).replace(',', '')), 
                    row.get('VOLUME', 0), row.get('PERIODE_BILL')
                ))
                row_count += 1

        # 4. LOGGING AKTIVITAS (Audit Admin)
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, row_count, status) 
            VALUES (?, ?, ?, 'SUCCESS')
        """, (file.filename, file_type, row_count))

        db.commit()
        return jsonify({
            "status": "success",
            "message": f"Sinkronisasi {file_type} Berhasil",
            "processed_rows": row_count
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": f"Smart Logic Error: {str(e)}"}), 500
    finally:
        if db: db.close()
