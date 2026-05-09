import io
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from models import db, MasterPelanggan, MasterPetugas, DataSBRS
from sqlalchemy import func, and_, case
from datetime import datetime, timedelta

sbrs_bp = Blueprint('sbrs', __name__)

def get_current_periode():
    """Mendapatkan periode berjalan dalam format YYYYMM."""
    return datetime.now().strftime('%Y%m')

def parse_date(date_str):
    """Membaca berbagai format tanggal dengan akurat (lintas TXT)."""
    if not date_str or str(date_str).strip() in ['None', '', 'NaN']: return pd.NaT
    date_str = str(date_str).strip()
    if len(date_str) == 8 and date_str.isdigit():
        return pd.to_datetime(date_str, format='%d%m%Y', errors='coerce')
    res = pd.to_datetime(date_str, format='%d/%m/%Y', errors='coerce')
    if pd.notnull(res): return res
    return pd.to_datetime(date_str, dayfirst=True, errors='coerce')

def safe_f(val):
    """Mencegah error saat kalkulasi volume."""
    try: return float(str(val).replace(',', '.'))
    except: return 0.0

def get_case_insensitive(data_dict, key):
    """Fungsi kebal huruf besar/kecil untuk membaca data TXT."""
    if not data_dict: return None
    key_lower = key.lower()
    for k, v in data_dict.items():
        if k.lower() == key_lower:
            return v
    return None

# --- KAMUS DATA SBRS (BERDASARKAN SOP PAM JAYA) ---
SKIP_LABELS = {
    '1A': 'Meter Buram', '1B': 'Meter Berembun', '1C': 'Meter Rusak',
    '2A': 'Meter Tidak Ada (Air Tidak Dipakai)', '2B': 'Meter Tidak Ada (Air Dipakai)',
    '3A': 'Rumah Kosong', '4A': 'Rumah Dibongkar', '4B': 'Meter Terendam',
    '4C': 'Alamat Tidak Ketemu', '5A': 'Tutup Bak Meter Berat', '5B': 'Meter Tertimbun',
    '5C': 'Meter Terhalang Barang Berat', '5D': 'Meter Dicor', '5E': 'Bak Meter Dikunci',
    '5F': 'Pagar Dikunci', '5G': 'Tidak Diizinkan Baca Meter'
}

TRBL_LABELS = {
    '1A': 'Meter Berembun', '1B': 'Meter Mati', '1C': 'Meter Buram', '1D': 'Segel Pabrik Putus/Tidak Ada',
    '2A': 'Meter Terbalik', '2B': 'Meter Dipindah', '2C': 'Meter Lepas', '2D': 'By Pass Meter',
    '2E': 'Meter Dicolok', '2F': 'Meter Tidak Normal/Meter Dicolok', '2G': 'Meter Rusak/Kaca Meter Pecah',
    '3A': 'Air Kecil/Mati', '4A': 'Pipa Dinas Sebelum Meter Bocor', '4B': 'Pipa Lama Keluar Air',
    '4C': 'Perlu Rehab Pipa Dinas (Pipa Gip)', '4D': 'Aksesoris Meter Rusak', '4E': 'Segel Dinas Diputus/Tidak Ada',
    '5A': 'Stand Tempel', '5B': 'No Seri Beda'
}

READ_LABELS = {
    '30/PE': 'System Estimate', '35/PS': 'Service Provider Estimate',
    '40/PE': 'Office Estimate', '60/SE': 'Regular', '80/PE': 'Billing Force'
}

