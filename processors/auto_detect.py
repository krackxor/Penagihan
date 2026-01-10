import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    SINERGI DETECTOR (Updated):
    Mendeteksi tipe file berdasarkan kolom kunci spesifik sesuai standarisasi sistem.
    """
    # Standarisasi nama kolom: Uppercase dan Hilangkan Spasi
    cols = [str(c).upper().strip() for c in df.columns]
    
    # 1. Deteksi MC (Master Catat) -> Kunci Utama: ZONA_NOVAK
    if 'ZONA_NOVAK' in cols:
        return 'mc'
    
    # 2. Deteksi MB (Master Bayar) -> Kunci Utama: TGL_BAYAR
    if 'TGL_BAYAR' in cols:
        return 'mb'
    
    # 3. Deteksi Collection -> Kunci Utama: PAY_DATE
    if 'PAY_DATE' in cols:
        return 'collection'
    
    # 4. Deteksi Ardebt -> Kunci Utama: JUMLAH
    # Ditambah pengecekan volume/periode_bill untuk membedakan dengan rute jika perlu
    if 'JUMLAH' in cols:
        return 'ardebt'
    
    # 5. Deteksi Rute -> Kunci Utama: PETUGAS
    if 'PETUGAS' in cols:
        return 'rute'
    
    return None

def parse_zona_novak(val):
    """
    INTELIJEN EKSTRAKSI ZONA_NOVAK:
    Memecah string (misal: 350960217) menjadi komponen operasional.
    
    Logic:
    35          -> RAYON (2 digit)
    096         -> PC (3 digit)
    02          -> EZ (2 digit)
    096/02      -> PCEZ (Gabungan PC/EZ)
    17          -> BLOK (2 digit)
    """
    if pd.isna(val) or val == '':
        return None

    # Bersihkan dari .0 (efek float excel) dan ambil string murni
    s = str(val).strip().split('.')[0]
    
    # Pastikan panjang 9 digit (padding nol di depan jika data dari excel terpotong)
    if len(s) < 9:
        s = s.zfill(9)
    
    # Ekstraksi berbasis posisi string (Slicing)
    return {
        'rayon': s[0:2],             # Digit 1-2
        'pc': s[2:5],                # Digit 3-5
        'ez': s[5:7],                # Digit 6-7
        'pcez': f"{s[2:5]}/{s[5:7]}",# Format Gabungan
        'blok': s[7:9]               # Digit 8-9
    }

def detect_file_period(df, file_type):
    """
    AUTOPILOT PERIOD:
    Data bulan N adalah target kerja bulan N+1.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    try:
        if file_type in ['rute', None]:
            return None, None

        date_col = get_date_column(file_type, cols)
        
        # Ambil sampel baris pertama yang valid
        valid_rows = df[df[date_col].notna()] if date_col in df.columns else pd.DataFrame()
        if valid_rows.empty:
            return None, None
            
        sample_row = valid_rows.iloc[0]
        raw_date = str(sample_row.get(date_col))
        dt = parse_flexible_date(raw_date)
        
        if dt:
            # MC & MB: Data bulan lalu digunakan untuk kerja bulan depan
            if file_type in ['mc', 'mb', 'ardebt']:
                dt = dt + relativedelta(months=1)
            
            return dt.strftime('%m'), dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Smart Period Detection Warning: {e}")
        
    return None, None

def get_date_column(file_type, cols):
    """Mapping acuan kolom tanggal sesuai standarisasi baru."""
    mapping = {
        'mc': 'ZONA_NOVAK', # Periode bisa dideteksi dari rincian MC jika tersedia
        'mb': 'TGL_BAYAR',
        'collection': 'PAY_DATE',
        'ardebt': 'PERIODE_BILL'
    }
    # Khusus MC jika tidak ada kolom tanggal spesifik, return kolom yang ada
    if file_type == 'mc' and 'TGL_CATAT' in cols: return 'TGL_CATAT'
    
    col_name = mapping.get(file_type)
    return col_name if col_name in cols else None

def parse_flexible_date(date_str):
    """Mengubah string tanggal liar menjadi objek datetime."""
    if not date_str or str(date_str).lower() in ('nan', 'none', ''):
        return None

    date_str = str(date_str).split(' ')[0].replace("'", "").strip()
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d%m%Y', '%m%Y', '%Y%m%d']
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
    return None
