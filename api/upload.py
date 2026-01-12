"""
Upload API - Sunter Dashboard Pro (V5.4 Intelligence Edition)
Sinergi & Smart Update:
1. N+1 Period Logic: MC & MB bulan 11 otomatis menjadi Periode 12-2025.
2. Collection Sync: PAY_DT bulan 12 tetap menjadi Periode 12-2025.
3. Excel Date Guard: Konversi angka serial (45986.0) menjadi tanggal valid.
4. Ardebt Integrity: Membersihkan NOMEN pada Ardebt agar sinkron dengan Master.
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, clean_notag

upload_bp = Blueprint('upload', __name__)

# =========================================================================
# 1. STRICT COLUMN CONFIGURATION
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
    'RUTE': ['PCEZ', 'PETUGAS']
}

# =========================================================================
# 2. HELPER FUNCTIONS (SINKRONISASI DATA)
# =========================================================================

def parse_excel_date(val):
    """Konversi format tanggal Excel (Serial/String) menjadi objek Datetime."""
    try:
        # Jika berupa angka serial Excel (contoh: 45987.0)
        if str(val).replace('.', '').isdigit():
            return datetime(1899, 12, 30) + timedelta(days=float(val))
        return pd.to_datetime(val, dayfirst=True)
    except:
        return datetime.now()

def get_logic_period(date_val, file_type):
    """
    LOGIKA PERIODE BILL:
    - MC & MB: Bulan N menjadi target bulan N+1 (Nov -> Des)
    - Collection: Tetap di bulan berjalan (Des -> Des)
    """
    dt = parse_excel_date(date_val)
    if file_type in ['MC', 'MB', 'ARDEBT']:
        # Tambah 1 bulan untuk Periode Target
        month = dt.month + 1
        year = dt.year
        if month > 12:
            month = 1
            year += 1
        return f"{str(month).zfill(2)}-{year}"
    return dt.strftime('%m-%Y')

def safe_float(val):
    """Data Guard: Memastikan angka desimal Excel terbaca benar."""
    try:
        if pd.isna(val) or str(val).strip() == '': return 0.0
        clean_val = str(val).replace('.', '').replace(',', '.')
        return float(clean_val)
    except: return 0.0

def autopilot_extract_zona(val):
    """Ekstraksi ZONA_NOVAK menjadi PCEZ (350960217 -> 096/02)."""
    if pd.isna(val) or str(val).strip() == '': return None
    s = ''.join(filter(str.isdigit, str(val).split('.')[0])).zfill(9)
    return {
        'rayon': s[0:2], 'pc': s[2:5], 'ez': s[5:7],
        'pcez': f"{s[2:5]}/{s[5:7]}", 'blok': s[7:9]
    }

# =========================================================================
# 3. MAIN UPLOAD HANDLER (DATABASE SYNC)
# =========================================================================

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
        df = pd.read_excel(file, dtype=str).fillna('')
        df.columns = [str(c).upper().strip() for c in df.columns]
        cols = df.columns.tolist()

        file_type = next((t for t, req in REQUIRED_COLS.items() if all(k in cols for k in req)), None)
        if not file_type:
            return jsonify({"error": "Format Header Excel tidak dikenali."}), 400

        row_count = 0
        detected_period = ""

        # --- MC PROCESSING (Pondasi Target) ---
        if file_type == 'MC':
            for _, r in df.iterrows():
                row_period = get_logic_period(r['TGL_CATAT'], 'MC')
                detected_period = row_period
                z = autopilot_extract_zona(r['ZONA_NOVAK'])
                if not z: continue
                
                db.execute("""
                    INSERT INTO master_pelanggan (nomen, nama, alamat, kd_pos, pcez, rayon, pc, ez, blok, 
                    notagihan, nomet, tarif, tgl_catat, stan_awal, stan_akir, kubik, nominal, cust_type, periode)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (clean_nomen(r['NOMEN']), r['NAMA_PEL'], f"{r['ALM1_PEL']} {r['ALM2_PEL']}".strip(), 
                      r['KD_POS'], z['pcez'], z['rayon'], z['pc'], z['ez'], z['blok'],
                      clean_notag(r['NOTAGIHAN']), str(r['NOMET']).strip(), r['TARIF'], r['TGL_CATAT'], 
                      safe_float(r['STAN_AWAL']), safe_float(r['STAN_AKIR']), 
                      safe_float(r['KUBIK']), safe_float(r['NOMINAL']), r['CUST_TYPE'], row_period))
                row_count += 1

        # --- MB PROCESSING (Realisasi Undue) ---
        elif file_type == 'MB':
            for _, r in df.iterrows():
                row_period = get_logic_period(r['TGL_BAYAR'], 'MB')
                detected_period = row_period
                # LOGIKA UNDUE: Dibayar Nov (Tgl 25) untuk Periode Des
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, bulan_rek, notagihan, tgl_bayar, nominal, periode)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), r['BULAN_REK'], clean_notag(r['NOTAGIHAN']), 
                      r['TGL_BAYAR'], safe_float(r['NOMINAL']), row_period))
                row_count += 1

        # --- COLLECTION PROCESSING (Realisasi Current) ---
        elif file_type == 'COLLECTION':
            for _, r in df.iterrows():
                # Tetap di periode bulan berjalan (Des -> Des)
                row_period = get_logic_period(r['PAY_DT'], 'COLLECTION')
                detected_period = row_period
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, notag, bill_period, bill_reason, nominal, pay_dt, freeze_dttm, vol_collect, periode)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), clean_notag(r['NOTAG']), r['BILL_PERIOD'], r['BILL_REASON'], 
                      safe_float(r['NOMINAL']), r['PAY_DT'], r['FREEZE_DTTM'], safe_float(r['VOL_COLLECT']), row_period))
                row_count += 1

        # --- ARDEBT PROCESSING (Tunggakan Berbulan-bulan) ---
        elif file_type == 'ARDEBT':
            # Hapus data lama agar sinkron dengan file terbaru
            db.execute("DELETE FROM ardebt")
            for _, r in df.iterrows():
                db.execute("INSERT INTO ardebt (nomen, periode_bill, jumlah, volume) VALUES (?, ?, ?, ?)",
                          (clean_nomen(r['NOMEN']), r['PERIODE_BILL'], safe_float(r['JUMLAH']), safe_float(r['VOLUME'])))
                row_count += 1

        # --- RUTE PROCESSING ---
        elif file_type == 'RUTE':
            for _, r in df.iterrows():
                db.execute("""
                    INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (str(r['PCEZ']).strip(), str(r['PETUGAS']).strip().upper(), str(r.get('NO_ADMIN', ''))))
                row_count += 1

        # Audit History
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)",
                  (file_name, file_type, detected_period, row_count, 'SUCCESS'))

        db.commit()
        return jsonify({"status": "success", "message": f"{file_type} Sync Berhasil!", "rows": row_count, "period": detected_period})

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