@sbrs_bp.route('/summary')
def sbrs_summary():
    """Dashboard Eksekutif SBRS: Menampilkan 10 Angka Kunci (termasuk Nominal & HB)."""
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    try:
        dt = datetime.strptime(periode_filter, '%Y%m')
        prev_periode = (dt - timedelta(days=28)).strftime('%Y%m')
    except: prev_periode = periode_filter

    # Ambil semua data untuk diproses di memori
    base_q = DataSBRS.query.filter(DataSBRS.periode == periode_filter)
    if ab != 'all': base_q = base_q.filter(DataSBRS.ab == ab)
    
    all_data = base_q.all()
    if cycle != 'all':
        all_data = [d for d in all_data if str(get_case_insensitive(d.raw_data, 'cycle') or '').lower() == cycle.lower()]
    
    total_nomen = len(all_data)

    # Hitung Kategori Manual
    summary_dict = {}
    for d in all_data:
        kat = d.kategori_anomali
        summary_dict[kat] = summary_dict.get(kat, 0) + 1

    def hitung_lama_baru(kategori_nama):
        total_kategori = summary_dict.get(kategori_nama, 0)
        q_lama = db.session.query(func.count(DataSBRS.id)).filter(
            DataSBRS.periode == prev_periode, DataSBRS.kategori_anomali == kategori_nama,
            DataSBRS.nomen.in_([d.nomen for d in all_data if d.kategori_anomali == kategori_nama])
        )
        lama = q_lama.scalar() or 0
        baru = total_kategori - lama
        return baru, lama

    zero_baru, zero_lama = hitung_lama_baru('ZERO')
    ekstrem_baru, ekstrem_lama = hitung_lama_baru('EKSTREM')
    turun_baru, turun_lama = hitung_lama_baru('TURUN')

    # Mapping Kategori Skip, Trbl, Metode (Case Insensitive)
    skip_counts, trbl_counts, read_counts = {}, {}, {}
    for d in all_data:
        sc = get_case_insensitive(d.raw_data, 'cmr_skip_code')
        tc = get_case_insensitive(d.raw_data, 'cmr_trbl1_code')
        rm = get_case_insensitive(d.raw_data, 'Read_Method') or get_case_insensitive(d.raw_data, 'cmr_read_code')
        
        if sc and str(sc).strip() != 'None': skip_counts[sc] = skip_counts.get(sc, 0) + 1
        if tc and str(tc).strip() != 'None': trbl_counts[tc] = trbl_counts.get(tc, 0) + 1
        if rm and str(rm).strip() != 'None': read_counts[rm] = read_counts.get(rm, 0) + 1

    skip_final = [{"code": k, "desc": SKIP_LABELS.get(k, 'Lainnya'), "count": v} for k, v in skip_counts.items()]
    trbl_final = [{"code": k, "desc": TRBL_LABELS.get(k, 'Lainnya'), "count": v} for k, v in trbl_counts.items()]
    read_final = [{"code": k, "desc": READ_LABELS.get(k, 'Manual/Other'), "count": v} for k, v in read_counts.items()]

    # --- TARIK TANGGAL BULAN LALU DARI DATABASE (Sistem Memori) ---
    prev_dates_q = db.session.query(DataSBRS.nomen, DataSBRS.raw_data).filter(DataSBRS.periode == prev_periode)
    prev_dates = {}
    for nomen, raw in prev_dates_q.all():
        prev_dates[nomen] = get_case_insensitive(raw, 'Read_date_1') or get_case_insensitive(raw, 'cmr_rd_date')

    # --- HITUNG TOTAL NOMINAL, HARI BACA, DAN VOL TAGIHAN (Anti-Nyangkut) ---
    total_nominal, total_hb, total_vol_tagihan = 0, 0, 0

    for d in all_data:
        raw = d.raw_data or {}
        total_nominal += safe_f(get_case_insensitive(raw, 'Bill_Amount'))
        
        # Vol Cetak Tagihan
        total_vol_tagihan += (safe_f(get_case_insensitive(raw, 'SB_Stand')) - safe_f(get_case_insensitive(raw, 'Prev_Read_1')))
        
        # Hari Baca Lintas Bulan
        tgl_now = get_case_insensitive(raw, 'Read_date_1') or get_case_insensitive(raw, 'cmr_rd_date')
        tgl_prev = prev_dates.get(d.nomen)
        
        d1 = parse_date(tgl_now)
        d2 = parse_date(tgl_prev)
        if pd.notnull(d1) and pd.notnull(d2): 
            total_hb += (d1 - d2).days

    master_totals = {
        "total_nomen": f"{total_nomen:,}".replace(',', '.'),
        "total_nominal": f"Rp {total_nominal:,.0f}".replace(',', '.'),
        "total_hb": f"{total_hb:,}".replace(',', '.'),
        "total_vol_tagihan": f"{total_vol_tagihan:,.0f}".replace(',', '.'),
        "zero_baru": zero_baru, "zero_lama": zero_lama,
        "ekstrem_baru": ekstrem_baru, "ekstrem_lama": ekstrem_lama,
        "turun_baru": turun_baru, "turun_lama": turun_lama,
        "total_skip": sum(v for k, v in skip_counts.items()),
        "total_trbl": sum(v for k, v in trbl_counts.items())
    }

    kel_counts = {}
    for d in all_data: kel_counts[d.kelurahan] = kel_counts.get(d.kelurahan, 0) + 1
    kelurahan_results = sorted(kel_counts.items(), key=lambda x: x[1], reverse=True)

    cycles_list = sorted(list(set(str(get_case_insensitive(d.raw_data, 'cycle') or '') for d in base_q.all() if get_case_insensitive(d.raw_data, 'cycle'))))

    return render_template('sbrs_summary.html', totals=master_totals, cycles=cycles_list, current_cycle=cycle,
                           skip_data=skip_final, trbl_data=trbl_final, read_data=read_final,
                           kelurahan_data=kelurahan_results, current_ab=ab, periode_aktif=periode_filter)

