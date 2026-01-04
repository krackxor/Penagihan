import pandas as pd

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan fingerprint kolom"""
    cols = [str(c).upper().strip() for c in df.columns]
    
    # Deteksi MC (Master Catat)
    if 'ZONA_NOVAK' in cols and 'NAMA_PEL' in cols:
        return 'mc'
    
    # Deteksi Rute (Mapping Petugas) - Diletakkan di atas agar tidak tertukar
    if 'PCEZ' in cols and 'PETUGAS' in cols:
        return 'rute'
    
    # Deteksi MB (Master Bayar)
    if 'TGL_BAYAR' in cols and 'BEATETAP' in cols:
        return 'mb'
    
    # Deteksi Collection (Daily)
    if 'AMT_COLLECT' in cols or 'PAY_DT' in cols:
        return 'collection'
    
    # Deteksi Ardebt (Tunggakan)
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    return None

def detect_file_period(df, file_type):
    """Mendeteksi bulan dan tahun dari isi file untuk keperluan logging/history"""
    cols = [str(c).upper().strip() for c in df.columns]
    
    try:
        if file_type == 'mc' and 'NAMA_BLN1' in cols:
            bulan = str(df.iloc[0].get('NAMA_BLN1'))
            tahun = str(df.iloc[0].get('TAHUN1'))
            return bulan, tahun
            
        elif file_type == 'collection' and 'BILL_PERIOD' in cols:
            period = str(df.iloc[0].get('BILL_PERIOD')) # Contoh: Nov/2025
            if '/' in period:
                return period.split('/')[0], period.split('/')[1]
                
        elif file_type == 'mb' and 'BULAN_REK' in cols:
            val = str(df.iloc[0].get('BULAN_REK')) # Contoh: 112025
            if len(val) >= 6:
                return val[:2], val[2:]
    except:
        pass
        
    return None, None
