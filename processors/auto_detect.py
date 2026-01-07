import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan keberadaan kolom kunci."""
    # Pastikan nama kolom dibersihkan dari spasi dan diubah ke uppercase
    cols = [str(c).upper().strip() for c in df.columns]
    
    # 1. Deteksi MC (Master Catat)
    if 'ZONA_NOVAK' in cols and ('NAMA_PEL' in cols or 'TGL_CATAT' in cols):
        return 'mc'
    
    # 2. Deteksi MB (Master Bayar)
    if 'TGL_BAYAR' in cols and ('BEATETAP' in cols or 'NOMEN' in cols):
        return 'mb'
    
    # 3. Deteksi Collection (Daily)
    if 'PAY_DT' in cols or 'AMT_COLLECT' in cols:
        return 'collection'
    
    # 4. Deteksi Ardebt (Tunggakan Berekor)
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    # 5. Deteksi Rute (Mapping Petugas)
    if 'PCEZ' in cols and 'PETUGAS' in cols:
        return 'rute'
    
    # 6. Deteksi Mainbill
    if 'FREEZE_DT' in cols:
        return 'mainbill'

    # 7. Deteksi SBR
    if 'CMR_RD_DATE' in cols:
        return 'sbr'
    
    return None

def detect_file_period(df, file_type):
    """
    Mengekstrak Periode secara otomatis.
    LOGIKA: 
    - MC, MB, ARDEBT: Data bulan N otomatis diset ke periode N+1 (Periode Penagihan).
    - Collection: Tetap sesuai bulan transaksi di file.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    df.columns = cols 
    
    try:
        if file_type == 'rute':
            return None, None

        date_col = get_date_column(file_type, cols)
        sample_row = df.dropna(subset=[date_col]).iloc[0] if date_col else None
        
        if sample_row is not None:
            raw_date = str(sample_row.get(date_col))
            dt = parse_flexible_date(raw_date)
            
            if dt:
                # --- LOGIKA OTOMATISASI PERIODE +1 ---
                # MC, MB, dan ARDEBT (Data bulan lalu ditagih bulan depan)
                if file_type in ['mc', 'mb', 'ardebt']:
                    dt = dt + relativedelta(months=1)
                    print(f"DEBUG: File {file_type.upper()} terdeteksi, periode disesuaikan ke +1: {dt.strftime('%m-%Y')}")
                
                return dt.strftime('%m'), dt.strftime('%Y')

        # Fallback lama dengan penyesuaian +1
        if file_type == 'mc' and 'NAMA_BLN1' in cols:
            b = int(df.iloc[0].get('NAMA_BLN1'))
            t = int(df.iloc[0].get('TAHUN1'))
            dt_fb = datetime(t, b, 1) + relativedelta(months=1)
            return dt_fb.strftime('%m'), dt_fb.strftime('%Y')
            
        elif file_type == 'mb' and 'BULAN_REK' in cols:
            val = str(df.iloc[0].get('BULAN_REK'))
            if len(val) == 6:
                b, t = int(val[:2]), int(val[2:])
                dt_fb = datetime(t, b, 1) + relativedelta(months=1)
                return dt_fb.strftime('%m'), dt_fb.strftime('%Y')

    except Exception as e:
        print(f"Debug Period Detection Error: {e}")
        
    return None, None

def get_date_column(file_type, cols):
    """Pemetaan jenis data ke nama kolom tanggal acuan."""
    mapping = {
        'mc': 'TGL_CATAT',
        'mb': 'TGL_BAYAR',
        'collection': 'PAY_DT',
        'mainbill': 'FREEZE_DT',
        'sbr': 'CMR_RD_DATE',
        'ardebt': 'PERIODE_BILL' 
    }
    col_name = mapping.get(file_type)
    return col_name if col_name in cols else None

def parse_flexible_date(date_str):
    """Helper untuk mengubah string tanggal acak menjadi objek datetime."""
    if not date_str or date_str.lower() == 'nan':
        return None

    date_str = date_str.split(' ')[0].replace("'", "").strip()
    
    formats = [
        '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', 
        '%d%m%Y', '%m%Y', '%b/%Y', '%m-%Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
            
    # Kasus khusus teks bulan (Indo ke Inggris)
    try:
        clean_date = date_str.replace('/', '-').upper()
        month_map = {'MEI': 'MAY', 'AGU': 'AUG', 'DES': 'DEC'}
        for indo, eng in month_map.items():
            clean_date = clean_date.replace(indo, eng)
        return datetime.strptime(clean_date, '%b-%Y')
    except:
        pass
            
    return None
