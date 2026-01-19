"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.29)
Update: 2026-01-19
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Shift Logic (N+1): TGL_BAYAR Desember (1-31) otomatis masuk Dashboard Januari.
2. Unified Key Mapping: Menjamin output periode MM-YYYY konsisten di semua tipe file.
3. Robust Serial Fixer: Konversi angka serial Excel (46037) menjadi objek tanggal Python.
4. Auto-Sanitizer: Pembersihan whitespace perbankan (\xa0) agar deteksi tidak gagal.
"""

import pandas as pd
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan struktur kolom kunci."""
    cols = [str(c).upper().strip() for c in df.columns]
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols: return 'MC'
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols: return 'MB'
    if 'BILL_PERIOD' in cols or 'PAY_DT' in cols: return 'COLLECTION'
    if 'PERIODE_BILL' in cols or 'JUMLAH' in cols: return 'ARDEBT'
    if 'PETUGAS' in cols and ('PCEZ' in cols or 'ZONA' in cols): return 'RUTE'
    return None

def clean_val(val):
    """Membersihkan karakter sampah tersembunyi (\xa0, spasi liar, kutip)."""
    if val is None or (isinstance(val, float) and pd.isna(val)): return ""
    return str(val).replace('\xa0', ' ').replace("'", "").replace("`", "").strip()

def parse_billing_date(val, file_type='MB'):
    """SMART BILLING DETECTOR: Mengenali 122025, Des/2025, Jan-26, dll."""
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
    """EXCEL SERIAL FIXER: Mengonversi angka 46037 menjadi tanggal asli."""
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
    """
    LOGIKA GESER (N+1): 
    1. Transaksi (Bayar/Catat) di bulan N -> Masuk Dashboard N+1.
    2. Contoh: TGL_BAYAR 01-31 Des 2025 -> Dashboard 01-2026.
    """
    if file_type in ['RUTE', 'ARDEBT'] or not file_type: return None, None

    cols = [str(c).upper().strip() for c in df.columns]
    
    # Prioritas deteksi berdasarkan TANGGAL TRANSAKSI
    mapping = {
        'MC': 'TGL_CATAT',
        'MB': 'TGL_BAYAR',
        'COLLECTION': 'PAY_DT'
    }
    
    date_col = mapping.get(file_type)
    
    # Fallback jika kolom spesifik tidak ditemukan
    if not date_col or date_col not in cols:
        if 'TGL_BAYAR' in cols: date_col = 'TGL_BAYAR'
        elif 'PAY_DT' in cols: date_col = 'PAY_DT'
        elif 'TGL_CATAT' in cols: date_col = 'TGL_CATAT'
        elif 'BULAN_REK' in cols: date_col = 'BULAN_REK'
        elif 'BILL_PERIOD' in cols: date_col = 'BILL_PERIOD'

    if not date_col or date_col not in cols: return None, None
    
    try:
        valid_rows = df[df[date_col].astype(str).str.strip() != ''].head(5)
        if valid_rows.empty: return None, None
            
        raw_date = valid_rows.iloc[0].get(date_col)
        
        # Gunakan parser yang sesuai dengan tipe kolom
        if date_col in ['BULAN_REK', 'BILL_PERIOD']:
            dt = parse_billing_date(raw_date, file_type)
        else:
            dt = parse_flexible_date(raw_date)
        
        if dt:
            # SINKRONISASI N+1: Majukan 1 bulan dari tanggal referensi
            target_dt = dt + relativedelta(months=1)
            return target_dt.strftime('%m'), target_dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Detection Error: {str(e)}")
        
    return None, None

def autopilot_extract_zona(val):
    """Ekstraksi PCEZ cerdas (Rayon-PC-EZ) untuk sinkronisasi rute."""
    s = clean_val(val)
    if not s: return None
    digits = ''.join(filter(str.isdigit, s.split('.')[0])).zfill(9)
    return {
        'rayon': digits[0:2], 'pc': digits[2:5], 'ez': digits[5:7],
        'pcez': digits[0:5], 'blok': digits[7:9]
    }

parse_zona_novak = autopilot_extract_zona
