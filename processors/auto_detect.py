"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.32)
Update: 2026-01-19
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Intelligent Shift Separation: MC/MB otomatis geser N+1 (Des -> Jan).
2. Collection Persistence: Pembayaran lapangan Januari tetap di Dashboard Januari.
3. Strict Date Normalization: Penanganan format DD-MM-YYYY dan Excel Serial (46xxx).
4. Auto-Sanitizer Pro: Pembersihan mendalam untuk spasi liar dan karakter perbankan.
"""

import pandas as pd
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan struktur kolom kunci secara cerdas."""
    cols = [str(c).upper().strip() for c in df.columns]
    # Deteksi Master Pelanggan (Target)
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols: return 'MC'
    # Deteksi Master Bayar (Realisasi Bank)
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols: return 'MB'
    # Deteksi Collection Harian (Realisasi Lapangan)
    if 'BILL_PERIOD' in cols or 'PAY_DT' in cols: return 'COLLECTION'
    # Deteksi Piutang Lama
    if 'PERIODE_BILL' in cols or 'JUMLAH' in cols: return 'ARDEBT'
    # Deteksi Rute Petugas
    if 'PETUGAS' in cols and ('PCEZ' in cols or 'ZONA' in cols): return 'RUTE'
    return None

def clean_val(val):
    """Pembersihan karakter sampah tersembunyi (Non-breaking spaces, quotes)."""
    if val is None or (isinstance(val, float) and pd.isna(val)): return ""
    return str(val).replace('\xa0', ' ').replace("'", "").replace("`", "").strip()

def parse_billing_date(val, file_type='MB'):
    """Parsing format bulan rekening (122025, Des/2025, Jan-26)."""
    s = clean_val(val)
    if not s or s.lower() in ('nan', 'none'): return None
    try:
        # Format Digital 122025
        if len(s) == 6 and s.isdigit(): return datetime.strptime(s, '%m%Y')
        s_clean = s.replace('/', '-').replace(' ', '-')
        formats = ['%m-%Y', '%b-%y', '%B-%Y', '%m-%y', '%d-%m-%Y', '%Y-%m-%d']
        for fmt in formats:
            try: return datetime.strptime(s_clean, fmt)
            except: continue
    except: pass
    return None

def parse_flexible_date(date_val):
    """Excel Serial Fixer: Mengonversi angka 46037 menjadi objek tanggal Python."""
    s = clean_val(date_val)
    if not s or s.lower() in ('nan', 'none'): return None
    try:
        # Penanganan format angka Excel (contoh: 46006)
        num_str = s.split('.')[0]
        if num_str.isdigit() and 40000 < int(num_str) < 60000:
            return datetime(1899, 12, 30) + timedelta(days=int(num_str))
    except: pass
    
    # Penanganan format teks standar
    s_date = s.split(' ')[0].replace("/", "-")
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m%Y', '%b-%y', '%B-%Y']
    for fmt in formats:
        try: return datetime.strptime(s_date, fmt)
        except: continue
    return None

def detect_file_period(df, file_type):
    """
    LOGIKA PERIOD LOCKING (V12.32):
    - MC & MB: Tanggal Des -> Dashboard Jan (SHIFT N+1)
    - COLLECTION: Tanggal Jan -> Dashboard Jan (NO SHIFT)
    Tujuan: Menyatukan target dan realisasi di 'Rumah Dashboard' yang sama.
    """
    if file_type in ['RUTE', 'ARDEBT'] or not file_type: return None, None
    cols = [str(c).upper().strip() for c in df.columns]
    
    mapping = {
        'MC': 'TGL_CATAT',
        'MB': 'TGL_BAYAR',
        'COLLECTION': 'PAY_DT'
    }
    date_col = mapping.get(file_type)
    
    # Fallback jika kolom tidak standar di Excel
    if not date_col or date_col not in cols:
        for c in ['TGL_BAYAR', 'PAY_DT', 'TGL_CATAT', 'BULAN_REK', 'BILL_PERIOD']:
            if c in cols: 
                date_col = c
                break

    if not date_col or date_col not in cols: return None, None
    
    try:
        # Ambil sampel baris pertama untuk deteksi periode
        valid_rows = df[df[date_col].astype(str).str.strip() != ''].head(5)
        if valid_rows.empty: return None, None
        raw_date = valid_rows.iloc[0].get(date_col)
        
        # Deteksi jenis data (Bulan-Tahun atau Tanggal Lengkap)
        if date_col in ['BULAN_REK', 'BILL_PERIOD']:
            dt = parse_billing_date(raw_date, file_type)
        else:
            dt = parse_flexible_date(raw_date)
        
        if dt:
            # FIX STRATEGIS: Pemisahan N+1
            if file_type in ['MC', 'MB']:
                # Transaksi Des masuk Dashboard Jan (N+1)
                target_dt = dt + relativedelta(months=1)
            else:
                # Transaksi Jan tetap di Dashboard Jan
                target_dt = dt
                
            return target_dt.strftime('%m'), target_dt.strftime('%Y')
    except Exception as e:
        print(f"⚠️ Detection Error: {str(e)}")
        
    return None, None

def autopilot_extract_zona(val):
    """Ekstraksi PCEZ cerdas (Rayon-PC-EZ) untuk sinkronisasi peta rute."""
    s = clean_val(val)
    if not s: return None
    digits = ''.join(filter(str.isdigit, s.split('.')[0])).zfill(9)
    return {
        'rayon': digits[0:2], 'pc': digits[2:5], 'ez': digits[5:7],
        'pcez': digits[0:5], 'blok': digits[7:9]
    }

parse_zona_novak = autopilot_extract_zona
