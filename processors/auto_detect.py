import pandas as pd
from datetime import datetime

def identify_file_type(df):
    """Mendeteksi tipe file berdasarkan keberadaan kolom kunci."""
    # Pastikan nama kolom dibersihkan dari spasi dan diubah ke uppercase
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
    
    # 4. Deteksi Ardebt (Tunggakan Berekor) - BERDASARKAN INSTRUKSI TERBARU
    # Menggunakan kolom kunci: PERIODE_BILL dan JUMLAH
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
        # Jika tipe file adalah rute, tidak perlu deteksi periode
        if file_type == 'rute':
            return None, None

        # Ambil sampel data baris pertama yang tidak kosong
        date_col = get_date_column(file_type, cols)
        sample_row = df.dropna(subset=[date_col]).iloc[0] if date_col else None
        
        if sample_row is not None:
            raw_date = str(sample_row.get(date_col))
            
            # Konversi berbagai format tanggal menjadi objek datetime
            dt = parse_flexible_date(raw_date)
            
            if dt:
                return dt.strftime('%m'), dt.strftime('%Y')

        # Fallback ke logika lama jika parsing tanggal fleksibel gagal
        if file_type == 'mc' and 'NAMA_BLN1' in cols:
            return str(df.iloc[0].get('NAMA_BLN1')).zfill(2), str(df.iloc[0].get('TAHUN1'))
            
        elif file_type == 'mb' and 'BULAN_REK' in cols:
            val = str(df.iloc[0].get('BULAN_REK'))
            # Menangani format 112025 (MMYYYY)
            if len(val) == 6:
                return val[:2], val[2:]
            return val, None

    except Exception as e:
        print(f"Debug Period Detection Error: {e}")
        
    return None, None

def get_date_column(file_type, cols):
    """Pemetaan jenis data ke nama kolom tanggal acuan sesuai SOP."""
    mapping = {
        'mc': 'TGL_CATAT',
        'mb': 'TGL_BAYAR',
        'collection': 'PAY_DT',
        'mainbill': 'FREEZE_DT',
        'sbr': 'CMR_RD_DATE',
        'ardebt': 'PERIODE_BILL' # Ardebt menggunakan periode_bill sebagai acuan
    }
    col_name = mapping.get(file_type)
    return col_name if col_name in cols else None

def parse_flexible_date(date_str):
    """Helper untuk mengubah string tanggal acak menjadi objek datetime."""
    if not date_str or date_str.lower() == 'nan':
        return None

    # Bersihkan string: ambil bagian tanggal saja jika ada jam/time
    date_str = date_str.split(' ')[0].replace("'", "").strip()
    
    formats = [
        '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', 
        '%d%m%Y', '%m%Y', '%b/%Y', '%m-%Y'
    ]
    
    # Coba satu per satu format standar
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
            
    # Kasus khusus format bulan dengan teks (Contoh: MEI/2025 atau JAN-2025)
    try:
        clean_date = date_str.replace('/', '-').upper()
        # Mapping bulan singkat Indonesia ke Inggris
        month_map = {
            'MEI': 'MAY', 'AGU': 'AUG', 'DES': 'DEC'
        }
        for indo, eng in month_map.items():
            clean_date = clean_date.replace(indo, eng)
        return datetime.strptime(clean_date, '%b-%Y')
    except:
        pass
            
    # Kasus khusus 6 digit: 112025 (MMYYYY)
    if len(date_str) == 6 and date_str.isdigit():
        try:
            return datetime.strptime(date_str, '%m%Y')
        except:
            pass
            
    return None
