import io
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from models import db, MasterPelanggan, MasterPetugas, DataSBRS
from sqlalchemy import func, and_, case
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timedelta

sbrs_bp = Blueprint('sbrs', __name__)

# --- KAMUS TRANSLATOR BULAN ---
BULAN_ID = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'Mei', '06': 'Jun',
    '07': 'Jul', '08': 'Ags', '09': 'Sep', '10': 'Okt', '11': 'Nov', '12': 'Des'
}

def get_current_periode():
    """Mendapatkan periode berjalan dalam format YYYYMM."""
    return datetime.now().strftime('%Y%m')

def get_prev_month(yyyymm, step=1):
    """Mundur X bulan dari periode saat ini untuk tren data historis."""
    if not yyyymm or len(yyyymm) != 6: return get_current_periode()
    y, m = int(yyyymm[:4]), int(yyyymm[4:])
    for _ in range(step):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return f"{y}{m:02d}"

def format_periode(yyyymm):
    """Menerjemahkan 202604 menjadi 'Apr 2026'."""
    if not yyyymm or len(yyyymm) != 6: return yyyymm
    return f"{BULAN_ID.get(yyyymm[4:], yyyymm[4:])} {yyyymm[:4]}"

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

def get_valid_str(val, fallback='-'):
    """Pembersih string untuk data wilayah."""
    s = str(val).strip() if val is not None else ''
    if s.lower() in ['none', '', '-', 'nan', 'null']:
        return fallback
    return s

def get_raw_val(raw_data, keys_to_try):
    """Mencari nilai dari daftar kunci yang mungkin (Pelacak Multi-Header)."""
    if not raw_data: return "-"
    for k in keys_to_try:
        for actual_key in [k, k.upper(), k.lower(), k.capitalize()]:
            if actual_key in raw_data and raw_data[actual_key] and str(raw_data[actual_key]).strip() not in ['None', 'nan', '']:
                return str(raw_data[actual_key]).strip()
    return "-"

# --- KAMUS DATA SBRS ---
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