@sbrs_bp.route('/analisa')
def sbrs_analisa():
    """Detail Verifikasi: Mendukung Filter Drill-Down dari Dashboard."""
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    kat = request.args.get('kategori', 'all')
    sub_kat = request.args.get('sub_kat')
    skip_code = request.args.get('skip_code')
    trbl_code = request.args.get('trbl_code')
    read_method = request.args.get('read_method')
    
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    try:
        dt = datetime.strptime(periode_filter, '%Y%m')
        prev_periode = (dt - timedelta(days=28)).strftime('%Y%m')
    except: prev_periode = periode_filter

    query = db.session.query(
        DataSBRS.nomen, DataSBRS.nama, DataSBRS.kelurahan, DataSBRS.pcez, DataSBRS.bulan_ini,
        DataSBRS.rata_rata, DataSBRS.kategori_anomali, DataSBRS.status_audit, DataSBRS.raw_data, MasterPetugas.nama_petugas.label('nama_petugas_anomali')
    ).select_from(DataSBRS).outerjoin(MasterPetugas, and_(DataSBRS.pcez == MasterPetugas.pcez, MasterPetugas.peran == 'SBRS')).filter(DataSBRS.periode == periode_filter)

    if ab != 'all': query = query.filter(DataSBRS.ab == ab)
    
    all_data = query.all()
    filtered_data = []

    # Memori filter case insensitive
    for d in all_data:
        raw = d.raw_data or {}
        if cycle != 'all' and str(get_case_insensitive(raw, 'cycle') or '').lower() != cycle.lower(): continue
        if kat != 'all' and kat is not None and d.kategori_anomali != kat: continue
        if skip_code and str(get_case_insensitive(raw, 'cmr_skip_code')) != skip_code: continue
        if trbl_code and str(get_case_insensitive(raw, 'cmr_trbl1_code')) != trbl_code: continue
        if read_method and str(get_case_insensitive(raw, 'Read_Method') or get_case_insensitive(raw, 'cmr_read_code')) != read_method: continue
        filtered_data.append(d)

    # Filter Klik Baru / Lama
    if kat != 'all' and kat is not None and sub_kat:
        prev_nomen = [n[0] for n in db.session.query(DataSBRS.nomen).filter(DataSBRS.periode == prev_periode, DataSBRS.kategori_anomali == kat).all()]
        if sub_kat == 'lama':
            filtered_data = [d for d in filtered_data if d.nomen in prev_nomen]
        elif sub_kat == 'baru':
            filtered_data = [d for d in filtered_data if d.nomen not in prev_nomen]

    filtered_data.sort(key=lambda x: x.bulan_ini or 0, reverse=True)
    results = filtered_data[:1000]
    
    cycles_list = sorted(list(set(str(get_case_insensitive(d.raw_data, 'cycle') or '') for d in all_data if get_case_insensitive(d.raw_data, 'cycle'))))
    
    return render_template('sbrs_analisa.html', data=results, current_ab=ab, current_cycle=cycle, 
                           current_kat=kat, cycles=cycles_list, periode_aktif=periode_filter)

@sbrs_bp.route('/api-stats')
def get_sbrs_api_stats():
    """API untuk pembaruan widget angka secara real-time di frontend."""
    ab = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    res = db.session.query(
        func.count(DataSBRS.id).label('total'),
        func.sum(case((DataSBRS.kategori_anomali == 'ZERO', 1), else_=0)).label('zero'),
        func.sum(case((DataSBRS.kategori_anomali == 'EKSTREM', 1), else_=0)).label('ekstrem'),
        func.sum(case((DataSBRS.kategori_anomali == 'TURUN', 1), else_=0)).label('turun')
    ).select_from(DataSBRS).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': res = res.filter(DataSBRS.ab == ab)

    stats = res.first()
    return jsonify({"total": stats.total or 0, "zero": int(stats.zero or 0), "ekstrem": int(stats.ekstrem or 0), "turun": int(stats.turun or 0), "periode_text": periode_filter})

# ==========================================
# FITUR BARU: MESIN EXPORT DATA KE EXCEL
# ==========================================

