"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.27)
Update: 2026-01-19
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Zero-Edit Automation: Parser lebih agresif menangani format Jan-26, 12/25, dan 12-2025.
2. N+1 Global Alignment: Memastikan target_period terkunci konsisten (Bulan N -> Dashboard N+1).
3. Robust Serial Fixer: Mendeteksi angka serial Excel (46037) dan mengonversinya secara otomatis.
4. Unicode/Bank Sanitizer: Membersihkan karakter non-standard (\xa0) dari ekspor perbankan.
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
    
    # Deteksi Master Bayar (MB)
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols: return 'MB'
    
    # Deteksi Realisasi Lapangan (Collection)
    if 'BILL_PERIOD' in cols or 'PAY_DT' in cols: return 'COLLECTION'
    
    # Deteksi Piutang Lama (Ardebt)
    if 'PERIODE_BILL' in cols or 'JUMLAH' in cols: return 'ARDEBT'
    
    # Deteksi Pemetaan Administrasi (Rute)
    if 'PETUGAS' in cols and ('PCEZ' in cols or 'ZONA' in cols): return 'RUTE'
    
    return None

def clean_val(val):
    """Membersihkan karakter sampah tersembunyi dari ekspor perbankan."""
    if val is None or (isinstance(val, float) and pd.isna(val)): return ""
    # Hapus spasi non-breaking (\xa0), kutip, backtick, dan whitespace liar
    return str(val).replace('\xa0', ' ').replace("'", "").replace("`", "").strip()

def parse_billing_date(val, file_type='MB'):
    """SMART BILLING DETECTOR: Mengenali 122025, Des/2025, Jan-26, dll."""
    s = clean_val(val)
    if not s or s.lower() in ('nan', 'none'): return None
    
    try:
        # 1. Format MB Murni: 112025 (6 digit)
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, '%m%Y')
        
        # 2. Format Separator & Abstraksi Bulan (Des/2025, Jan-26)
        s_clean = s.replace('/', '-').replace(' ', '-')
        # Daftar scanner format bulan-tahun
        formats = ['%m-%Y', '%b-%y', '%B-%Y', '%m-%y', '%d-%m-%Y', '%Y-%m-%d']
        for fmt in formats:
            try:
                return datetime.strptime(s_clean, fmt)
            except:
                continue
    except:
        pass
    return None

def parse_flexible_date(date_val):
    """EXCEL SERIAL FIXER: Mengonversi angka 46037 menjadi tanggal asli."""
    s = clean_val(date_val)
    if not s or s.lower() in ('nan', 'none'): return None
    
    # Proteksi: Serial Date Excel (Contoh: 46037.0)
    try:
        # Bersihkan desimal jika ada
        num_str = s.split('.')[0]
        if num_str.isdigit() and 40000 < int(num_str) < 60000:
            return datetime(1899, 12, 30) + timedelta(days=int(num_str))
    except:
        pass

    # Standard Parsing
    s_date = s.split(' ')[0].replace("/", "-")
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m%Y', '%b-%y', '%B-%Y']
    for fmt in formats:
        try:
            return datetime.strptime(s_date, fmt)
        except:
            continue
    return None

def detect_file_period(df, file_type):
    """
    LOGIKA N+1: Dashboard Januari (01) didapat dari Rekening Desember (12).
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
        # Ambil sampel baris pertama yang valid
        valid_rows = df[df[date_col].astype(str).str.strip() != ''].head(5)
        if valid_rows.empty: return None, None
            
        raw_date = valid_rows.iloc[0].get(date_col)
        
        # Parsing tanggal dasar
        if date_col in ['BULAN_REK', 'BILL_PERIOD']:
            dt = parse_billing_date(raw_date, file_type)
        else:
            dt = parse_flexible_date(raw_date)
        
        if dt:
            # FIX UTAMA: Otomatis memajukan 1 bulan (N+1) untuk target dashboard
            target_dt = dt + relativedelta(months=1)
            return target_dt.strftime('%m'), target_dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Detection Error: {str(e)}")
        
    return None, None

def autopilot_extract_zona(val):
    """Ekstraksi PCEZ cerdas (Rayon-PC-EZ)."""
    s = clean_val(val)
    if not s: return None
    
    # Ambil angka saja, buang titik/karakter pemisah
    digits = ''.join(filter(str.isdigit, s.split('.')[0])).zfill(9)
    return {
        'rayon': digits[0:2], 
        'pc': digits[2:5], 
        'ez': digits[5:7],
        'pcez': digits[0:5], 
        'blok': digits[7:9]
    }

# Aliasing untuk sinkronisasi sistem
parse_zona_novak = autopilot_extract_zona
