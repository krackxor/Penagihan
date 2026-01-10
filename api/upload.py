"""
Upload API - Sunter Dashboard Pro (V3.7 Sinergi Strict Edition)
Sinergi & Smart Update:
1. Strict Validation: Wajib menyertakan kolom spesifik (NAMA_PEL, ALM, PAY_DT, dll).
2. ZONA_NOVAK Intelligence: Ekstraksi otomatis Rayon, PC, EZ, PCEZ, dan Blok.
3. Collection Full Sync: Menyimpan seluruh data penagihan lapangan secara lengkap.
4. Maintenance Friendly: Komentar detail di setiap fungsi untuk kemudahan edit.
"""

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen

upload_bp = Blueprint('upload', __name__)

# --- KONFIGURASI KOLOM WAJIB (STRICT CONTROL) ---
# Daftar kolom ini harus ada di file Excel agar sistem mau memproses data.
REQUIRED_COLS = {
    'MC': [
        'NOMEN', 'NAMA_PEL', 'ALM1_PEL', 'ALM2_PEL', 'ALM3_PEL', 'KD_POS', 
        'ZONA_NOVAK', 'NOTAGIHAN', 'NOMET', 'TARIF', 'TGL_CATAT', 
        'STAN_AWAL', 'STAN_AKIR', 'KUBIK', 'NOMINAL', 'CUST_TYPE'
    ],
    'MB': ['NOMEN', 'BULAN_REK', 'NOTAGIHAN', 'TGL_BAYAR', 'NOMINAL'],
    'ARDEBT': ['NOMEN', 'PERIODE_BILL', 'JUMLAH', 'VOLUME'],
    'COLLECTION': [
        'NOMEN', 'NOTAG', 'BILL_PERIOD', 'BILL_REASON', 
        'NOMINAL', 'PAY_DT', 'FREEZE_DTTM', 'VOL_COLLECT'
    ],
    'RUTE': ['PCEZ', 'PETUGAS']
}

