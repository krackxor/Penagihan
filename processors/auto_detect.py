import pandas as pd

def identify_file_type(df):
    """Mendeteksi tipe file - Fungsi Anda tetap ada, Rute ditambahkan di akhir"""
    cols = [str(c).upper().strip() for c in df.columns]
    
    # 1. Deteksi MC (Master Catat) - Fungsi Lama Anda
    if 'ZONA_NOVAK' in cols and 'NAMA_PEL' in cols:
        return 'mc'
    
    # 2. Deteksi MB (Master Bayar) - Fungsi Lama Anda
    if 'TGL_BAYAR' in cols and 'BEATETAP' in cols:
        return 'mb'
    
    # 3. Deteksi Collection (Daily) - Fungsi Lama Anda
    if 'AMT_COLLECT' in cols or 'PAY_DT' in cols:
        return 'collection'
    
    # 4. Deteksi Ardebt (Tunggakan) - Fungsi Lama Anda
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    # 5. Deteksi Rute (Mapping Petugas) - Fungsi Baru
    if 'PCEZ' in cols and 'PETUGAS' in cols:
        return 'rute'
    
    return None

def detect_file_period(df, file_type):
    """Fungsi Deteksi Periode Milik Anda - 100% UTUH"""
    cols = [str(c).upper().strip() for c in df.columns]
    
    try:
        if file_type == 'mc' and 'NAMA_BLN1' in cols:
            # Ambil dari baris pertama
            bulan = df.iloc[0].get('NAMA_BLN1')
            tahun = df.iloc[0].get('TAHUN1')
            return bulan, tahun
            
        elif file_type == 'collection' and 'BILL_PERIOD' in cols:
            period = str(df.iloc[0].get('BILL_PERIOD')) # Contoh: Nov/2025
            if '/' in period:
                return period.split('/')[0], period.split('/')[1]
                
        elif file_type == 'mb' and 'BULAN_REK' in cols:
            val = str(df.iloc[0].get('BULAN_REK')) # Contoh: 112025
            return val[:2], val[2:]
    except:
        pass
        
    return None, None
