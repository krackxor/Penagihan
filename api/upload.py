"""
Upload API - Sunter Dashboard Pro (V3.0 Smart Autopilot)
Sinergi & Smart Update:
1. Auto-Clean IDPEL: Menangani otomatis format ilmiah (3.5E+08) & leading zeros.
2. Autopilot Rute: Deteksi kolom PCEZ & PETUGAS untuk pemetaan wilayah.
3. Collection Sync: Integrasi otomatis data pembayaran (MB) ke database piutang.
4. Smart Detection: Mengenali tipe file berdasarkan kata kunci kolom (Case-Insensitive).
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
    Contoh Input: '350960217' -> Output: ('096/02', '35')
    """
    if pd.isna(val) or str(val).strip() == '':
        return None, None
    
    digits = ''.join(filter(str.isdigit, str(val).strip()))
    
    if len(digits) >= 7:
        rayon = digits[:2]      # Rayon 34/35
        pce = digits[2:5]       # Kode PCE
        ez = digits[5:7]        # Kode EZ
        return f"{pce}/{ez}", rayon
    
    return str(val), "35"

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """
    Endpoint Unggahan Tunggal:
    Autopilot mendeteksi apakah file adalah MC (Tagihan), MB (Collection), 
    RUTE (Mapping), atau ARDEBT (Tunggakan).
    """
    
    # 1. VALIDASI AKSES
    if session.get('role') != 'admin':
        return jsonify({"error": "Akses Ditolak: Perlu Hak Akses Admin"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "File tidak ditemukan"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # 2. SMART LOADING (Data Sanitization)
        # dtype=str mencegah IDPEL berubah menjadi 3.5E+08
        df = pd.read_excel(file, dtype=str).fillna('')
        
        # Standarisasi Nama Kolom (Uppercase & Trim Spasi)
        df.columns = [str(c).upper().strip() for c in df.columns]
        cols = df.columns.tolist()

        # --- LOGIKA AUTOPILOT DETEKSI TIPE FILE ---
        file_type = None
        
        if 'PCEZ' in cols and 'PETUGAS' in cols:
            file_type = 'RUTE'
        elif 'ZONA_NOVAK' in cols and 'NAMA_PEL' in cols:
            file_type = 'MC'  # Master Catat (Tagihan Baru)
        elif 'TGL_BAYAR' in cols or 'PAY_DT' in cols:
            file_type = 'MB'  # Master Bayar (Collection)
        elif 'JUMLAH' in cols and 'PERIODE_BILL' in cols:
            file_type = 'ARDEBT'
        else:
            return jsonify({
                "error": "Struktur Excel tidak dikenal",
                "tips": "RUTE: Kolom 'PCEZ' & 'PETUGAS'. COLLECTION: Kolom 'TGL_BAYAR' & 'NOMEN'."
            }), 400

        row_count = 0
        current_month = datetime.now().strftime('%m-%Y')

        # 3. PEMROSESAN SINERGI BERDASARKAN TIPE
        
        # A. PROSES RUTE (Mapping Petugas)
        if file_type == 'RUTE':
            for _, row in df.iterrows():
                pcez = str(row.get('PCEZ')).strip()
                petugas = str(row.get('PETUGAS')).strip().upper()
                no_admin = str(row.get('NO_ADMIN', '628123456789')).replace('.0', '')
                
                if pcez and petugas:
                    db.execute("""
                        INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin) 
                        VALUES (?, ?, ?)
                    """, (pcez, petugas, no_admin))
                    row_count += 1

        # B. PROSES MC (Master Tagihan)
        elif file_type == 'MC':
            db.execute("DELETE FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'", (current_month,))
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                pcez, rayon = autopilot_extract_pcez(row.get('ZONA_NOVAK'))
                nom_raw = str(row.get('NOMINAL', 0)).replace(',', '').replace('.0', '')
                
                db.execute("""
                    INSERT INTO master_pelanggan 
                    (nomen, nama, pcez, rayon, nominal, volume, tipe, periode, is_high_value) 
                    VALUES (?, ?, ?, ?, ?, ?, 'MC', ?, ?)
                """, (nomen, row.get('NAMA_PEL'), pcez, rayon, float(nom_raw), 
                      row.get('KUBIK', 0), current_month, 1 if float(nom_raw) >= 300000 else 0))
                row_count += 1

        # C. PROSES MB (Master Bayar / Collection)
        elif file_type == 'MB':
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                # Cari kolom tgl bayar (mendukung beberapa variasi nama kolom)
                tgl = row.get('TGL_BAYAR') or row.get('PAY_DT')
                
                if nomen:
                    # Update status lunas di master tagihan secara otomatis (Sinergi)
                    db.execute("""
                        UPDATE master_pelanggan 
                        SET status_lunas = 1, tgl_lunas = ? 
                        WHERE nomen = ? AND periode = ?
                    """, (tgl, nomen, current_month))
                    
                    # Simpan ke history collection harian
                    nom_bayar = str(row.get('NOMINAL', 0)).replace(',', '').replace('.0', '')
                    db.execute("""
                        INSERT OR REPLACE INTO collection_harian (nomen, nominal, pay_dt, periode)
                        VALUES (?, ?, ?, ?)
                    """, (nomen, float(nom_bayar), tgl, current_month))
                    row_count += 1

        # 4. AUDIT TRAIL (Logging)
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, row_count, status) 
            VALUES (?, ?, ?, 'SUCCESS')
        """, (file.filename, file_type, row_count))

        db.commit()
        return jsonify({
            "status": "success",
            "message": f"Autopilot: {file_type} Berhasil Disinkronkan",
            "rows": row_count
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": f"Smart Logic Error: {str(e)}"}), 500
    finally:
        if db: db.close()
