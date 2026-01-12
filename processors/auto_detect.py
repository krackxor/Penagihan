import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    SINERGI DETECTOR (V5.3):
    Mendeteksi tipe file berdasarkan kolom kunci spesifik dari file asli.
    """
    # Standarisasi nama kolom: Uppercase dan Hilangkan Spasi
    cols = [str(c).upper().strip() for c in df.columns]
    
    # 1. Deteksi MC (Master Catat) -> Kunci Utama: ZONA_NOVAK
    if 'ZONA_NOVAK' in cols and 'TGL_CATAT' in cols:
        return 'mc'
    
    # 2. Deteksi MB (Master Bayar) -> Kunci Utama: TGL_BAYAR
    if 'TGL_BAYAR' in cols:
        return 'mb'
    
    # 3. Deteksi Collection -> Kunci Utama: PAY_DT (Disesuaikan dengan file asli)
    if 'PAY_DT' in cols:
        return 'collection'
    
    # 4. Deteksi Ardebt -> Kunci Utama: PERIODE_BILL
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    # 5. Deteksi Rute -> Kunci Utama: PETUGAS
    if 'PETUGAS' in cols and 'PCEZ' in cols:
        return 'rute'
    
    return None

def parse_flexible_date(date_str):
    """
    Mengubah string tanggal atau serial excel menjadi objek datetime.
    Mendukung angka seperti 45987.0 dari file MB/MC Anda.
    """
    if not date_str or str(date_str).lower() in ('nan', 'none', ''):
        return None

    s_date = str(date_str).split(' ')[0].replace("'", "").strip()
    
    # Cek jika format adalah Serial Date Excel (angka murni)
    try:
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
    """Mapping acuan kolom tanggal sesuai standarisasi file asli."""
    mapping = {
        'mc': 'TGL_CATAT',      # Dari file MC 1125.xls
        'mb': 'TGL_BAYAR',      # Dari file MB 1125.xls
        'collection': 'PAY_DT', # Dari file Collection 1225.xls
        'ardebt': 'PERIODE_BILL'
    }
    col_name = mapping.get(file_type)
    return col_name if col_name in cols else None

def detect_file_period(df, file_type):
    """
    AUTOPILOT PERIOD:
    Data bulan N (November) menjadi target bulan N+1 (Desember).
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    try:
        if file_type in ['rute', None]:
            return None, None

        date_col = get_date_column(file_type, cols)
        if not date_col:
            return None, None
        
        # Ambil sampel baris pertama yang berisi data
        valid_rows = df[df[date_col].notna()]
        if valid_rows.empty:
            return None, None
            
        raw_date = str(valid_rows.iloc[0].get(date_col))
        dt = parse_flexible_date(raw_date)
        
        if dt:
            # Sinergi: MC, MB, & Ardebt dimajukan 1 bulan untuk periode kerja
            if file_type in ['mc', 'mb', 'ardebt']:
                dt = dt + relativedelta(months=1)
            
            return dt.strftime('%m'), dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Smart Period Detection Warning: {e}")
        
    return None, None

def parse_zona_novak(val):
    """Ekstraksi PCEZ dari ZONA_NOVAK (350960217 -> 096/02)."""
    if pd.isna(val) or val == '':
        return None
    s = str(val).strip().split('.')[0]
    if len(s) < 9:
        s = s.zfill(9)
    return {
        'rayon': s[0:2],
        'pc': s[2:5],
        'ez': s[5:7],
        'pcez': f"{s[2:5]}/{s[5:7]}",
        'blok': s[7:9]
    }
