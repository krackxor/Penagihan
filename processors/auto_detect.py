"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.22)
Update: 2026-01-13
---------------------------------------------------------------------------
Pembaruan Strategis:
1. N+1 Global Alignment: Memastikan Bulan Rekening 11 otomatis masuk ke Periode 12.
2. Zero Gap Parsing: Menangani whitespace non-standard (\xa0) dan karakter kutip.
3. Enhanced MB Detection: Validasi format 112025 (6-digit) sebagai prioritas utama audit.
4. Serial Date Fix: Konversi otomatis angka Serial Excel menjadi objek tanggal Python.
"""

import pandas as pd
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan struktur kolom kunci."""
    cols = [str(c).upper().strip() for c in df.columns]
    
    # Deteksi Master Pelanggan (MC)
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols: return 'MC'
    
    # Deteksi Master Bayar (MB) - Sumber Utama UNDUE
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols: return 'MB'
    
    # Deteksi Realisasi Lapangan (Collection) - Sumber Utama CURRENT
    if 'BILL_PERIOD' in cols or 'PAY_DT' in cols: return 'COLLECTION'
    
    # Deteksi Piutang Lama (Ardebt)
    if 'PERIODE_BILL' in cols or 'JUMLAH' in cols: return 'ARDEBT'
    
    # Deteksi Pemetaan Administrasi (Rute)
    if 'PETUGAS' in cols and ('PCEZ' in cols or 'ZONA' in cols): return 'RUTE'
    
    return None

def clean_val(val):
    """Membersihkan karakter sampah tersembunyi dari ekspor perbankan."""
    if not val or pd.isna(val): return ""
    # Hapus spasi non-breaking (\xa0), kutip, dan whitespace
    return str(val).replace('\xa0', ' ').replace("'", "").replace("`", "").strip()

def parse_billing_date(val, file_type='MB'):
    """Membedah Bulan Rekening (Bulan N)."""
    s = clean_val(val)
    if not s or s.lower() in ('nan', 'none'): return None
    
    try:
        # 1. Format MB: 112025 (6 digit angka murni)
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, '%m%Y')
        
        # 2. Format Separator: 11/2025 atau Nov/2025
        if '/' in s:
            parts = s.split('/')
            if parts[0].isalpha(): # Contoh: Nov/2025
                return datetime.strptime(f"{parts[0]} {parts[1]}", "%b %Y")
            else: # Contoh: 11/2025
                return datetime.strptime(f"{parts[0]} {parts[1]}", "%m %Y")
                
        # 3. Format Fallback (Tanggal Standar)
        for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m-%Y']:
            try: return datetime.strptime(s.split(' ')[0], fmt)
            except: continue
    except: pass
    return None

def parse_flexible_date(date_val):
    """Konverter Tanggal Universal termasuk Serial Date Excel."""
    s_date = clean_val(date_val).split(' ')[0].replace("/", "-")
    if not s_date or s_date.lower() in ('nan', 'none'): return None
    
    # Proteksi: Serial Date Excel (Contoh: 45291)
    try:
        if s_date.replace('.', '').isdigit() and len(s_date) < 6:
            return datetime(1899, 12, 30) + timedelta(days=float(s_date))
    except: pass

    # Daftar format umum
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m%Y', '%b-%y', '%B-%Y']
    for fmt in formats:
        try: return datetime.strptime(s_date, fmt)
        except: continue
    return None

def detect_file_period(df, file_type):
    """
    LOGIKA N+1: Dashboard Desember (12) didapat dari Rekening November (11).
    """
    if file_type in ['RUTE', 'ARDEBT'] or not file_type: return None, None

    cols = [str(c).upper().strip() for c in df.columns]
    mapping = {
        'MC': 'TGL_CATAT',
        'MB': 'BULAN_REK',
        'COLLECTION': 'BILL_PERIOD'
    }
    
    date_col = mapping.get(file_type)
    if not date_col or date_col not in cols:
        date_col = 'TGL_BAYAR' if 'TGL_BAYAR' in cols else 'PAY_DT' if 'PAY_DT' in cols else None

    if not date_col or date_col not in cols: return None, None
    
    try:
        # Ambil sampel baris pertama yang valid (bukan header kosong)
        valid_rows = df[df[date_col].astype(str).str.strip() != ''].head(5)
        if valid_rows.empty: return None, None
            
        raw_date = valid_rows.iloc[0].get(date_col)
        
        # Parsing tanggal dasar
        if date_col in ['BULAN_REK', 'BILL_PERIOD']:
            dt = parse_billing_date(raw_date, file_type)
        else:
            dt = parse_flexible_date(raw_date)
        
        if dt:
            # FIX UTAMA: Menambahkan 1 bulan ke depan untuk target dashboard
            target_dt = dt + relativedelta(months=1)
            return target_dt.strftime('%m'), target_dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Detection Error: {str(e)}")
        
    return None, None

def autopilot_extract_zona(val):
    """Ekstraksi PCEZ cerdas (Rayon-PC-EZ)."""
    s = clean_val(val)
    if not s: return None
    
    # Ambil angka saja
    digits = ''.join(filter(str.isdigit, s.split('.')[0])).zfill(9)
    return {
        'rayon': digits[0:2], 
        'pc': digits[2:5], 
        'ez': digits[5:7],
        'pcez': digits[0:5], 
        'blok': digits[7:9]
    }

# Aliasing untuk sinkronisasi dengan API Upload
parse_zona_novak = autopilot_extract_zona
