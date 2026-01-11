"""
Upload API - Sunter Dashboard Pro (V4.7 Sinergi Intelligence)
Sinergi & Smart Update:
1. Float Guard: Otomatis menangani sel Excel kosong ('') menjadi angka 0 agar tidak error.
2. Strict Validation: Wajib menyertakan kolom spesifik untuk MC, MB, ARDEBT, RUTE, dan COLLECTION.
3. ZONA_NOVAK Intelligence: Ekstraksi otomatis Rayon, PC, EZ, PCEZ, dan Blok.
4. Audit Trail Integrity: Mencatat log sukses/gagal ke tabel upload_history untuk audit Admin.
"""

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen

upload_bp = Blueprint('upload', __name__)

# =========================================================================
# 1. KONFIGURASI KOLOM WAJIB (STRICT CONTROL)
# =========================================================================
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
    'RUTE': ['PCEZ', 'PETUGAS'] # Sinergi V4.7: Bisa ditambahkan NO_ADMIN di Excel
}

# =========================================================================
# 2. FUNGSI PEMBANTU (HELPER FUNCTIONS)
# =========================================================================

def safe_float(val):
    """ Mengonversi data Excel menjadi angka aman (Float Guard). """
    try:
        if pd.isna(val) or str(val).strip() == '':
            return 0.0
        clean_val = str(val).replace('.', '').replace(',', '.')
        return float(clean_val)
    except (ValueError, TypeError):
        return 0.0

def autopilot_extract_zona(val):
    """ Membedah string ZONA_NOVAK menjadi komponen rute. """
    if pd.isna(val) or str(val).strip() == '':
        return None
    s = ''.join(filter(str.isdigit, str(val).split('.')[0])).zfill(9)
    return {
        'rayon': s[0:2],
        'pc': s[2:5],
        'ez': s[5:7],
        'pcez': f"{s[2:5]}/{s[5:7]}",
        'blok': s[7:9]
    }

# =========================================================================
# 3. ROUTE UTAMA (UPLOAD HANDLER)
# =========================================================================

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """ 
    ENDPOINT: Memproses file Excel dan mendistribusikannya ke database. 
    V4.7: Menambahkan pencatatan riwayat otomatis ke tabel upload_history.
    """
    if session.get('role') != 'admin':
        return jsonify({"error": "Akses Ditolak: Hanya Admin yang bisa upload data."}), 403

    if 'file' not in request.files:
        return jsonify({"error": "Sistem tidak mendeteksi adanya file."}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        # Load Excel sebagai string untuk melindungi format ID Pelanggan (Nomen)
        df = pd.read_excel(file, dtype=str).fillna('')
        df.columns = [str(c).upper().strip() for c in df.columns]
        cols = df.columns.tolist()

        # Identifikasi Tipe File
        file_type = next((t for t, req in REQUIRED_COLS.items() if all(k in cols for k in req)), None)

        if not file_type:
            return jsonify({"error": "Header Excel tidak sesuai standar."}), 400

        row_count = 0
        current_month = datetime.now().strftime('%m-%Y')

        # --- EKSEKUSI DATA MASTER (MC) ---
        if file_type == 'MC':
            db.execute("DELETE FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'", (current_month,))
            for _, r in df.iterrows():
                z = autopilot_extract_zona(r['ZONA_NOVAK'])
                if not z: continue
                full_addr = f"{r['ALM1_PEL']} {r['ALM2_PEL']} {r['ALM3_PEL']}".strip()
                db.execute("""
                    INSERT INTO master_pelanggan (nomen, nama, alamat, kd_pos, pcez, rayon, pc, ez, blok, 
                    notagihan, nomet, tarif, tgl_catat, stan_awal, stan_akir, kubik, nominal, cust_type, tipe, periode)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'MC',?)
                """, (clean_nomen(r['NOMEN']), r['NAMA_PEL'], full_addr, r['KD_POS'], z['pcez'], z['rayon'], z['pc'], z['ez'], z['blok'],
                      r['NOTAGIHAN'], r['NOMET'], r['TARIF'], r['TGL_CATAT'], safe_float(r['STAN_AWAL']), safe_float(r['STAN_AKIR']), 
                      safe_float(r['KUBIK']), safe_float(r['NOMINAL']), r['CUST_TYPE'], current_month))
                row_count += 1

        # --- EKSEKUSI DATA BAYAR (MB) ---
        elif file_type == 'MB':
            for _, r in df.iterrows():
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, bulan_rek, notagihan, tgl_bayar, nominal, periode)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), r['BULAN_REK'], r['NOTAGIHAN'], r['TGL_BAYAR'], safe_float(r['NOMINAL']), current_month))
                row_count += 1

        # --- EKSEKUSI TUNGGAKAN (ARDEBT) ---
        elif file_type == 'ARDEBT':
            db.execute("DELETE FROM ardebt")
            for _, r in df.iterrows():
                db.execute("""
                    INSERT INTO ardebt (nomen, periode_bill, jumlah, volume)
                    VALUES (?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), r['PERIODE_BILL'], safe_float(r['JUMLAH']), safe_float(r['VOLUME'])))
                row_count += 1

        # --- EKSEKUSI SETORAN (COLLECTION) ---
        elif file_type == 'COLLECTION':
            for _, r in df.iterrows():
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, notag, bill_period, bill_reason, nominal, pay_dt, 
                    freeze_dttm, vol_collect, periode) VALUES (?,?,?,?,?,?,?,?,?)
                """, (clean_nomen(r['NOMEN']), r['NOTAG'], r['BILL_PERIOD'], r['BILL_REASON'], safe_float(r['NOMINAL']), 
                      r['PAY_DT'], r['FREEZE_DTTM'], safe_float(r['VOL_COLLECT']), current_month))
                row_count += 1

        # --- EKSEKUSI MAPPING RUTE ---
        elif file_type == 'RUTE':
            for _, r in df.iterrows():
                # V4.7: Mendukung kolom NO_ADMIN jika tersedia di Excel
                no_admin = r.get('NO_ADMIN', '628123456789').strip()
                db.execute("""
                    INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (r['PCEZ'].strip(), r['PETUGAS'].upper().strip(), no_admin))
                row_count += 1

        # --- CATAT RIWAYAT KE LOG AUDIT ---
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status)
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, file_type, current_month, row_count, 'SUCCESS'))

        db.commit()
        return jsonify({"status": "success", "message": f"Sinergi {file_type} Berhasil!", "rows": row_count})

    except Exception as e:
        if db: db.rollback()
        # Mencatat kegagalan ke histori jika memungkinkan
        try:
            db.execute("INSERT INTO upload_history (file_name, status) VALUES (?, ?)", (file_name, 'FAILED'))
            db.commit()
        except: pass
        return jsonify({"error": f"Kegagalan Sistem: {str(e)}"}), 500
    finally:
        if db: db.close()