def autopilot_extract_zona(val):
    """
    FUNGSI: Membedah string ZONA_NOVAK (Contoh: 350960217).
    LOGIKA EKSTRAKSI:
    - RAYON (2 digit): 35
    - PC (3 digit): 096
    - EZ (2 digit): 02
    - PCEZ (Format PC/EZ): 096/02
    - BLOK (2 digit): 17
    """
    if pd.isna(val) or str(val).strip() == '':
        return None

    # Bersihkan dari desimal .0 dan ambil angka saja
    s = str(val).strip().split('.')[0]
    s = ''.join(filter(str.isdigit, s))
    
    # Pastikan panjang string minimal 9 digit (Gunakan Padding 0 di depan jika kurang)
    s = s.zfill(9)
    
    return {
        'rayon': s[0:2],              # Digit 1-2
        'pc': s[2:5],                 # Digit 3-5
        'ez': s[5:7],                 # Digit 6-7
        'pcez': f"{s[2:5]}/{s[5:7]}", # Gabungan PC/EZ (XXX/XX)
        'blok': s[7:9]                # Digit 8-9 (2 Terakhir)
    }

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """
    ENDPOINT UTAMA: Mengolah file Excel dan menyimpannya ke database sesuai tipe.
    ALUR: Validasi Role -> Identifikasi Kolom -> Eksekusi Simpan -> Logging.
    """
    
    # --- 1. VALIDASI AKSES ADMIN ---
    if session.get('role') != 'admin':
        return jsonify({"error": "Akses Ditolak: Hanya Admin yang bisa upload data."}), 403

    if 'file' not in request.files:
        return jsonify({"error": "Sistem tidak mendeteksi adanya file."}), 400
    
    file = request.files['file']
    db = get_db_connection()
    
    try:
        # --- 2. PEMBACAAN EXCEL DENGAN PROTEKSI IDPEL ---
        # dtype=str menjaga agar NOMEN (IDPEL) tidak rusak (misal 001 jadi 1)
        df = pd.read_excel(file, dtype=str).fillna('')
        
        # Standarisasi Nama Kolom (Huruf Besar & Hilangkan Spasi)
        df.columns = [str(c).upper().strip() for c in df.columns]
        cols = df.columns.tolist()

        # --- 3. IDENTIFIKASI TIPE FILE BERDASARKAN KOLOM WAJIB (STRICT) ---
        file_type = None
        for t, required in REQUIRED_COLS.items():
            if all(k in cols for k in required):
                file_type = t
                break

        if not file_type:
            return jsonify({
                "error": "Kolom Wajib Tidak Lengkap!",
                "detail": "Pastikan header Excel Anda sesuai dengan spesifikasi sistem."
            }), 400

        row_count = 0
        current_month = datetime.now().strftime('%m-%Y')

        # --- 4. PEMROSESAN DATA BERDASARKAN TIPE ---

        # A. PROSES MC (MASTER CATAT / DATA TARGET)
        if file_type == 'MC':
            # Bersihkan data lama pada periode berjalan agar tidak duplikat
            db.execute("DELETE FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'", (current_month,))
            
            for _, r in df.iterrows():
                # Jalankan intelijen ekstraksi ZONA_NOVAK
                zona = autopilot_extract_zona(r['ZONA_NOVAK'])
                if not zona: continue
                
                # Penggabungan alamat 3 baris
                full_address = f"{r['ALM1_PEL']} {r['ALM2_PEL']} {r['ALM3_PEL']}".strip()
                
                db.execute("""
                    INSERT INTO master_pelanggan (
                        nomen, nama, alamat, kd_pos, pcez, rayon, pc, ez, blok, 
                        notagihan, nomet, tarif, tgl_catat, stan_awal, stan_akir, 
                        kubik, nominal, cust_type, tipe, periode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (
                    clean_nomen(r['NOMEN']), r['NAMA_PEL'], full_address, r['KD_POS'],
                    zona['pcez'], zona['rayon'], zona['pc'], zona['ez'], zona['blok'],
                    r['NOTAGIHAN'], r['NOMET'], r['TARIF'], r['TGL_CATAT'],
                    r['STAN_AWAL'], r['STAN_AKIR'], float(str(r['KUBIK']).replace(',', '')),
                    float(str(r['NOMINAL']).replace(',', '')), r['CUST_TYPE'], current_month
                ))
                row_count += 1

        # B. PROSES MB (MASTER BAYAR / LUNAS KANTOR)
        elif file_type == 'MB':
            for _, r in df.iterrows():
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, bulan_rek, notagihan, tgl_bayar, nominal, periode)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), r['BULAN_REK'], r['NOTAGIHAN'], r['TGL_BAYAR'], r['NOMINAL'], current_month))
                row_count += 1

        # C. PROSES ARDEBT (TUNGGAKAN PIUTANG LAMA)
        elif file_type == 'ARDEBT':
            # Data Ardebt di-reset setiap upload karena bersifat data status terbaru
            db.execute("DELETE FROM ardebt")
            for _, r in df.iterrows():
                db.execute("""
                    INSERT INTO ardebt (nomen, periode_bill, jumlah, volume)
                    VALUES (?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), r['PERIODE_BILL'], float(r['JUMLAH']), float(r['VOLUME'])))
                row_count += 1

        # D. PROSES COLLECTION (FULL SYNC - PENAGIHAN LAPANGAN)
        elif file_type == 'COLLECTION':
            for _, r in df.iterrows():
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (
                        nomen, notag, bill_period, bill_reason, nominal, pay_dt, 
                        freeze_dttm, vol_collect, periode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    clean_nomen(r['NOMEN']), r['NOTAG'], r['BILL_PERIOD'], r['BILL_REASON'],
                    float(r['NOMINAL']), r['PAY_DT'], r['FREEZE_DTTM'], r['VOL_COLLECT'], current_month
                ))
                row_count += 1

        # E. PROSES RUTE (MAPPING PETUGAS)
        elif file_type == 'RUTE':
            for _, r in df.iterrows():
                db.execute("""
                    INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (r['PCEZ'].strip(), r['PETUGAS'].upper().strip()))
                row_count += 1

        # --- 5. LOGGING AKTIVITAS (AUDIT TRAIL) ---
        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Sinergi {file_type} Berhasil!", 
            "rows": row_count
        })

    except Exception as e:
        if db: db.rollback()
        print(f"ERROR UPLOAD: {str(e)}")
        return jsonify({"error": f"Kegagalan Sistem: {str(e)}"}), 500
    finally:
        if db: db.close()
