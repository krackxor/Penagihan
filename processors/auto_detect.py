import pandas as pd
from datetime import datetime

def detect_file_period(df, file_type):
    """
    Menentukan periode berdasarkan Field Acuan sesuai SOP Poin 2
    """
    date_column = None
    
    # Mapping Field Acuan sesuai SOP
    if file_type == 'mc': date_column = 'TGL_CATAT'
    elif file_type == 'mb': date_column = 'TGL_BAYAR'
    elif file_type == 'collection': date_column = 'PAY_DT'
    elif file_type == 'sbrs': date_column = 'cmr_rd_date'
    elif file_type == 'mainbill': date_column = 'FREEZE_DT'
    
    if date_column and date_column in df.columns:
        # Mengambil sampel tanggal pertama untuk menentukan periode
        sample_date = df[date_column].iloc[0]
        
        # Konversi format Excel date jika diperlukan
        if isinstance(sample_date, float) or isinstance(sample_date, int):
            date_obj = pd.to_datetime(sample_date, unit='D', origin='1899-12-30')
        else:
            date_obj = pd.to_datetime(sample_date)
            
        return date_obj.month, date_obj.year
    
    # Fallback untuk AR/Debt (Sesuai SOP: Sesuai Bill)
    if file_type == 'ardebt' and 'PERIODE_BILL' in df.columns:
        # Logika khusus untuk mengambil periode dari kolom PERIODE_BILL
        return int(df['PERIODE_BILL'].iloc[0]), 2025 # Contoh tahun statis atau dinamis
        
    return None, None
