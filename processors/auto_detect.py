import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    Mendeteksi tipe file berdasarkan keberadaan kolom kunci secara robust.
    """
    # Pastikan nama kolom dibersihkan dari spasi dan diubah ke uppercase
    cols = [str(c).upper().strip() for c in df.columns]
    
    # 1. Deteksi MC (Master Catat)
    if 'ZONA_NOVAK' in cols and ('NAMA_PEL' in cols or 'TGL_CATAT' in cols or 'NAMA_BLN1' in cols):
        return 'mc'
    
    # 2. Deteksi MB (Master Bayar)
    if 'TGL_BAYAR' in cols and ('BEATETAP' in cols or 'NOMEN' in cols or 'BULAN_REK' in cols):
        return 'mb'
    
    # 3. Deteksi Collection (Daily)
    if 'PAY_DT' in cols or 'AMT_COLLECT' in cols or 'NOTAG' in cols:
        # Tambahan deteksi 'NOTAG' untuk konsistensi skema collection baru
        if 'PAY_DT' in cols or 'NOTAG' in cols:
            return 'collection'
    
    # 4. Deteksi Ardebt (Tunggakan Berekor)
    if 'PERIODE_BILL' in cols and ('JUMLAH' in cols or 'VOLUME' in cols):
        return 'ardebt'
    
    # 5. Deteksi Rute (Mapping Petugas)
    if 'PCEZ' in cols and 'PETUGAS' in cols:
        return 'rute'
    
    # 6. Deteksi Mainbill (Freeze Data)
    if 'FREEZE_DT' in cols:
        return 'mainbill'

    # 7. Deteksi SBR (Stand Baru)
    if 'CMR_RD_DATE' in cols:
        return 'sbr'
    
    return None

def detect_file_period(df, file_type):
    """
    Mengekstrak Periode secara otomatis dengan logika bisnis N+1.
    LOGIKA: 
    - MC, MB, ARDEBT: Data bulan N otomatis diset ke periode N+1 (Periode Penagihan).
    - Collection: Tetap sesuai bulan transaksi di file.
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    try:
        if file_type == 'rute' or file_type is None:
            return None, None

        date_col = get_date_column(file_type, cols)
        
        # Mengambil sampel baris pertama yang tidak kosong pada kolom tanggal
        valid_rows = df[df[date_col].notna()] if date_col in df.columns else pd.DataFrame()
        sample_row = valid_rows.iloc[0] if not valid_rows.empty else None
        
        if sample_row is not None:
            raw_date = str(sample_row.get(date_col))
            dt = parse_flexible_date(raw_date)
            
            if dt:
                # --- LOGIKA OTOMATISASI PERIODE +1 ---
                # MC, MB, dan ARDEBT (Data hasil kerja bulan lalu ditagih bulan depan)
                if file_type in ['mc', 'mb', 'ardebt']:
                    dt = dt + relativedelta(months=1)
                
                return dt.strftime('%m'), dt.strftime('%Y')

        # --- FALLBACK LOGIC UNTUK FORMAT KHUSUS ---
        if file_type == 'mc' and 'NAMA_BLN1' in cols and 'TAHUN1' in cols:
            b = int(float(sample_row.get('NAMA_BLN1'))) if sample_row is not None else 0
            t = int(float(sample_row.get('TAHUN1'))) if sample_row is not None else 0
            if b > 0 and t > 0:
                dt_fb = datetime(t, b, 1) + relativedelta(months=1)
                return dt_fb.strftime('%m'), dt_fb.strftime('%Y')
            
        elif file_type == 'mb' and 'BULAN_REK' in cols:
            val = str(sample_row.get('BULAN_REK')).split('.')[0] if sample_row is not None else ""
            if len(val) == 6: # Format MMYYYY
                b, t = int(val[:2]), int(val[2:])
                dt_fb = datetime(t, b, 1) + relativedelta(months=1)
                return dt_fb.strftime('%m'), dt_fb.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Error Period Detection: {e}")
        
    return None, None

def get_date_column(file_type, cols):
    """Pemetaan jenis data ke nama kolom tanggal acuan utama."""
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
    """Helper untuk mengubah string tanggal acak menjadi objek datetime secara robust."""
    if not date_str or str(date_str).lower() in ('nan', 'none', ''):
        return None

    # Bersihkan karakter aneh dan ambil bagian tanggal saja (sebelum spasi)
    date_str = str(date_str).split(' ')[0].replace("'", "").strip()
    
    # Daftar format tanggal yang umum ditemukan di Excel
    formats = [
        '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', 
        '%d%m%Y', '%m%Y', '%b-%Y', '%b/%Y', '%m-%Y',
        '%Y%m%d'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
            
    # Penanganan khusus untuk nama bulan Indonesia
    try:
        clean_date = date_str.replace('/', '-').upper()
        # Map bulan Indonesia ke Inggris
        month_map = {
            'JAN': 'JAN', 'PEB': 'FEB', 'FEB': 'FEB', 'MAR': 'MAR', 
            'APR': 'APR', 'MEI': 'MAY', 'JUN': 'JUN', 'JUL': 'JUL', 
            'AGU': 'AUG', 'SEP': 'SEP', 'OKT': 'OCT', 'NOP': 'NOV', 
            'NOV': 'NOV', 'DES': 'DEC'
        }
        for indo, eng in month_map.items():
            if indo in clean_date:
                clean_date = clean_date.replace(indo, eng)
                break
        
        # Coba parse setelah translasi bulan
        for fmt in ['%d-%b-%Y', '%b-%Y', '%d-%b-%y']:
            try:
                return datetime.strptime(clean_date, fmt)
            except:
                continue
    except:
        pass
            
    return None
