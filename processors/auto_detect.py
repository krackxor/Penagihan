"""
Smart Period & Type Detector - Sunter Dashboard Pro (V12.35 Ultra-Sync)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Strict Shift Locking: Mencegah kebocoran periode pada file COLLECTION.
2. Nomen Sanitizer Pro: Pembersihan ID Pelanggan dari spasi liar/titik.
3. Accurate Billing Detection: Mendukung format MMYYYY (122025) secara presisi.
4. Robust Excel Handling: Perbaikan konversi serial date untuk stabilitas upload.
"""

import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan struktur kolom kunci secara cerdas."""
    cols = [str(c).upper().strip() for c in df.columns]
    
    # Deteksi Master Pelanggan (MC)
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols: return 'MC'
    
    # Deteksi Master Bayar (MB) - Realisasi Bank
    if 'BULAN_REK' in cols or 'TGL_BAYAR' in cols: return 'MB'
    
    # Deteksi Collection Harian (Lapangan)
    if 'PAY_DT' in cols or 'BILL_PERIOD' in cols: return 'COLLECTION'
    
    # Deteksi Piutang Lama (ARDEBT)
    if 'PERIODE_BILL' in cols or 'JUMLAH' in cols: return 'ARDEBT'
    
    # Deteksi Rute Petugas
    if 'PETUGAS' in cols and ('PCEZ' in cols or 'ZONA' in cols): return 'RUTE'
    
    return None

def clean_val(val):
    """Pembersihan karakter sampah tersembunyi secara mendalam."""
    if val is None or (isinstance(val, float) and pd.isna(val)): return ""
    # Menghapus spasi non-breaking dan karakter kutipan liar
    return str(val).replace('\xa0', ' ').replace("'", "").replace("`", "").strip()

def parse_billing_date(val):
    """Parsing format bulan rekening tagihan (Contoh: 122025 atau 01-2026)."""
    s = clean_val(val).replace('-', '').replace('/', '')
    if not s or not s.isdigit(): return None
    
    try:
        # Jika format 122025 (MMYYYY)
        if len(s) == 6:
            return datetime.strptime(s, '%m%Y')
        # Jika format 1225 (MMYY)
        elif len(s) == 4:
            return datetime.strptime(s, '%m%y')
    except: 
        pass
    return None

def parse_flexible_date(date_val):
    """Excel Serial Fixer: Mengonversi angka serial Excel (46xxx) menjadi tanggal."""
    s = clean_val(date_val)
    if not s or s.lower() in ('nan', 'none'): return None
    
    try:
        # Penanganan format angka Excel (contoh: 46006)
        if s.replace('.','').isdigit():
            num_val = int(float(s))
            if 40000 < num_val < 60000:
                return datetime(1899, 12, 30) + timedelta(days=num_val)
    except: 
        pass
    
    # Penanganan format teks standar
    s_date = s.split(' ')[0].replace("/", "-")
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y']
    for fmt in formats:
        try: 
            return datetime.strptime(s_date, fmt)
        except: 
            continue
    return None

def detect_file_period(df, file_type):
    """
    LOGIKA PERIOD LOCKING (V12.35):
    - MC & MB: Data Des -> Dashboard Jan (SHIFT N+1) untuk sinkronisasi tagihan.
    - COLLECTION: Data Jan -> Dashboard Jan (NO SHIFT) agar tren harian akurat.
    """
    if file_type in ['RUTE', 'ARDEBT'] or not file_type: return None, None
    cols = [str(c).upper().strip() for c in df.columns]
    
    # Penentuan kolom tanggal utama berdasarkan prioritas
    date_col = None
    priority = ['BULAN_REK', 'BILL_PERIOD', 'TGL_CATAT', 'TGL_BAYAR', 'PAY_DT']
    for p in priority:
        if p in cols:
            date_col = p
            break

    if not date_col: return None, None
    
    try:
        # Ambil sampel baris pertama yang tidak kosong
        sample = df[df[date_col].astype(str).str.strip() != ''].head(1)
        if sample.empty: return None, None
        raw_val = sample.iloc[0].get(date_col)
        
        # Ekstraksi Tanggal
        if date_col in ['BULAN_REK', 'BILL_PERIOD']:
            dt = parse_billing_date(raw_val)
        else:
            dt = parse_flexible_date(raw_val)

        if dt:
            # FIX LOGIKA: SHIFT N+1 (MC & MB ditarik ke depan, COLLECTION tetap di tempat)
            if file_type in ['MC', 'MB']:
                # Tagihan Desember ditarik ke Dashboard Januari
                target_dt = dt + relativedelta(months=1)
            else:
                # Transaksi Januari tetap di Dashboard Januari
                target_dt = dt
                
            return target_dt.strftime('%m'), target_dt.strftime('%Y')
    except: 
        pass
        
    return None, None

def autopilot_extract_zona(val):
    """Ekstraksi PCEZ cerdas (Rayon-PC-EZ) untuk validasi rute petugas."""
    s = clean_val(val)
    if not s: return None
    # Membersihkan titik atau spasi (Contoh: 34.001 -> 34001)
    clean_s = "".join(filter(str.isdigit, s))
    digits = clean_s.zfill(9)
    return {
        'rayon': digits[0:2],
        'pcez': digits[0:5],
        'ez': digits[5:7]
    }

parse_zona_novak = autopilot_extract_zona