@sbrs_bp.route('/save-catatan', methods=['POST'])
def save_catatan():
    """Menyimpan Catatan Analisa Desktop langsung ke dalam JSON raw_data."""
    try:
        data = request.json
        nomen = data.get('nomen')
        periode = data.get('periode')
        catatan = data.get('catatan')
        
        record = DataSBRS.query.filter_by(nomen=nomen, periode=periode).first()
        if record:
            raw = record.raw_data or {}
            raw['catatan_desktop'] = catatan
            record.raw_data = raw
            flag_modified(record, "raw_data")
            db.session.commit()
            return jsonify({"status": "success", "message": "Catatan berhasil disimpan!"})
        return jsonify({"status": "error", "message": "Data tidak ditemukan."}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@sbrs_bp.route('/summary')
def sbrs_summary():
    """Dashboard Eksekutif SBRS: Menampilkan Angka Kunci & Tab Wilayah."""
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    try:
        dt = datetime.strptime(periode_filter, '%Y%m')
        prev_periode = (dt - timedelta(days=28)).strftime('%Y%m')
    except: prev_periode = periode_filter

    base_q = DataSBRS.query.filter(DataSBRS.periode == periode_filter)
    if ab != 'all': base_q = base_q.filter(DataSBRS.ab == ab)
    
    all_data = base_q.all()
    if cycle != 'all':
        all_data = [d for d in all_data if str(get_case_insensitive(d.raw_data, 'cycle') or '').lower() == cycle.lower()]
    
    total_nomen = len(all_data)

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

    prev_dates_q = db.session.query(DataSBRS.nomen, DataSBRS.raw_data).filter(DataSBRS.periode == prev_periode)
    prev_dates = {nomen: get_case_insensitive(raw, 'Read_date_1') or get_case_insensitive(raw, 'cmr_rd_date') for nomen, raw in prev_dates_q.all()}

    total_nominal, total_hb, total_vol_tagihan = 0, 0, 0
    for d in all_data:
        raw = d.raw_data or {}
        total_nominal += safe_f(get_case_insensitive(raw, 'Bill_Amount'))
        total_vol_tagihan += (safe_f(get_case_insensitive(raw, 'SB_Stand')) - safe_f(get_case_insensitive(raw, 'Prev_Read_1')))
        
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

    cc_counts, pc_counts, pcez_counts, ab_counts, kel_counts, kec_counts = {}, {}, {}, {}, {}, {}
    for d in all_data:
        raw = d.raw_data or {}
        
        cc = get_valid_str(get_case_insensitive(raw, 'CC'))
        cc_counts[cc] = cc_counts.get(cc, 0) + 1
        
        pc = get_valid_str(get_case_insensitive(raw, 'KODE PA/PC') or get_case_insensitive(raw, 'PC'))
        pc_counts[pc] = pc_counts.get(pc, 0) + 1
        
        pcez = get_valid_str(get_case_insensitive(raw, 'PCEZ') or get_case_insensitive(raw, 'PCEZBK') or d.pcez)
        pcez_counts[pcez] = pcez_counts.get(pcez, 0) + 1

        ab_val = get_valid_str(get_case_insensitive(raw, 'AB') or d.ab)
        ab_counts[ab_val] = ab_counts.get(ab_val, 0) + 1
        
        kel = get_valid_str(get_case_insensitive(raw, 'KELURAHAN') or get_case_insensitive(raw, 'KEL') or d.kelurahan)
        kel_counts[kel] = kel_counts.get(kel, 0) + 1
        
        kec = get_valid_str(get_case_insensitive(raw, 'KECAMATAN') or get_case_insensitive(raw, 'KEC'))
        kec_counts[kec] = kec_counts.get(kec, 0) + 1

    cc_data = sorted(cc_counts.items(), key=lambda x: x[1], reverse=True)
    pc_data = sorted(pc_counts.items(), key=lambda x: x[1], reverse=True)
    pcez_data = sorted(pcez_counts.items(), key=lambda x: x[1], reverse=True)
    ab_data = sorted(ab_counts.items(), key=lambda x: x[1], reverse=True)
    kel_data = sorted(kel_counts.items(), key=lambda x: x[1], reverse=True)
    kec_data = sorted(kec_counts.items(), key=lambda x: x[1], reverse=True)

    cycles_list = sorted(list(set(str(get_case_insensitive(d.raw_data, 'cycle') or '') for d in base_q.all() if get_case_insensitive(d.raw_data, 'cycle'))))

    return render_template('sbrs_summary.html', totals=master_totals, cycles=cycles_list, current_cycle=cycle,
                           skip_data=skip_final, trbl_data=trbl_final, read_data=read_final,
                           cc_data=cc_data, pc_data=pc_data, pcez_data=pcez_data, 
                           ab_data=ab_data, kelurahan_data=kel_data, kecamatan_data=kec_data, 
                           current_ab=ab, periode_aktif=periode_filter)

@sbrs_bp.route('/analisa')
def sbrs_analisa():
    """Detail Verifikasi: Menggabungkan Data 3 Bulan Berturut-turut untuk Semua Field yang Di-request."""
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    kat = request.args.get('kategori', 'all')
    sub_kat = request.args.get('sub_kat')
    skip_code = request.args.get('skip_code')
    trbl_code = request.args.get('trbl_code')
    read_method = request.args.get('read_method')
    
    # 6 Parameter Filter Wilayah Murni
    cc_filter = request.args.get('cc')
    pc_filter = request.args.get('pc')
    pcez_filter = request.args.get('pcez')
    ab_tab_filter = request.args.get('ab_tab')
    kel_filter = request.args.get('kelurahan')
    kec_filter = request.args.get('kecamatan')
    
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    # Eksekusi Mundur 2 Bulan untuk Tren dan Format Bulan
    prev_periode_1 = get_prev_month(periode_filter, 1)
    prev_periode_2 = get_prev_month(periode_filter, 2)
    
    label_kini = format_periode(periode_filter)
    label_lalu_1 = format_periode(prev_periode_1)
    label_lalu_2 = format_periode(prev_periode_2)

    query = db.session.query(
        DataSBRS.nomen, DataSBRS.nama, DataSBRS.kelurahan, DataSBRS.pcez, DataSBRS.bulan_ini,
        DataSBRS.rata_rata, DataSBRS.kategori_anomali, DataSBRS.status_audit, DataSBRS.raw_data, MasterPetugas.nama_petugas.label('nama_petugas_anomali')
    ).select_from(DataSBRS).outerjoin(MasterPetugas, and_(DataSBRS.pcez == MasterPetugas.pcez, MasterPetugas.peran == 'SBRS')).filter(DataSBRS.periode == periode_filter)

    if ab != 'all': query = query.filter(DataSBRS.ab == ab)
    
    all_data = query.all()
    filtered_data = []

    for d in all_data:
        raw = d.raw_data or {}
        if cycle != 'all' and str(get_case_insensitive(raw, 'cycle') or '').lower() != cycle.lower(): continue
        if kat != 'all' and kat is not None and d.kategori_anomali != kat: continue
        if skip_code and str(get_case_insensitive(raw, 'cmr_skip_code')) != skip_code: continue
        if trbl_code and str(get_case_insensitive(raw, 'cmr_trbl1_code')) != trbl_code: continue
        if read_method and str(get_case_insensitive(raw, 'Read_Method') or get_case_insensitive(raw, 'cmr_read_code')) != read_method: continue
        
        # Eksekusi Filter 6 Tab Wilayah
        if cc_filter and get_valid_str(get_case_insensitive(raw, 'CC')).lower() != cc_filter.lower(): continue
        if pc_filter and get_valid_str(get_case_insensitive(raw, 'KODE PA/PC') or get_case_insensitive(raw, 'PC')).lower() != pc_filter.lower(): continue
        if pcez_filter and get_valid_str(get_case_insensitive(raw, 'PCEZ') or get_case_insensitive(raw, 'PCEZBK') or d.pcez).lower() != pcez_filter.lower(): continue
        if ab_tab_filter and get_valid_str(get_case_insensitive(raw, 'AB') or d.ab).lower() != ab_tab_filter.lower(): continue
        if kel_filter and get_valid_str(get_case_insensitive(raw, 'KELURAHAN') or get_case_insensitive(raw, 'KEL') or d.kelurahan).lower() != kel_filter.lower(): continue
        if kec_filter and get_valid_str(get_case_insensitive(raw, 'KECAMATAN') or get_case_insensitive(raw, 'KEC')).lower() != kec_filter.lower(): continue
        
        filtered_data.append(d)

    if kat != 'all' and kat is not None and sub_kat:
        prev_nomen = [n[0] for n in db.session.query(DataSBRS.nomen).filter(DataSBRS.periode == prev_periode_1, DataSBRS.kategori_anomali == kat).all()]
        if sub_kat == 'lama':
            filtered_data = [d for d in filtered_data if d.nomen in prev_nomen]
        elif sub_kat == 'baru':
            filtered_data = [d for d in filtered_data if d.nomen not in prev_nomen]

    filtered_data.sort(key=lambda x: x.bulan_ini or 0, reverse=True)
    top_data = filtered_data[:1000]

    # Ambil Data Histori Penuh (Raw Data) 2 Bulan Ke Belakang dari Database
    nomen_list = [d.nomen for d in top_data]
    hist_1_records = db.session.query(DataSBRS).filter(DataSBRS.periode == prev_periode_1, DataSBRS.nomen.in_(nomen_list)).all()
    hist_1 = {r.nomen: r for r in hist_1_records}
    
    hist_2_records = db.session.query(DataSBRS).filter(DataSBRS.periode == prev_periode_2, DataSBRS.nomen.in_(nomen_list)).all()
    hist_2 = {r.nomen: r for r in hist_2_records}

    # Fungsi Ekstraksi 20 Field Sekaligus
    def extract_all_fields(raw_dict):
        if not raw_dict:
            return {
                "cmr_prev_read": 0, "cmr_loc_code": "-", "read_method": "-", 
                "prev_read_1": 0, "curr_read_1": 0, "cmr_reading": 0, 
                "cmr_mtr_num": "-", "bill_amount": "0", "tariff": "-", 
                "hari_baca": "0", "cmr_trbl1_code": "-", "payment_amount": "0", 
                "cmr_chg_spcl_msg": "-", "cmr_cycle": "-", "sb_stand": 0, 
                "vol_lapangan": 0, "vol_pusat": 0, "vol_cetak": 0
            }
        
        prev1 = safe_f(get_raw_val(raw_dict, ['PREV_READ_1', 'START_READ_STAN', 'cmr_prev_read']))
        curr1 = safe_f(get_raw_val(raw_dict, ['CURR_READ_1', 'END_READ_STAN', 'cmr_reading']))
        cmr_read = safe_f(get_raw_val(raw_dict, ['CMR_READING']))
        cmr_prev = safe_f(get_raw_val(raw_dict, ['CMR_PREV_READ']))
        sb_st = safe_f(get_raw_val(raw_dict, ['SB_STAND', 'SB_Stand']))
        
        return {
            "cmr_prev_read": cmr_prev,
            "cmr_loc_code": get_raw_val(raw_dict, ['CMR_LOC_CODE', 'LOC_CODE']),
            "read_method": get_raw_val(raw_dict, ['READ_METHOD', 'Read_Method', 'cmr_read_code']),
            "prev_read_1": prev1,
            "curr_read_1": curr1,
            "cmr_reading": cmr_read,
            "cmr_mtr_num": get_raw_val(raw_dict, ['CMR_MTR_NUM', 'METER_SERIAL_1', 'METER_SERIAL']),
            "bill_amount": get_raw_val(raw_dict, ['BILL_AMOUNT', 'TOTAL_TAGIHAN']),
            "tariff": get_raw_val(raw_dict, ['TARIFF', 'TARIF', 'cmr_tarif']),
            "hari_baca": get_raw_val(raw_dict, ['HARI_BACA', 'DAYS']),
            "cmr_trbl1_code": get_raw_val(raw_dict, ['CMR_TRBL1_CODE', 'TRBL1_CODE']),
            "payment_amount": get_raw_val(raw_dict, ['PAYMENT_AMOUNT']),
            "cmr_chg_spcl_msg": get_raw_val(raw_dict, ['CMR_CHG_SPCL_MSG', 'REMARK']),
            "cmr_cycle": get_raw_val(raw_dict, ['CMR_CYCLE', 'CYCLE', 'BILL_CYCLE']),
            "sb_stand": sb_st,
            "vol_lapangan": curr1 - prev1,
            "vol_pusat": cmr_read - cmr_prev,
            "vol_cetak": sb_st - prev1
        }

    results = []
    for d in top_data:
        raw_kini = d.raw_data or {}
        r1 = hist_1.get(d.nomen)
        raw_lalu_1 = r1.raw_data if r1 else {}
        r2 = hist_2.get(d.nomen)
        raw_lalu_2 = r2.raw_data if r2 else {}
        
        raw_rata = get_case_insensitive(raw_kini, 'Estimation_Value') or get_case_insensitive(raw_kini, 'AVG_CONSUMPTION')
        rata_real = float(raw_rata) if raw_rata else d.rata_rata
        
        # Eksekusi Ekstraksi 3 Bulan Berturut-turut untuk SEMUA FIELD (kecuali statis)
        data_kini = extract_all_fields(raw_kini)
        data_lalu_1 = extract_all_fields(raw_lalu_1)
        data_lalu_2 = extract_all_fields(raw_lalu_2)

        results.append({
            "nomen": d.nomen,
            "nama": d.nama,
            "kelurahan": d.kelurahan,
            "pcez": d.pcez,
            "kategori_anomali": d.kategori_anomali,
            "status_audit": d.status_audit,
            
            # Data Utama untuk Tabel Depan
            "bulan_ini": data_kini['vol_cetak'], 
            "vol_kini": data_kini['vol_cetak'],
            "vol_lalu_1": data_lalu_1['vol_cetak'] if data_lalu_1['vol_cetak'] != 0 else rata_real,
            "vol_lalu_2": data_lalu_2['vol_cetak'] if data_lalu_2['vol_cetak'] != 0 else rata_real,
            "stand_awal": data_kini['prev_read_1'],
            "stand_akhir": data_kini['sb_stand'],
            "catatan": raw_kini.get('catatan_desktop', ''),
            "rata_rata": rata_real,
            "cmr_mrid": get_raw_val(raw_kini, ['CMR_MRID', 'MRID']),
            "cmr_trbl1_code": data_kini['cmr_trbl1_code'],
            "read_method": data_kini['read_method'],
            "nama_petugas_anomali": d.nama_petugas_anomali,
            "raw_data": raw_kini,
            
            # Modal Info yang Menampung Seluruh 3 Bulan Secara Terpisah
            "modal_info": { 
                "kini": data_kini,
                "lalu_1": data_lalu_1,
                "lalu_2": data_lalu_2,
                
                # Single Data Request (Sesuai Permintaan Bos: 1 Bulan Saja)
                "cmr_mrid": get_raw_val(raw_kini, ['CMR_MRID', 'MRID']),
                "rayon": get_raw_val(raw_kini, ['RAYON', 'PCEZ', 'PCEZBK']),
                
                "alamat": get_raw_val(raw_kini, ['cmr_address', 'ALAMAT']),
                "wa": get_raw_val(raw_kini, ['WA_NUMBER', 'MOBILE', 'cmr_phone', 'NO_HP']),
                "telp": get_raw_val(raw_kini, ['PHONE', 'TELEPON']),
                "email": get_raw_val(raw_kini, ['EMAIL', 'SUREL']),
                "indikasi": raw_kini.get('INDIKASI_SINERGI', 'Aman')
            }
        })
    
    cycles_list = sorted(list(set(str(get_case_insensitive(d.raw_data, 'cycle') or '') for d in all_data if get_case_insensitive(d.raw_data, 'cycle'))))
    
    return render_template('sbrs_analisa.html', data=results, current_ab=ab, current_cycle=cycle, 
                           current_kat=kat, cycles=cycles_list, 
                           periode_aktif=periode_filter, label_kini=label_kini, 
                           label_lalu_1=label_lalu_1, label_lalu_2=label_lalu_2)

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

    for d in all_data:
        raw = d.raw_data or {}
        if cycle != 'all' and str(get_case_insensitive(raw, 'cycle') or '').lower() != cycle.lower(): continue
        if kat != 'all' and kat is not None and d.kategori_anomali != kat: continue
        filtered_data.append(d)

    if kat != 'all' and kat is not None and sub_kat:
        prev_nomen = [n[0] for n in db.session.query(DataSBRS.nomen).filter(DataSBRS.periode == prev_periode, DataSBRS.kategori_anomali == kat).all()]
        if sub_kat == 'lama': filtered_data = [d for d in filtered_data if d.nomen in prev_nomen]
        elif sub_kat == 'baru': filtered_data = [d for d in filtered_data if d.nomen not in prev_nomen]

    prev_dates_q = db.session.query(DataSBRS.nomen, DataSBRS.raw_data).filter(DataSBRS.periode == prev_periode)
    prev_dates = {nomen: get_case_insensitive(raw, 'Read_date_1') or get_case_insensitive(raw, 'cmr_rd_date') for nomen, raw in prev_dates_q.all()}

    data_list = []
    for r in filtered_data:
        raw = r.raw_data or {}
        
        hb = 0
        tgl_now = get_case_insensitive(raw, 'Read_date_1') or get_case_insensitive(raw, 'cmr_rd_date')
        tgl_prev = prev_dates.get(r.nomen)

        d1 = parse_date(tgl_now)
        d2 = parse_date(tgl_prev)
        if pd.notnull(d1) and pd.notnull(d2):
            hb = (d1 - d2).days 

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
