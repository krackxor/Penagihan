import pandas as pd

def detect_file_period(df, file_type):
    """
    Menentukan periode berdasarkan Field Acuan (SOP Poin 2)
    """
    # Mapping Field Acuan sesuai SOP
    acuan = {
        'mc': 'TGL_CATAT',
        'mb': 'TGL_BAYAR',
        'collection': 'PAY_DT',
        'sbrs': 'cmr_rd_date',
        'mainbill': 'FREEZE_DT',
        'ardebt': 'PERIODE_BILL'
    }
    
    date_col = acuan.get(file_type)
    if not date_col or date_col not in df.columns:
        return None, None

    # Ambil contoh data pertama
    raw_val = df[date_col].iloc[0]
    
    # Konversi format tanggal (mendukung format Excel & String)
    try:
        if isinstance(raw_val, (int, float)): # Format angka Excel
            date_obj = pd.to_datetime(raw_val, unit='D', origin='1899-12-30')
        else:
            date_obj = pd.to_datetime(raw_val, dayfirst=True)
            
        return int(date_obj.month), int(date_obj.year)
    except:
        return None, None
