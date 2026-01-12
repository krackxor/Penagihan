import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    SINERGI DETECTOR (V6.2):
    Mendeteksi tipe file berdasarkan kolom kunci spesifik.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols:
        return 'mc'
    
    if 'TGL_BAYAR' in cols:
        return 'mb'
    
    if 'PAY_DT' in cols:
        return 'collection'
    
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    if 'PETUGAS' in cols and 'PCEZ' in cols:
        return 'rute'
    
    return None

def parse_flexible_date(date_val):
    """
    Mengubah input (String/Serial Excel) menjadi objek datetime.
    """
    if not date_val or str(date_val).lower() in ('nan', 'none', ''):
        return None

    s_date = str(date_val).split(' ')[0].replace("'", "").strip()
    try:
        # Menangani Serial Date Excel (Contoh: 45987.0)
        if s_date.replace('.', '').isdigit():
            return datetime(1899, 12, 30) + timedelta(days=float(s_date))
    except:
        pass

    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d%m%Y', '%m%Y', '%Y%m%d']
    for fmt in formats:
        try:
            return datetime.strptime(s_date, fmt)
        except:
            continue
    return None

def get_date_column(file_type, cols):
    mapping = {
        'mc': 'TGL_CATAT',
        'mb': 'TGL_BAYAR',
        'collection': 'PAY_DT',
        'ardebt': 'PERIODE_BILL'
    }
    col_name = mapping.get(file_type)
    return col_name if col_name in cols else None

def detect_file_period(df, file_type):
    """
    LOGIKA PERIODE V6.1 (ULTRA-LOCK):
    Mengunci satu periode untuk seluruh isi file berdasarkan baris pertama.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    try:
        if file_type in ['rute', None]:
            return None, None

        date_col = get_date_column(file_type, cols)
        if not date_col:
            return None, None
        
        # MENGUNCI PERIODE BERDASARKAN SAMPEL PERTAMA YANG VALID
        valid_rows = df[df[date_col].notna()]
        if valid_rows.empty:
            return None, None
            
        raw_date = valid_rows.iloc[0].get(date_col)
        dt = parse_flexible_date(raw_date)
        
        if dt:
            # MC/MB/Ardebt: Target Kerja N+1 (Nov -> Des)
            if file_type in ['mc', 'mb', 'ardebt']:
                target_dt = dt + relativedelta(months=1)
            
            # Collection: Realisasi Tetap (Des -> Des)
            elif file_type == 'collection':
                target_dt = dt 

            return target_dt.strftime('%m'), target_dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Smart Period Detection Warning: {e}")
        
    return None, None

def autopilot_extract_zona(val):
    """
    FIXED: Mengubah nama fungsi dari parse_zona_novak menjadi autopilot_extract_zona
    agar sinkron dengan api/upload.py.
    """
    if pd.isna(val) or str(val).strip() == '':
        return None
    # Membersihkan karakter non-digit dan mengambil bagian depan sebelum titik
    s = ''.join(filter(str.isdigit, str(val).split('.')[0])).zfill(9)
    return {
        'rayon': s[0:2],
        'pc': s[2:5],
        'ez': s[5:7],
        'pcez': f"{s[2:5]}/{s[5:7]}",
        'blok': s[7:9]
    }

# Alias tambahan untuk keamanan sinkronisasi
parse_zona_novak = autopilot_extract_zona
