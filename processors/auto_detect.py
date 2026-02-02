"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.36 Intelligence Sync)
Update: 2026-02-02
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ FIX BELUM BAYAR: Memisahkan deteksi MB dan MC secara mutlak menggunakan 
   kolom 'STAN_AWAL' untuk MC agar tidak bentrok dengan file pembayaran.
2. Intelligent PCEZ Normalization: Memastikan format '092/01' diprioritaskan.
3. Fallback Safety: Menjamin data tidak 'None' meski format tidak standar.
"""

import pandas as pd
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan struktur kolom unik secara akurat."""
    cols = [str(c).upper().strip() for c in df.columns]
    
    # --- 1. DETEKSI MASTER BAYAR (MB) ---
    # File MB ditandai dengan adanya transaksi 'BULAN_REK' atau 'TGL_BAYAR'.
    # Harus dicek pertama agar tidak disangka MC karena memiliki kolom NOMEN.
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols or 'JML_BAYAR' in cols:
        return 'MB'

    # --- 2. DETEKSI MASTER PELANGGAN (MC) ---
    # File MC memiliki kolom data fisik meteran yang TIDAK ADA di file MB.
    # Menggunakan 'STAN_AWAL' atau 'KUBIK' sebagai pembeda mutlak.
    if 'STAN_AWAL' in cols or 'STAN_AKIR' in cols or 'KUBIK' in cols:
        return 'MC'

    # --- 3. DETEKSI COLLECTION (LAPANGAN) ---
    coll_triggers = ['BILL_PERIOD', 'PAY_DT', 'TGL_KOLEK']
    if any(c in cols for c in coll_triggers):
        return 'COLLECTION'

    # --- 4. DETEKSI ARDEBT (TUNGGAKAN) ---
    ardebt_triggers = ['PERIODE_BILL', 'JUMLAH', 'SALDO_AKHIR']
    if any(c in cols for c in ardebt_triggers):
        return 'ARDEBT'

    # --- 5. DETEKSI RUTE PETUGAS ---
    if 'PETUGAS' in cols and ('PCEZ' in cols or 'ZONA' in cols or 'RUTE' in cols):
        return 'RUTE'

    return None

def clean_val(val):
    """Pembersihan karakter sampah tersembunyi."""
    if val is None or (isinstance(val, float) and pd.isna(val)): return ""
    return str(val).replace('\xa0', ' ').replace("'", "").replace("`", "").strip()

def parse_billing_date(val, file_type='MB'):
    """Parsing format bulan rekening (122025, Des/2025, Jan-26)."""
    s = clean_val(val)
    if not s or s.lower() in ('nan', 'none'): return None
    try:
        if len(s) == 6 and s.isdigit(): return datetime.strptime(s, '%m%Y')
        s_clean = s.replace('/', '-').replace(' ', '-')
        formats = ['%m-%Y', '%b-%y', '%B-%Y', '%m-%y', '%d-%m-%Y', '%Y-%m-%d']
        for fmt in formats:
            try: return datetime.strptime(s_clean, fmt)
            except: continue
    except: pass
    return None

def parse_flexible_date(date_val):
    """Excel Serial Fixer: Mengonversi angka 46037 menjadi objek tanggal."""
    s = clean_val(date_val)
    if not s or s.lower() in ('nan', 'none'): return None
    try:
        num_str = s.split('.')[0]
        if num_str.isdigit() and 40000 < int(num_str) < 60000:
            return datetime(1899, 12, 30) + timedelta(days=int(num_str))
    except: pass
    
    s_date = s.split(' ')[0].replace("/", "-")
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m%Y', '%b-%y', '%B-%Y']
    for fmt in formats:
        try: return datetime.strptime(s_date, fmt)
        except: continue
    return None

def detect_file_period(df, file_type):
    """Logika Period Locking N+1 & Sync."""
    if file_type in ['RUTE', 'ARDEBT'] or not file_type: return None, None
    cols = [str(c).upper().strip() for c in df.columns]
    
    mapping = {'MC': 'TGL_CATAT', 'MB': 'TGL_BAYAR', 'COLLECTION': 'PAY_DT'}
    date_col = mapping.get(file_type)
    
    if not date_col or date_col not in cols:
        for c in ['TGL_BAYAR', 'PAY_DT', 'TGL_CATAT', 'BULAN_REK', 'BILL_PERIOD', 'WA', 'NO_HP']:
            if c in cols: 
                date_col = c
                break

    if not date_col or date_col not in cols: 
        now = datetime.now()
        return now.strftime('%m'), now.strftime('%Y')
    
    try:
        valid_rows = df[df[date_col].astype(str).str.strip() != ''].head(5)
        if valid_rows.empty: 
            now = datetime.now()
            return now.strftime('%m'), now.strftime('%Y')

        raw_date = valid_rows.iloc[0].get(date_col)
        dt = parse_billing_date(raw_date, file_type) if date_col in ['BULAN_REK', 'BILL_PERIOD'] else parse_flexible_date(raw_date)
        
        if not dt: dt = datetime.now()
        
        if file_type in ['MC', 'MB']:
            target_dt = dt + relativedelta(months=1)
        else:
            target_dt = dt
            
        return target_dt.strftime('%m'), target_dt.strftime('%Y')
    except:
        now = datetime.now()
        return now.strftime('%m'), now.strftime('%Y')

def autopilot_extract_zona(val):
    """
    Ekstraksi PCEZ cerdas V2.
    Mengutamakan format 092/01 agar sinkron dengan file Rute RL JS.
    """
    s = clean_val(val)
    if not s: return None
    
    try:
        if '/' in s:
            parts = [p.strip() for p in s.split('/')]
            if len(parts) >= 2:
                pcez_clean = f"{parts[0].zfill(3)}/{parts[1].zfill(2)}"
                return {
                    'pcez': pcez_clean,
                    'rayon': '34', 
                    'pc': parts[0].zfill(3),
                    'ez': parts[1].zfill(2),
                    'blok': '00'
                }

        digits = ''.join(filter(str.isdigit, s.split('.')[0]))
        
        if len(digits) >= 7:
            return {
                'rayon': digits[0:2],
                'pc': digits[2:5],
                'ez': digits[5:7],
                'pcez': f"{digits[2:5]}/{digits[5:7]}", 
                'blok': digits[7:9] if len(digits) > 7 else '00'
            }
        elif len(digits) == 5:
            return {
                'rayon': '34',
                'pc': digits[0:3],
                'ez': digits[3:5],
                'pcez': f"{digits[0:3]}/{digits[3:5]}",
                'blok': '00'
            }
            
        return {'rayon': '00', 'pc': '000', 'ez': '00', 'pcez': s, 'blok': '00'}
        
    except:
        return {'rayon': '00', 'pc': '000', 'ez': '00', 'pcez': '000/00', 'blok': '00'}

parse_zona_novak = autopilot_extract_zona
