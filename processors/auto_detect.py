"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.7 Strict Audit)
Update: 2026-01-12
---------------------------------------------------------------------------
Pembaruan Strategis:
1. FIXED: Menambahkan parse_billing_date untuk eliminasi ImportError.
2. Ardebt Detection: Otomatis mendeteksi file piutang lama (ARDEBT).
3. MB & Coll Logic: Pembedaan format 112025 vs Nov/2025 untuk validasi audit.
4. N+1 Targetting: Konsistensi penentuan periode dashboard (Bulan N -> Dashboard N+1).
"""

import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    SINERGI DETECTOR (V12.7):
    Mendeteksi tipe file berdasarkan struktur kolom kunci.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    # Deteksi Master Pelanggan (MC)
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols: return 'MC'
    
    # Deteksi Master Bayar (MB) - Berisi data bank
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols: return 'MB'
    
    # Deteksi Realisasi Lapangan (Collection)
    if 'BILL_PERIOD' in cols or 'PAY_DT' in cols: return 'COLLECTION'
    
    # Deteksi Piutang Lama (Ardebt)
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols: return 'ARDEBT'
    
    # Deteksi Pemetaan Administrasi (Rute)
    if 'PETUGAS' in cols and 'PCEZ' in cols: return 'RUTE'
    
    return None

def parse_billing_date(val, file_type='MB'):
    """
    FIXED: Fungsi krusial untuk membedah Bulan Rekening (Bulan N).
    Mendukung format: 122025 (MB) atau Dec/2025 (Collection).
    """
    if not val or str(val).lower() in ('nan', 'none', ''): return None
    s = str(val).strip().replace("'", "")
    
    try:
        # 1. Format MB: 122025 (6 digit angka murni)
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, '%m%Y')
        
        # 2. Format Collection: 12/2025 atau Dec/2025
        if '/' in s:
            parts = s.split('/')
            if parts[0].isalpha(): # Contoh: Dec/2025
                return datetime.strptime(f"{parts[0]} {parts[1]}", "%b %Y")
            else: # Contoh: 12/2025
                return datetime.strptime(f"{parts[0]} {parts[1]}", "%m %Y")
                
        # 3. Format Tanggal Standar (Fallback)
        for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
            try:
                return datetime.strptime(s.split(' ')[0], fmt)
            except: continue
    except: pass
    return None

def parse_flexible_date(date_val):
    """
    Konverter Tanggal Universal: Mendukung format string dan Serial Date Excel.
    """
    if not date_val or str(date_val).lower() in ('nan', 'none', ''): return None

    s_date = str(date_val).split(' ')[0].replace("'", "").replace("/", "-").strip()
    
    # Proteksi: Serial Date Excel (Contoh: 45291)
    try:
        if s_date.replace('.', '').isdigit() and len(s_date) < 6:
            return datetime(1899, 12, 30) + timedelta(days=float(s_date))
    except: pass

    # Daftar format tanggal umum
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m%Y', '%b-%y', '%B-%Y']
    for fmt in formats:
        try: return datetime.strptime(s_date, fmt)
        except: continue
    return None

def detect_file_period(df, file_type):
    """
    LOGIKA PERIODE V12.7 (ULTRA-SYNC):
    Dashboard N+1 dideteksi dari Bulan Rekening N di dalam file.
    """
    if file_type == 'RUTE' or not file_type: return None, None

    cols = [str(c).upper().strip() for c in df.columns]
    mapping = {
        'MC': 'TGL_CATAT',
        'MB': 'BULAN_REK',
        'COLLECTION': 'BILL_PERIOD',
        'ARDEBT': 'PERIODE_BILL'
    }
    
    # Jika kolom utama tidak ada, coba fallback ke kolom tanggal bayar
    date_col = mapping.get(file_type)
    if not date_col or date_col not in cols:
        date_col = 'TGL_BAYAR' if 'TGL_BAYAR' in cols else 'PAY_DT' if 'PAY_DT' in cols else None

    if not date_col or date_col not in cols: return None, None
    
    try:
        valid_rows = df[df[date_col].astype(str).str.strip() != '']
        if valid_rows.empty: return None, None
            
        raw_date = valid_rows.iloc[0].get(date_col)
        
        # Gunakan parse_billing_date untuk kolom periode, flexible untuk tanggal
        if date_col in ['BULAN_REK', 'BILL_PERIOD', 'PERIODE_BILL']:
            dt = parse_billing_date(raw_date, file_type)
        else:
            dt = parse_flexible_date(raw_date)
        
        if dt:
            # SEMUA DATA N DIPROSES UNTUK DASHBOARD N+1
            target_dt = dt + relativedelta(months=1)
            return target_dt.strftime('%m'), target_dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Detection Error: {str(e)}")
        
    return None, None

def autopilot_extract_zona(val):
    """
    Extract PCEZ cerdas dari kolom ZONA_NOVAK.
    """
    if pd.isna(val) or str(val).strip() == '': return None
    
    s = ''.join(filter(str.isdigit, str(val).split('.')[0])).zfill(9)
    return {
        'rayon': s[0:2],
        'pc': s[2:5],
        'ez': s[5:7],
        'pcez': s[0:5], # Format 5 digit PCEZ
        'blok': s[7:9]
    }

# Aliasing untuk sinkronisasi dengan API Upload
parse_zona_novak = autopilot_extract_zona
