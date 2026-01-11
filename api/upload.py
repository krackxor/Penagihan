"""
Upload API - Sunter Dashboard Pro (V5.0 Sinergi Intelligence)
Sinergi & Smart Update:
1. Auto-Period Logic: MC/MB > date 25 automatically enters the next month's period (N+1).
2. Dynamic Collection Period: Determines the period directly from PAY_DT row by row.
3. NOMET Guard+: Ensures alphanumeric meter numbers are stored accurately.
4. Float Guard: Automatically handles empty cells as 0.0.
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen

upload_bp = Blueprint('upload', __name__)

# =========================================================================
# 1. REQUIRED COLUMNS CONFIGURATION
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
# 2. HELPER FUNCTIONS (AUTO-PERIOD & DATA GUARDS)
# =========================================================================

def get_dynamic_period(date_str, file_type):
    """
    Automatic Period Determination Logic:
    - MC & MB: If date > 25, period = Next Month (N+1).
    - COLLECTION: Period follows the month in PAY_DT.
    """
    try:
        # Normalize various date formats
        if '-' in str(date_str):
            dt = pd.to_datetime(date_str, dayfirst=True)
        else:
            # Handle Excel serial formats or strings without separators
            dt = pd.to_datetime(date_str)

        if file_type in ['MC', 'MB']:
            # N+1 logic if date exceeds the 25th
            if dt.day > 25:
                # Advance to next month
                target_dt = dt.replace(day=1) + timedelta(days=32)
                return target_dt.strftime('%m-%Y')
            return dt.strftime('%m-%Y')
        
        elif file_type == 'COLLECTION':
            # Collection follows the payment month directly
            return dt.strftime('%m-%Y')
            
    except:
        return datetime.now().strftime('%m-%Y')

def safe_float(val):
    """Excel Data Guard: Converts string/empty to safe float."""
    try:
        if pd.isna(val) or str(val).strip() == '': return 0.0
        clean_val = str(val).replace('.', '').replace(',', '.')
        return float(clean_val)
    except: return 0.0

def autopilot_extract_zona(val):
    """Slices ZONA_NOVAK into route components."""
    if pd.isna(val) or str(val).strip() == '': return None
    s = ''.join(filter(str.isdigit, str(val).split('.')[0])).zfill(9)
    return {
        'rayon': s[0:2], 'pc': s[2:5], 'ez': s[5:7],
        'pcez': f"{s[2:5]}/{s[5:7]}", 'blok': s[7:9]
    }

# =========================================================================
# 3. MAIN UPLOAD ROUTE
# =========================================================================

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    if session.get('role') != 'admin':
        return jsonify({"error": "Access Denied"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "No file found"}), 400
    
    file = request.files['file']
    file_name = file.filename
    db = get_db_connection()
    
    try:
        # Load data as string to protect alphanumeric formats (NOMET)
        df = pd.read_excel(file, dtype=str).fillna('')
        df.columns = [str(c).upper().strip() for c in df.columns]
        cols = df.columns.tolist()

        file_type = next((t for t, req in REQUIRED_COLS.items() if all(k in cols for k in req)), None)
        if not file_type:
            return jsonify({"error": "Excel Header format not recognized."}), 400

        row_count = 0
        last_detected_period = datetime.now().strftime('%m-%Y')

        # --- MC EXECUTION LOGIC (Master Pelanggan) ---
        if file_type == 'MC':
            for _, r in df.iterrows():
                row_period = get_dynamic_period(r['TGL_CATAT'], 'MC')
                last_detected_period = row_period
                z = autopilot_extract_zona(r['ZONA_NOVAK'])
                if not z: continue
                
                full_addr = f"{r['ALM1_PEL']} {r['ALM2_PEL']} {r['ALM3_PEL']}".strip()
                val_nomet = str(r['NOMET']).strip() if r['NOMET'] else "-"
                
                db.execute("""
                    INSERT INTO master_pelanggan (nomen, nama, alamat, kd_pos, pcez, rayon, pc, ez, blok, 
                    notagihan, nomet, tarif, tgl_catat, stan_awal, stan_akir, kubik, nominal, cust_type, periode)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (clean_nomen(r['NOMEN']), r['NAMA_PEL'], full_addr, r['KD_POS'], z['pcez'], z['rayon'], z['pc'], z['ez'], z['blok'],
                      r['NOTAGIHAN'], val_nomet, r['TARIF'], r['TGL_CATAT'], safe_float(r['STAN_AWAL']), safe_float(r['STAN_AKIR']), 
                      safe_float(r['KUBIK']), safe_float(r['NOMINAL']), r['CUST_TYPE'], row_period))
                row_count += 1

        # --- MB EXECUTION LOGIC (Master Bayar) ---
        elif file_type == 'MB':
            for _, r in df.iterrows():
                row_period = get_dynamic_period(r['TGL_BAYAR'], 'MB')
                last_detected_period = row_period
                db.execute("""
                    INSERT OR REPLACE INTO master_bayar (nomen, bulan_rek, notagihan, tgl_bayar, nominal, periode)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), r['BULAN_REK'], r['NOTAGIHAN'], r['TGL_BAYAR'], safe_float(r['NOMINAL']), row_period))
                row_count += 1

        # --- COLLECTION EXECUTION LOGIC (Harian Petugas) ---
        elif file_type == 'COLLECTION':
            for _, r in df.iterrows():
                row_period = get_dynamic_period(r['PAY_DT'], 'COLLECTION')
                last_detected_period = row_period
                db.execute("""
                    INSERT OR REPLACE INTO collection_harian (nomen, notag, bill_period, bill_reason, nominal, pay_dt, freeze_dttm, vol_collect, periode)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (clean_nomen(r['NOMEN']), r['NOTAG'], r['BILL_PERIOD'], r['BILL_REASON'], 
                      safe_float(r['NOMINAL']), r['PAY_DT'], r['FREEZE_DTTM'], safe_float(r['VOL_COLLECT']), row_period))
                row_count += 1

        # --- RUTE EXECUTION LOGIC ---
        elif file_type == 'RUTE':
            for _, r in df.iterrows():
                db.execute("""
                    INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (str(r['PCEZ']).strip(), str(r['PETUGAS']).strip().upper(), str(r.get('NO_ADMIN', ''))))
                row_count += 1

        # --- ARDEBT EXECUTION LOGIC ---
        elif file_type == 'ARDEBT':
            db.execute("DELETE FROM ardebt")
            for _, r in df.iterrows():
                db.execute("INSERT INTO ardebt (nomen, periode_bill, jumlah, volume) VALUES (?, ?, ?, ?)",
                          (clean_nomen(r['NOMEN']), r['PERIODE_BILL'], safe_float(r['JUMLAH']), safe_float(r['VOLUME'])))
                row_count += 1

        # Audit history with detected period
        db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?, ?, ?, ?, ?)",
                  (file_name, file_type, last_detected_period, row_count, 'SUCCESS'))

        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"{file_type} Sync Successful!", 
            "rows": row_count, 
            "period": last_detected_period
        })

    except Exception as e:
        if db: db.rollback()
        db.execute("INSERT INTO upload_history (file_name, status, row_count) VALUES (?, 'FAILED', 0)", (file_name,))
        db.commit()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
