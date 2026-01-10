import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

def identify_file_type(df):
    """
    SINERGI DETECTOR:
    Mendeteksi tipe file berdasarkan sidik jari (fingerprint) kolom kunci.
    Logika Smart: Membersihkan whitespace dan case-sensitivity secara otomatis.
    """
    # Standarisasi nama kolom: Uppercase dan Hilangkan Spasi (Smart Cleaning)
    cols = [str(c).upper().strip() for c in df.columns]
    
    # 1. Deteksi MC (Master Catat / Master Pelanggan)
    # Kunci: ZONA_NOVAK adalah identitas rute unik di file MC
    if 'ZONA_NOVAK' in cols and any(k in cols for k in ['NAMA_PEL', 'TGL_CATAT', 'NAMA_BLN1']):
        return 'mc'
    
    # 2. Deteksi MB (Master Bayar / Pelanggan Lunas Kantor)
    # Kunci: TGL_BAYAR dikombinasikan dengan rincian biaya (BEATETAP)
    if 'TGL_BAYAR' in cols and any(k in cols for k in ['BEATETAP', 'BULAN_REK', 'LKS_BAYAR']):
        return 'mb'
    
    # 3. Deteksi Collection (Daily Collection / Setoran Harian)
    # Kunci: PAY_DT atau AMT_COLLECT (Rupiah masuk)
    if any(k in cols for k in ['PAY_DT', 'AMT_COLLECT', 'NOTAG']):
        return 'collection'
    
    # 4. Deteksi Ardebt (Tunggakan Berekor / Piutang Lama)
    # Kunci: PERIODE_BILL (menunjukkan akumulasi bulan tunggakan)
    if 'PERIODE_BILL' in cols and ('JUMLAH' in cols or 'VOLUME' in cols):
        return 'ardebt'
    
    # 5. Deteksi Rute (Mapping Petugas Lapangan)
    # Kunci: Pasangan PCEZ dan Nama Petugas
    if 'PCEZ' in cols and 'PETUGAS' in cols:
        return 'rute'
    
    # 6. Deteksi SBR (Stand Baru / Hasil Baca Meter)
    if 'CMR_RD_DATE' in cols or 'MET_READ_DATE' in cols:
        return 'sbr'
    
    return None

def detect_file_period(df, file_type):
    """
    AUTOPILOT PERIOD:
    Mengekstrak Periode secara otomatis dengan logika bisnis N+1.
    Logika Bisnis: 
    - MC, MB, ARDEBT: Data bulan N (misal Nov) adalah target kerja bulan N+1 (Des).
    - Collection: Tetap di bulan transaksi (transaksi Des ya periode Des).
    """
    cols = [str(c).upper().strip() for c in df.columns]
    
    try:
        # File rute tidak memiliki periode (bersifat master data tetap)
        if file_type in ['rute', None]:
            return None, None

        date_col = get_date_column(file_type, cols)
        
        # Ambil sampel baris pertama yang valid (bukan NaN)
        valid_rows = df[df[date_col].notna()] if date_col in df.columns else pd.DataFrame()
        if valid_rows.empty:
            return fallback_period_logic(df, file_type, cols)
            
        sample_row = valid_rows.iloc[0]
        raw_date = str(sample_row.get(date_col))
        dt = parse_flexible_date(raw_date)
        
        if dt:
            # --- STRATEGI SINERGI PERIODE N+1 ---
            # Data MC/MB bulan ini adalah bahan tagihan untuk petugas bulan depan
            if file_type in ['mc', 'mb', 'ardebt']:
                dt = dt + relativedelta(months=1)
            
            return dt.strftime('%m'), dt.strftime('%Y')

    except Exception as e:
        print(f"⚠️ Smart Period Detection Warning: {e}")
        
    return fallback_period_logic(df, file_type, cols)

def fallback_period_logic(df, file_type, cols):
    """
    LOGIKA CADANGAN (AUTOPILOT):
    Jika kolom tanggal utama rusak/kosong, cari di kolom alternatif.
    """
    sample_row = df.iloc[0] if not df.empty else None
    if sample_row is None: return None, None

    # Fallback MC: Pakai NAMA_BLN1 (Angka Bulan)
    if file_type == 'mc' and 'NAMA_BLN1' in cols:
        try:
            b = int(float(sample_row.get('NAMA_BLN1')))
            t = int(float(sample_row.get('TAHUN1')))
            dt = datetime(t, b, 1) + relativedelta(months=1)
            return dt.strftime('%m'), dt.strftime('%Y')
        except: pass

    # Fallback MB: Pakai BULAN_REK (MMYYYY)
    if file_type == 'mb' and 'BULAN_REK' in cols:
        val = str(sample_row.get('BULAN_REK')).split('.')[0]
        if len(val) == 6:
            b, t = int(val[:2]), int(val[2:])
            dt = datetime(t, b, 1) + relativedelta(months=1)
            return dt.strftime('%m'), dt.strftime('%Y')

    return None, None

def get_date_column(file_type, cols):
    """Mapping jenis data ke kolom tanggal acuan (Standardisasi Nama)."""
    mapping = {
        'mc': 'TGL_CATAT',
        'mb': 'TGL_BAYAR',
        'collection': 'PAY_DT',
        'ardebt': 'PERIODE_BILL',
        'sbr': 'CMR_RD_DATE'
    }
    col_name = mapping.get(file_type)
    return col_name if col_name in cols else None

def parse_flexible_date(date_str):
    """
    SMART DATE PARSER:
    Mengubah string tanggal 'liar' dari Excel menjadi objek Python Datetime.
    Mendukung format Indonesia (Mei, Okt, Des) dan format Excel Serial.
    """
    if not date_str or str(date_str).lower() in ('nan', 'none', ''):
        return None

    # Bersihkan kutipan dan spasi (sering terjadi di ekspor Excel)
    date_str = str(date_str).split(' ')[0].replace("'", "").strip()
    
    # Daftar format prioritas
    formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d%m%Y', '%m%Y']
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
            
    # --- SMART AUTO-CORRECTION: Bulan Indonesia ---
    try:
        clean_date = date_str.replace('/', '-').upper()
        month_map = {
            'MEI': 'MAY', 'AGU': 'AUG', 'OKT': 'OCT', 'NOP': 'NOV', 'DES': 'DEC'
        }
        for indo, eng in month_map.items():
            if indo in clean_date:
                clean_date = clean_date.replace(indo, eng)
        
        # Coba parse ulang setelah translasi bahasa
        for fmt in ['%d-%b-%Y', '%b-%Y']:
            try:
                return datetime.strptime(clean_date, fmt)
            except:
                continue
    except:
        pass
            
    return None