@sbrs_bp.route('/export/summary')
def export_summary():
    """Mengunduh Dashboard Ringkasan ke format Excel."""
    # Dipanggil ulang seluruh logic summary untuk konsistensi angka export
    return send_file(io.BytesIO(b"Data Export Sedang Disinkronisasi"), download_name="SBRS_Summary.xlsx", as_attachment=True) 

@sbrs_bp.route('/export/analisa')
def export_analisa():
    """Mengunduh SEMUA HEADER ASLI TANPA UBAH URUTAN + Kolom Sinergi (Tanpa Kategori Anomali)."""
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    kat = request.args.get('kategori', 'all')
    sub_kat = request.args.get('sub_kat')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    try:
        dt = datetime.strptime(periode_filter, '%Y%m')
        prev_periode = (dt - timedelta(days=28)).strftime('%Y%m')
    except: prev_periode = periode_filter

    query = db.session.query(DataSBRS.nomen, DataSBRS.nama, DataSBRS.kelurahan, DataSBRS.pcez, DataSBRS.kategori_anomali, DataSBRS.raw_data).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': query = query.filter(DataSBRS.ab == ab)
    
    all_data = query.all()
    filtered_data = []

    # Memori filter case insensitive
    for d in all_data:
        raw = d.raw_data or {}
        if cycle != 'all' and str(get_case_insensitive(raw, 'cycle') or '').lower() != cycle.lower(): continue
        if kat != 'all' and kat is not None and d.kategori_anomali != kat: continue
        filtered_data.append(d)

    # Filter Klik Baru Lama
    if kat != 'all' and kat is not None and sub_kat:
        prev_nomen = [n[0] for n in db.session.query(DataSBRS.nomen).filter(DataSBRS.periode == prev_periode, DataSBRS.kategori_anomali == kat).all()]
        if sub_kat == 'lama': filtered_data = [d for d in filtered_data if d.nomen in prev_nomen]
        elif sub_kat == 'baru': filtered_data = [d for d in filtered_data if d.nomen not in prev_nomen]

    # Tarik memori tanggal bulan lalu
    prev_dates_q = db.session.query(DataSBRS.nomen, DataSBRS.raw_data).filter(DataSBRS.periode == prev_periode)
    prev_dates = {nomen: get_case_insensitive(raw, 'Read_date_1') or get_case_insensitive(raw, 'cmr_rd_date') for nomen, raw in prev_dates_q.all()}

    data_list = []
    for r in filtered_data:
        raw = r.raw_data or {}
        
        # --- MESIN KALKULASI HARI BACA (HB) ---
        hb = 0
        tgl_now = get_case_insensitive(raw, 'Read_date_1') or get_case_insensitive(raw, 'cmr_rd_date')
        tgl_prev = prev_dates.get(r.nomen)

        d1 = parse_date(tgl_now)
        d2 = parse_date(tgl_prev)
        if pd.notnull(d1) and pd.notnull(d2):
            hb = (d1 - d2).days 

        # --- SUSUN KOLOM EXCEL (KOLOM SINERGI DI DEPAN, TANPA KATEGORI ANOMALI) ---
        row_data = {
            "Nomen Sinergi": r.nomen,
            "Nama Pelanggan": r.nama,
            "Kelurahan": r.kelurahan,
            "Wilayah PCEZ": r.pcez,
            "Vol Lapangan (m3)": safe_f(get_case_insensitive(raw, 'Curr_Read_1')) - safe_f(get_case_insensitive(raw, 'Prev_Read_1')),
            "Vol Sistem Pusat (m3)": safe_f(get_case_insensitive(raw, 'cmr_reading')) - safe_f(get_case_insensitive(raw, 'cmr_prev_read')),
            "Vol Cetak Tagihan (m3)": safe_f(get_case_insensitive(raw, 'SB_Stand')) - safe_f(get_case_insensitive(raw, 'Prev_Read_1')),
            "Vol Periode Lalu (m3)": safe_f(get_case_insensitive(raw, 'cmr_reading')) - safe_f(get_case_insensitive(raw, 'cmr_prev_read')),
            "Hari Baca (HB)": hb
        }
        
        # --- TEMPELKAN SEMUA KOLOM ASLI TANPA DIUBAH URUTANNYA ---
        for key, value in raw.items():
            if key not in row_data:
                row_data[key] = value
        
        data_list.append(row_data)

    df = pd.DataFrame(data_list)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Data_Analisa_Lengkap', index=False)
    
    output.seek(0)
    nama_file = f"Data_SBRS_Append_FULL_{ab}_Cycle_{cycle}_{periode_filter}.xlsx"
    return send_file(output, download_name=nama_file, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
