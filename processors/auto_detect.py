"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.0 Strict Audit)
Last Updated: 2026-01-12
---------------------------------------------------------------------------
Pembaruan Strategis:
1. FIXED: Menambahkan parse_billing_date untuk sinkronisasi api/upload.py.
2. MB Logic: Deteksi Bulan Rekening dari format 112025.
3. Collection Logic: Deteksi Billing Period dari format Nov/2025.
4. Hard Filter Support: Memungkinkan penghitungan selisih bulan bayar vs tagihan.
"""

import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    Mendeteksi tipe file berdasarkan kolom kunci spesifik.
    V12.0: Mendukung deteksi berbasis kolom audit (BULAN_REK / BILL_PERIOD).
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols: return 'MC'
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols: return 'MB'
    if 'BILL_PERIOD' in cols or 'PAY_DT' in cols: return 'COLLECTION'
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols: return 'ARDEBT'
    if 'PETUGAS' in cols and 'PCEZ' in cols: return 'RUTE'
    
    return None

def parse_billing_date(val, file_type):
    """
    Konverter khusus untuk menentukan BULAN TAGIHAN (Bulan N).
    Mendukung format MB (112025) dan Collection (Nov/2025).
    """
    if not val or str(val).lower() in ('nan', 'none', ''):
        return None

    s = str(val).strip().replace("'", "")
    
    try:
        # 1. Format MB: 112025 (6 digit angka)
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, '%m%Y')
        
        # 2. Format Collection: Nov/2025 atau 11/2025
        if '/' in s:
            parts = s.split('/')
            # Jika bagian pertama adalah huruf (Nov/2025)
            if parts[0].isalpha():
                return datetime.strptime(f"{parts[0]} {parts[1]}", "%b %Y")
            # Jika bagian pertama adalah angka (11/2025)
            return datetime.strptime(f"{parts[0]} {parts[1]}", "%m %Y")

        # 3. Format Tanggal Standar (Fallback)
        for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
            try:
                return datetime.strptime(s.split(' ')[0], fmt)
            except: continue
    except:
        pass
    return None

def parse_flexible_date(date_val):
    """
    Konverter Tanggal Universal: Mendukung format string dan Serial Date Excel.
    Digunakan untuk kolom TGL_BAYAR atau PAY_DT.
    """
    if not date_val or str(date_val).lower() in ('nan', 'none', ''):
        return None

    s_date = str(date_val).split(' ')[0].replace("'", "").replace("/", "-").strip()
    
    # Proteksi Serial Date Excel
    try:
        if s_date.replace('.', '').isdigit() and len(s_date) < 6:
            return datetime(1899, 12, 30) + timedelta(days=float(s_date))
    except: pass

    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m%Y', '%b-%y']
    for fmt in formats:
        try: return datetime.strptime(s_date, fmt)
        except: continue
    return None

def detect_file_period(df, file_type):
    """
    LOGIKA PERIODE V12.0:
    Menghitung periode target N+1 berdasarkan Bulan Rekening di dalam file.
    """
    if file_type == 'RUTE' or not file_type:
        return None, None

    cols = [str(c).upper().strip() for c in df.columns]
    
    # Tentukan kolom referensi bulan tagihan (Bulan N)
    col_ref = 'BULAN_REK' if 'BULAN_REK' in cols else \
              'BILL_PERIOD' if 'BILL_PERIOD' in cols else \
              'TGL_CATAT' if 'TGL_CATAT' in cols else \
              'PERIODE_BILL' if 'PERIODE_BILL' in cols else None
    
    if not col_ref: return None, None
    
    try:
        # Ambil sampel baris pertama yang valid
        valid_rows = df[df[col_ref].astype(str).str.strip() != '']
        if valid_rows.empty: return None, None
            
        raw_val = valid_rows.iloc[0].get(col_ref)
        dt_n = parse_billing_date(raw_val, file_type)
        
        if dt_n:
            # SEMUA DATA TAGIHAN BULAN N ADALAH TARGET UNTUK PERIODE N+1 (Dashboard)
            target_dt = dt_n + relativedelta(months=1)
            return target_dt.strftime('%m'), target_dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Detection Error: {str(e)}")
        
    return None, None

def autopilot_extract_zona(val):
    """
    Extract PCEZ cerdas dari kolom ZONA_NOVAK.
    """
    if pd.isna(val) or str(val).strip() == '': return None
    
    s = ''.join(filter(str.isdigit, str(val).split('.')[0]))
    if len(s) >= 7:
        return {
            'rayon': s[0:2],
            'pc': s[2:3],
            'ez': s[3:5],
            'pcez': s[0:5],
            'blok': s[5:7]
        }
    return None

# Aliasing untuk sinkronisasi dengan API Upload
parse_zona_novak = autopilot_extract_zona
