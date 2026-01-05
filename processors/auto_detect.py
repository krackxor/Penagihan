import pandas as pd
from datetime import datetime

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan keberadaan kolom kunci."""
    cols = [str(c).upper().strip() for c in df.columns]
    
    # 1. Deteksi MC (Master Catat) - Berdasarkan ZONA_NOVAK dan TGL_CATAT
    if 'ZONA_NOVAK' in cols and ('NAMA_PEL' in cols or 'TGL_CATAT' in cols):
        return 'mc'
    
    # 2. Deteksi MB (Master Bayar) - Berdasarkan TGL_BAYAR
    if 'TGL_BAYAR' in cols and ('BEATETAP' in cols or 'NOMEN' in cols):
        return 'mb'
    
    # 3. Deteksi Collection (Daily) - Berdasarkan PAY_DT
    if 'PAY_DT' in cols or 'AMT_COLLECT' in cols:
        return 'collection'
    
    # 4. Deteksi Ardebt (Tunggakan)
    if 'PERIODE_BILL' in cols and 'JUMLAH' in cols:
        return 'ardebt'
    
    # 5. Deteksi Rute (Mapping Petugas)
    if 'PCEZ' in cols and 'PETUGAS' in cols:
        return 'rute'
    
    # 6. Deteksi Mainbill (Sesuai SOP)
    if 'FREEZE_DT' in cols:
        return 'mainbill'

    # 7. Deteksi SBR (Sesuai SOP)
    if 'CMR_RD_DATE' in cols:
        return 'sbr'
    
    return None

def detect_file_period(df, file_type):
    """
    Mengekstrak Periode (Bulan & Tahun) secara otomatis dari isi file.
    Logika: Mengambil sampel baris pertama dari kolom acuan tanggal.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    df.columns = cols # Standarisasi kolom menjadi uppercase
    
    try:
        # Ambil sampel data baris pertama yang tidak kosong
        sample_row = df.dropna(subset=[get_date_column(file_type, cols)]).iloc[0] if get_date_column(file_type, cols) else None
        
        if sample_row is not None:
            raw_date = str(sample_row.get(get_date_column(file_type, cols)))
            
            # Konversi berbagai format tanggal menjadi objek datetime
            # Mendukung format: 19-06-2025, 2025-06-19, 19/06/2025, atau 112025
            dt = parse_flexible_date(raw_date)
            
            if dt:
                return dt.strftime('%m'), dt.strftime('%Y')

        # Fallback ke logika lama Anda jika parsing tanggal gagal
        if file_type == 'mc' and 'NAMA_BLN1' in cols:
            return str(df.iloc[0].get('NAMA_BLN1')).zfill(2), str(df.iloc[0].get('TAHUN1'))
            
        elif file_type == 'mb' and 'BULAN_REK' in cols:
            val = str(df.iloc[0].get('BULAN_REK'))
            return val[:2], val[2:]

    except Exception as e:
        print(f"Debug Period Detection: {e}")
        
    return None, None

def get_date_column(file_type, cols):
    """Pemetaan jenis data ke nama kolom tanggal acuan sesuai SOP."""
    mapping = {
        'mc': 'TGL_CATAT',
        'mb': 'TGL_BAYAR',
        'collection': 'PAY_DT',
        'mainbill': 'FREEZE_DT',
        'sbr': 'CMR_RD_DATE'
    }
    col_name = mapping.get(file_type)
    return col_name if col_name in cols else None

def parse_flexible_date(date_str):
    """Helper untuk mengubah string tanggal acak menjadi objek datetime."""
    date_str = date_str.split(' ')[0] # Ambil tanggal saja jika ada jam
    formats = [
        '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', 
        '%d%m%Y', '%m%Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
            
    # Kasus khusus BULAN_REK: 112025
    if len(date_str) == 6 and date_str.isdigit():
        try:
            return datetime.strptime(date_str, '%m%Y')
        except:
            pass
            
    return None
