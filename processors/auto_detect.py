"""
Smart Period & Type Detector - Sunter Dashboard Pro (V6.3)
Last Updated: 2026-01-12
---------------------------------------------------------------------------
Pembaruan:
1. Rute Compatibility: Mengizinkan bypass deteksi periode untuk modul administratif.
2. Robust Parsing: Penanganan format tanggal Excel Serial & String yang lebih kuat.
3. Function Aliasing: Memastikan sinkronisasi nama fungsi dengan API Upload.
"""

import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    SINERGI DETECTOR (V6.3):
    Mendeteksi tipe file berdasarkan kolom kunci spesifik.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    # Deteksi Master Pelanggan (MC)
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols:
        return 'MC'
    
    # Deteksi Master Bayar (MB)
    if 'TGL_BAYAR' in cols:
        return 'MB'
    
    # Deteksi Realisasi Lapangan (Collection)
    if 'PAY_DT' in cols:
        return 'COLLECTION'
    
    # Deteksi Tunggakan Lama (Ardebt)
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ARDEBT'
    
    # Deteksi Pemetaan Area (Rute) - PCEZ & PETUGAS sesuai file 'Rute RL JS'
    if 'PETUGAS' in cols and 'PCEZ' in cols:
        return 'RUTE'
    
    return None

def parse_flexible_date(date_val):
    """
    Konverter Tanggal Universal: Mendukung format string dan Serial Date Excel.
    """
    if not date_val or str(date_val).lower() in ('nan', 'none', ''):
        return None

    s_date = str(date_val).split(' ')[0].replace("'", "").strip()
    
    # Proteksi: Jika input adalah angka murni (Serial Date Excel)
    try:
        if s_date.replace('.', '').isdigit():
            return datetime(1899, 12, 30) + timedelta(days=float(s_date))
    except:
        pass

    # Daftar format tanggal yang umum digunakan dalam laporan Excel
    formats = [
        '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', 
        '%d%m%Y', '%m%Y', '%Y%m%d', '%b-%y', '%B-%Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(s_date, fmt)
        except:
            continue
    return None

def detect_file_period(df, file_type):
    """
    LOGIKA PERIODE V6.3 (ULTRA-SYNC):
    Menentukan periode target berdasarkan jenis file dan referensi waktu baris pertama.
    """
    # [BYPASS] Khusus modul RUTE: Tidak membutuhkan deteksi periode dari file.
    if file_type == 'RUTE' or not file_type:
        return None, None

    cols = [str(c).upper().strip() for c in df.columns]
    mapping = {
        'MC': 'TGL_CATAT',
        'MB': 'TGL_BAYAR',
        'COLLECTION': 'PAY_DT',
        'ARDEBT': 'PERIODE_BILL'
    }
    
    date_col = mapping.get(file_type)
    if not date_col or date_col not in cols:
        return None, None
    
    try:
        # Ambil sampel baris pertama yang tidak kosong
        valid_rows = df[df[date_col].astype(str).str.strip() != '']
        if valid_rows.empty:
            return None, None
            
        raw_date = valid_rows.iloc[0].get(date_col)
        dt = parse_flexible_date(raw_date)
        
        if dt:
            # LOGIKA SINERGI N+1:
            # MC, MB, ARDEBT (Data Bulan N diproses untuk Periode Target N+1)
            if file_type in ['MC', 'MB', 'ARDEBT']:
                target_dt = dt + relativedelta(months=1)
            # COLLECTION (Realisasi tetap pada bulan yang sama)
            else:
                target_dt = dt 

            return target_dt.strftime('%m'), target_dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Detection Logic Warning: {str(e)}")
        
    return None, None

def autopilot_extract_zona(val):
    """
    Extract PCEZ cerdas dari kolom ZONA_NOVAK.
    Contoh: 010920100 -> Rayon: 01, PC: 092, EZ: 01, PCEZ: 092/01
    """
    if pd.isna(val) or str(val).strip() == '':
        return None
    
    # Bersihkan string dan ambil 9 digit angka
    s = ''.join(filter(str.isdigit, str(val).split('.')[0])).zfill(9)
    return {
        'rayon': s[0:2],
        'pc': s[2:5],
        'ez': s[5:7],
        'pcez': f"{s[2:5]}/{s[5:7]}",
        'blok': s[7:9]
    }

# Aliasing untuk sinkronisasi dengan kode lama (Core Compatibility)
parse_zona_novak = autopilot_extract_zona
