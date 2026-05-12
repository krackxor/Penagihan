import os
import gc
import json
import re
import csv
from datetime import datetime
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy import text
from models import db

importer_bp = Blueprint('importer', __name__)

# ==========================================================
# 1. STRATEGI ANTI-GAGAL & HEMAT RAM EKSTREM
# ==========================================================

def get_current_periode():
    return datetime.now().strftime('%Y%m')

def detect_separator(filepath, default=';'):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            counts = { ';': first_line.count(';'), '|': first_line.count('|'), ',': first_line.count(',') }
            best_sep = max(counts, key=counts.get)
            return best_sep if counts[best_sep] > 0 else default
    except: return default

def get_val(row_dict, possible_keys, default=''):
    for k in possible_keys:
        if k in row_dict and row_dict[k] is not None:
            val = str(row_dict[k]).strip().replace('"', '')
            if val.lower() not in ['none', 'nan', 'null', '']: return val
    return default

def clean_nomen(val):
    if not val: return None
    s = str(val).replace('"', '').strip().upper().split('.')[0]
    s = s.replace('K', '')
    s = re.sub(r'[^0-9]', '', s)
    return s if s else None

def standardize_cust_type(val):
    s = str(val).replace('"', '').strip().upper()
    if s == 'R' or 'REG' in s: return 'REGULAR'
    return s

def extract_periode(val):
    try:
        val = str(val).replace('"', '').strip()
        if not val or val.lower() in ['none', 'nan', '']: return "000000"
        if '/' in val:
            parts = val.split(' ')[0].split('/')
            if len(parts) == 3:
                m = parts[1].zfill(2)
                y = parts[2] if len(parts[2]) != 2 else "20" + parts[2]
                return f"{y}{m}"
        if len(val) == 6 and val[2:].startswith('20'): return val[2:] + val[:2]
        return val[:6].replace('-', '')
    except: return "000000"

def shift_period_plus_one(yyyymm):
    yyyymm_str = str(yyyymm).strip()
    if not yyyymm_str or len(yyyymm_str) != 6: return yyyymm_str
    try:
        y, m = int(yyyymm_str[:4]), int(yyyymm_str[4:])
        return f"{y+1}01" if m == 12 else f"{y}{m+1:02d}"
    except: return yyyymm_str

def parse_float(val):
    try:
        if not val: return 0.0
        v_str = str(val).replace('"', '').strip().replace('.', '').replace(',', '.')
        return float(v_str)
    except: return 0.0

def process_mega_file(file, logic_func, chunk_size=250, default_sep=';'):
    """MESIN PURE PYTHON STREAMING: Anti-Crash untuk VPS RAM Rendah"""
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    if not os.path.exists('instance'): os.makedirs('instance')
    file.save(temp_path)

    smart_sep = detect_separator(temp_path, default=default_sep)
    total = 0

    try:
        with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter=smart_sep, quotechar='"')
            
            # --- STRATEGI HEADER SANITIZATION ---
            if reader.fieldnames:
                clean_fieldnames = [str(col).replace('\ufeff', '').replace('"', '').strip().upper() for col in reader.fieldnames]
                reader.fieldnames = clean_fieldnames
            else:
                return 0

            chunk = []
            for row in reader:
                chunk.append(row)
                if len(chunk) >= chunk_size:
                    added_count = logic_func(chunk)
                    if added_count: total += added_count
                    
                    db.session.commit()
                    db.session.expunge_all()
                    chunk = [] 
            
            if chunk:
                added_count = logic_func(chunk)
                if added_count: total += added_count
                db.session.commit()
                db.session.expunge_all()

        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)
        gc.collect()

# ==========================================================
# 2. RUTE UTAMA UPLOAD
# ==========================================================
@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')
    file_mc = request.files.get('file_mc')
    file_mb = request.files.get('file_mb')             
    file_daily = request.files.get('file_daily')       
    file_cid = request.files.get('file_cid')
    file_arrdebt = request.files.get('file_arrdebt')
    file_mainbill = request.files.get('file_mainbill') or request.files.get('file')

    try:
        if file_cust and file_spot: return handle_sbrs_upload(file_cust, file_spot)
        elif file_mc: return handle_mc_upload(file_mc)                              
        elif file_mb: return handle_mb_upload(file_mb)                              
        elif file_daily: return handle_daily_upload(file_daily)                     
        elif file_cid: return handle_cid_upload(file_cid)                           
        elif file_arrdebt: return handle_arrdebt_upload(file_arrdebt)               
        elif file_mainbill: return handle_mainbill_upload(file_mainbill)            
        else: return jsonify({"status": "error", "message": "Format file tidak dikenali atau kosong!"}), 400
    except Exception as e:
        db.session.rollback()
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": f"Fatal System Error: {str(e)}"}), 500


# =========================================================================
# 3. LOGIKA MASTER CID
# =========================================================================
def handle_cid_upload(file_cid):
    def cid_logic(data_chunk):
        cid_entries = []
        for row in data_chunk:
            nomen_raw = get_val(row, ['NOMEN', 'ACCT_ID', 'ID_PELANGGAN'])
            nomen = clean_nomen(nomen_raw)
            if not nomen: continue
            
            tipe_raw = get_val(row, ['TIPEPLGGN', 'TYPECUST1', 'CUST_TYPE'])
            tipe_bersih = standardize_cust_type(tipe_raw)
            row['TIPEPLGGN'] = tipe_bersih 
            
            cid_entries.append({
                "nomen": nomen,
                "norek": get_val(row, ['NOREK', 'NO_REK']),
                "nama": get_val(row, ['NAMA', 'NAMA_PEL', 'NAMA_PELANGGAN'], 'Pelanggan Baru'),
                "status": get_val(row, ['STATUS']),
                "tipeplggn": tipe_bersih,
                "custclass": get_val(row, ['CUSTCLASS', 'CUST_CLASS']),
                "tarif": get_val(row, ['TARIFF', 'TARIF', 'GOL_TARIF']),
                "alamat": get_val(row, ['ALAMAT', 'ALM1_PEL']),
                "kodepos": get_val(row, ['KODEPOS', 'KODE_POS']),
                "kelurahan": get_val(row, ['KELURAHAN', 'KEL']),
                "kecamatan": get_val(row, ['KECAMATAN', 'KEC']),
                "kota": get_val(row, ['KOTA / KABUPATEN', 'KOTA', 'KABUPATEN']),
                "ab": get_val(row, ['AB', 'WILAYAH'], 'AB Sunter'),
                "regional": get_val(row, ['REGIONAL', 'REGION']),
                "cc": get_val(row, ['CC']),
                "kode_pa_pc": get_val(row, ['KODE PA/PC', 'KODE_PA_PC', 'PC']),
                "zona_novak": get_val(row, ['ZONA_NOVAK', 'ZONA']),
                "pcez": get_val(row, ['PCEZ', 'PCEZBK']),
                "rayon": get_val(row, ['RAYON', 'KODE PA/PC', 'PCEZ'])[:10] if get_val(row, ['RAYON', 'KODE PA/PC', 'PCEZ']) else '',
                "cycle": get_val(row, ['CYCLE', 'BILL_CYCLE']),
                "merk": get_val(row, ['MERK', 'MERK_METER']),
                "serial": get_val(row, ['SERIAL', 'NO_METER', 'NOMET']),
                "hp": get_val(row, ['HP', 'NO_HP']),
                "tlp": get_val(row, ['TLP', 'TELEPON']),
                "wa": get_val(row, ['WA', 'WHATSAPP']),
                "email": get_val(row, ['EMAIL']),
                "fax": get_val(row, ['FAX']),
                "latitude": get_val(row, ['LATITUDE', 'LAT']),
                "longitude": get_val(row, ['LONGITUDE', 'LONG']),
                "raw_data": json.dumps(row)
            })
            
        if cid_entries:
            sql_cid = text("""
                INSERT INTO master_pelanggan (
                    nomen, norek, nama, status, tipeplggn, custclass, tarif, alamat, kodepos, 
                    kelurahan, kecamatan, kota, ab, regional, cc, kode_pa_pc, zona_novak, 
                    pcez, rayon, cycle, merk, serial, hp, tlp, wa, email, fax, latitude, longitude, raw_data
                ) VALUES (
                    :nomen, :norek, :nama, :status, :tipeplggn, :custclass, :tarif, :alamat, :kodepos, 
                    :kelurahan, :kecamatan, :kota, :ab, :regional, :cc, :kode_pa_pc, :zona_novak, 
                    :pcez, :rayon, :cycle, :merk, :serial, :hp, :tlp, :wa, :email, :fax, :latitude, :longitude, CAST(:raw_data AS JSONB)
                ) ON CONFLICT (nomen) DO UPDATE SET 
                    norek=EXCLUDED.norek, nama=EXCLUDED.nama, status=EXCLUDED.status, tipeplggn=EXCLUDED.tipeplggn, 
                    custclass=EXCLUDED.custclass, tarif=EXCLUDED.tarif, alamat=EXCLUDED.alamat, kodepos=EXCLUDED.kodepos, 
                    kelurahan=EXCLUDED.kelurahan, kecamatan=EXCLUDED.kecamatan, kota=EXCLUDED.kota, ab=EXCLUDED.ab, 
                    regional=EXCLUDED.regional, cc=EXCLUDED.cc, kode_pa_pc=EXCLUDED.kode_pa_pc, zona_novak=EXCLUDED.zona_novak, 
                    pcez=EXCLUDED.pcez, rayon=EXCLUDED.rayon, cycle=EXCLUDED.cycle, merk=EXCLUDED.merk, serial=EXCLUDED.serial, 
                    hp=EXCLUDED.hp, tlp=EXCLUDED.tlp, wa=EXCLUDED.wa, email=EXCLUDED.email, fax=EXCLUDED.fax, 
                    latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql_cid, cid_entries)
            return len(cid_entries)
        return 0

    total = process_mega_file(file_cid, cid_logic, chunk_size=250)
    return jsonify({"status": "success", "message": f"Master CID Sukses! {total} pelanggan diperbarui."})

# =========================================================================
# 4. LOGIKA MC (MASTER CETAK)
# =========================================================================
def handle_mc_upload(file_mc):
    def mc_logic(data_chunk):
        mc_entries = []
        for row in data_chunk:
            nomen = clean_nomen(get_val(row, ['NOMEN', 'ACCT_ID']))
            if not nomen: continue
            
            tipe_raw = get_val(row, ['CUST_TYPE', 'TYPECUST1', 'TIPEPLGGN'])
            if tipe_raw: row['CUST_TYPE'] = standardize_cust_type(tipe_raw)
            
            tahun2 = get_val(row, ['TAHUN2'])
            bulan2 = get_val(row, ['NAMA_BLN2'])
            if tahun2 and bulan2:
                periode_target = f"{tahun2}{bulan2.zfill(2)}"
            else:
                periode_asli = extract_periode(get_val(row, ['PERIODE', 'BLNTAG']))
                periode_target = shift_period_plus_one(periode_asli)

            mc_entries.append({
                "nomen": nomen,
                "periode": periode_target,
                "alm1_pel": get_val(row, ['ALM1_PEL', 'ALAMAT']),
                "zona_novak": get_val(row, ['ZONA_NOVAK', 'ZONA']),
                "notagihan": get_val(row, ['NOTAGIHAN', 'NO_TAGIHAN']),
                "total_tagihan": parse_float(get_val(row, ['NOMINAL', 'REK_AIR', 'TOTAL_TAGIHAN'])),
                "raw_data": json.dumps(row)
            })
            
        if mc_entries:
            sql_mc = text("""
                INSERT INTO transaksi_tagihan (nomen, periode, alm1_pel, zona_novak, notagihan, total_tagihan, status_lunas, raw_data)
                VALUES (:nomen, :periode, :alm1_pel, :zona_novak, :notagihan, :total_tagihan, 0, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen, periode) DO UPDATE SET 
                    alm1_pel=EXCLUDED.alm1_pel, zona_novak=EXCLUDED.zona_novak, notagihan=EXCLUDED.notagihan,
                    total_tagihan=EXCLUDED.total_tagihan, status_lunas=0, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql_mc, mc_entries)
            return len(mc_entries)
        return 0

    total = process_mega_file(file_mc, mc_logic, chunk_size=500)
    return jsonify({"status": "success", "message": f"MC Tagihan Sukses! {total} data tercatat."})

# =========================================================================
# 5. LOGIKA MASTER BAYAR (MB)
# =========================================================================
def handle_mb_upload(file_mb):
    def mb_logic(data_chunk):
        mb_entries = []
        lunas_entries = []
        for row in data_chunk:
            nomen = clean_nomen(get_val(row, ['NOMEN', 'CMR_ACCOUNT']))
            if not nomen: continue
            
            bulan_rek_raw = get_val(row, ['BULAN_REK'])
            periode_asli = extract_periode(bulan_rek_raw if bulan_rek_raw else get_val(row, ['PERIODE']))
            periode_target = shift_period_plus_one(periode_asli)
            
            mb_entries.append({
                "nomen": nomen,
                "periode": periode_target,
                "bulan_rek": bulan_rek_raw,
                "tgl_bayar": get_val(row, ['TGL_BAYAR', 'PAY_DT']),
                "nominal": parse_float(get_val(row, ['NOMINAL', 'RPBAYAR'])),
                "denda": parse_float(get_val(row, ['DENDA'])),
                "lks_bayar": get_val(row, ['LKS_BAYAR', 'PAY_LOC']),
                "notagihan": get_val(row, ['NOTAGIHAN', 'BILL_ID']),
                "raw_data": json.dumps(row)
            })
            lunas_entries.append({"n": nomen, "p": periode_target})
            
        if mb_entries:
            sql_mb = text("""
                INSERT INTO data_mb (nomen, periode, bulan_rek, tgl_bayar, nominal, denda, lks_bayar, notagihan, raw_data)
                VALUES (:nomen, :periode, :bulan_rek, :tgl_bayar, :nominal, :denda, :lks_bayar, :notagihan, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen, periode) DO UPDATE SET 
                    bulan_rek=EXCLUDED.bulan_rek, tgl_bayar=EXCLUDED.tgl_bayar, nominal=EXCLUDED.nominal,
                    denda=EXCLUDED.denda, lks_bayar=EXCLUDED.lks_bayar, notagihan=EXCLUDED.notagihan, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql_mb, mb_entries)
            
            if lunas_entries:
                sql_lunas = text("UPDATE transaksi_tagihan SET status_lunas = 1 WHERE nomen = :n AND periode = :p")
                db.session.execute(sql_lunas, lunas_entries)
            return len(mb_entries)
        return 0

    total_bayar = process_mega_file(file_mb, mb_logic, chunk_size=500)
    return jsonify({"status": "success", "message": f"Master Bayar (MB) Sukses! {total_bayar} dilunaskan."})

# =========================================================================
# 6. LOGIKA KOLEKSI HARIAN (DAILY DATA)
# =========================================================================
def handle_daily_upload(file_daily):
    def daily_logic(data_chunk):
        daily_entries = []
        lunas_entries = []
        for row in data_chunk:
            nomen = clean_nomen(get_val(row, ['NOMEN', 'ACCT_ID']))
            if not nomen: continue
            
            tipe_raw = get_val(row, ['TYPECUST1', 'CUST_TYPE'])
            tipe_bersih = standardize_cust_type(tipe_raw)
            row['TYPECUST1'] = tipe_bersih
            
            bill_period_raw = get_val(row, ['BILL_PERIOD', 'PERIODE_DTTM'])
            periode_asli = extract_periode(bill_period_raw)
            periode_target = shift_period_plus_one(periode_asli)

            daily_entries.append({
                "nomen": nomen,
                "periode": periode_target,
                "pay_dt": get_val(row, ['PAY_DT', 'TGL_BAYAR']),
                "bill_period": bill_period_raw,
                "pay_amt": parse_float(get_val(row, ['PAY_AMT', 'NOMINAL'])),
                "pay_status_flg": get_val(row, ['PAY_STATUS_FLG', 'STATUS_FLG']),
                "bill_type": get_val(row, ['BILL_TYPE', 'JENIS']),
                "typecust1": tipe_bersih,
                "pay_loc": get_val(row, ['PAY_LOC', 'LKS_BAYAR']),
                "bill_id": get_val(row, ['BILL_ID', 'NOTAGIHAN']),
                "ab": get_val(row, ['AB', 'WILAYAH']),
                "status": get_val(row, ['STATUS']),
                "raw_data": json.dumps(row)
            })
            
            status_flag = get_val(row, ['PAY_STATUS_FLG', 'STATUS_FLG'])
            if status_flag in ['1', '50', 'LUNAS']:
                lunas_entries.append({"n": nomen, "p": periode_target})
            
        if daily_entries:
            sql_daily = text("""
                INSERT INTO data_daily (
                    nomen, periode, pay_dt, bill_period, pay_amt, pay_status_flg, 
                    bill_type, typecust1, pay_loc, bill_id, ab, status, raw_data
                )
                VALUES (
                    :nomen, :periode, :pay_dt, :bill_period, :pay_amt, :pay_status_flg, 
                    :bill_type, :typecust1, :pay_loc, :bill_id, :ab, :status, CAST(:raw_data AS JSONB)
                )
                ON CONFLICT (nomen, bill_id) DO UPDATE SET 
                    periode=EXCLUDED.periode, pay_dt=EXCLUDED.pay_dt, bill_period=EXCLUDED.bill_period, 
                    pay_amt=EXCLUDED.pay_amt, pay_status_flg=EXCLUDED.pay_status_flg, bill_type=EXCLUDED.bill_type, 
                    typecust1=EXCLUDED.typecust1, pay_loc=EXCLUDED.pay_loc, ab=EXCLUDED.ab, 
                    status=EXCLUDED.status, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql_daily, daily_entries)
            
            if lunas_entries:
                sql_lunas = text("UPDATE transaksi_tagihan SET status_lunas = 1 WHERE nomen = :n AND periode = :p")
                db.session.execute(sql_lunas, lunas_entries)
            return len(daily_entries)
        return 0

    total = process_mega_file(file_daily, daily_logic, chunk_size=500)
    return jsonify({"status": "success", "message": f"Koleksi Harian Sukses! {total} transaksi disinkronkan."})

# =========================================================================
# 7. LOGIKA MAINBILL
# =========================================================================
def handle_mainbill_upload(file_mainbill):
    def mainbill_logic(data_chunk):
        mb_entries = []
        for row in data_chunk:
            nomen = clean_nomen(get_val(row, ['NOMEN', 'ACCT_ID']))
            if not nomen: continue
            
            end_read_raw = get_val(row, ['END_READ', 'TGL_BACA'])
            periode_target = "999999"
            if len(end_read_raw) >= 10:
                parts = end_read_raw[:10].split('/')
                if len(parts) == 3: 
                    y = parts[2]
                    if len(y) == 2: y = "20" + y
                    periode_target = f"{y}{parts[1].zfill(2)}"

            mb_entries.append({
                "nomen": nomen,
                "periode": periode_target,
                "jenis_pelanggan": get_val(row, ['JENIS_PELANGGAN', 'TYPECUST1']),
                "cc": get_val(row, ['CC']),
                "pcezbk": get_val(row, ['PCEZBK', 'PCEZ']),
                "tarif": get_val(row, ['TARIF', 'TARIFF']),
                "bill_cycle": get_val(row, ['BILL_CYCLE', 'CYCLE']),
                "read_method": get_val(row, ['READ_METHOD']),
                "konsumsi": parse_float(get_val(row, ['KONSUMSI', 'VOL'])),
                "tagihan_air": parse_float(get_val(row, ['TAGIHAN_AIR', 'REK_AIR'])),
                "start_read": get_val(row, ['START_READ']),
                "start_read_stan": get_val(row, ['START_READ_STAN', 'STAN_AWAL']),
                "end_read": end_read_raw,
                "hari_baca": get_val(row, ['HARI_BACA', 'HB']),
                "raw_data": json.dumps(row)
            })
            
        if mb_entries:
            sql = text("""
                INSERT INTO data_mainbill (
                    nomen, periode, jenis_pelanggan, cc, pcezbk, tarif, bill_cycle, 
                    read_method, konsumsi, tagihan_air, start_read, start_read_stan, end_read, hari_baca, raw_data
                ) VALUES (
                    :nomen, :periode, :jenis_pelanggan, :cc, :pcezbk, :tarif, :bill_cycle, 
                    :read_method, :konsumsi, :tagihan_air, :start_read, :start_read_stan, :end_read, :hari_baca, CAST(:raw_data AS JSONB)
                ) ON CONFLICT (nomen, periode) DO UPDATE SET 
                    jenis_pelanggan=EXCLUDED.jenis_pelanggan, cc=EXCLUDED.cc, pcezbk=EXCLUDED.pcezbk,
                    tarif=EXCLUDED.tarif, bill_cycle=EXCLUDED.bill_cycle, read_method=EXCLUDED.read_method,
                    konsumsi=EXCLUDED.konsumsi, tagihan_air=EXCLUDED.tagihan_air, start_read=EXCLUDED.start_read,
                    start_read_stan=EXCLUDED.start_read_stan, end_read=EXCLUDED.end_read,
                    hari_baca=EXCLUDED.hari_baca, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql, mb_entries)
            return len(mb_entries)
        return 0

    total = process_mega_file(file_mainbill, mainbill_logic, chunk_size=500)
    return jsonify({"status": "success", "message": f"MainBill Sukses! {total} rincian meter disimpan."})

# =========================================================================
# 8. LOGIKA SBRS (ANOMALI)
# =========================================================================
def handle_sbrs_upload(file_cust, file_spot):
    cust_filename = secure_filename(file_cust.filename)
    cust_temp_path = os.path.join('instance', cust_filename)
    file_cust.save(cust_temp_path)
    
    smart_sep_cust = detect_separator(cust_temp_path, default=';')
    lookup_cust = {}

    with open(cust_temp_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter=smart_sep_cust, quotechar='"')
        if reader.fieldnames:
            reader.fieldnames = [str(col).replace('\ufeff', '').replace('"', '').strip().upper() for col in reader.fieldnames]
        for row in reader:
            nk = clean_nomen(get_val(row, ['CMR_ACCOUNT', 'NOMEN']))
            if nk: lookup_cust[nk] = row

    if os.path.exists(cust_temp_path): os.remove(cust_temp_path)

    def sbrs_logic(data_chunk):
        master_provision = [] 
        sbrs_entries = []

        for spot_row in data_chunk:
            nomen = clean_nomen(get_val(spot_row, ['NOMEN', 'CMR_ACCOUNT']))
            if not nomen: continue
            
            cust_data = lookup_cust.get(nomen, {})
            merged_row = spot_row.copy()
            merged_row.update(cust_data)
            
            nama_pel = get_val(merged_row, ['CMR_NAME', 'NAMA'], 'Pelanggan Baru')
            ab_pel = get_val(merged_row, ['AB', 'CC', 'WILAYAH'], 'AB Sunter')
            pc_ez = get_val(merged_row, ['PCEZBK', 'PCEZ'])
            if not pc_ez:
                pc = get_val(merged_row, ['PC'])
                ez = get_val(merged_row, ['EZ'])
                pc_ez = f"{pc}{ez}"
            
            master_provision.append({"nomen": nomen, "nama": nama_pel, "ab": ab_pel, "pcez": pc_ez})

            def gv(keys): return get_val(merged_row, keys)

            curr = parse_float(gv(['CURR_READ_1', 'END_READ_STAN']))
            prev = parse_float(gv(['PREV_READ_1', 'CMR_PREV_READ']))
            rata_raw = gv(['Estimation_Value', 'AVG_CONSUMPTION'])
            rata = float(rata_raw) if rata_raw else 15.0

            m3 = curr - prev
            skip_code = gv(['cmr_skip_code']).upper()
            trbl_code = gv(['cmr_trbl1_code']).upper()
            metode = gv(['Read_Method', 'cmr_read_code']).upper()

            kat = "NORMAL"
            if m3 < 0: kat = "MINUS"
            elif m3 == 0: kat = "ZERO"
            elif m3 > (rata * 2): kat = "EKSTREM"
            elif m3 < (rata * 0.5): kat = "TURUN"

            indikasi = "Aman"
            if trbl_code in ['2D', '2E', '2F', '4E']: indikasi = "FRAUD"
            elif metode in ['30/PE', '40/PE', '35/PS']: indikasi = "WARNING"
            elif skip_code in ['5G']: indikasi = "TOLAK BACA"

            merged_row['INDIKASI_SINERGI'] = indikasi
            periode_sbrs = extract_periode(gv(['BILL_PERIOD']))
            if not periode_sbrs or periode_sbrs == '000000': periode_sbrs = get_current_periode()
            
            sbrs_entries.append({
                "nomen": nomen, "periode": periode_sbrs,
                "nama": nama_pel, "ab": ab_pel, "kelurahan": gv(['KEL', 'KELURAHAN']),
                "pcez": pc_ez, "bulan_ini": m3, "rata_rata": rata, "stand_meter": curr,
                "kategori_anomali": kat, "raw_data": json.dumps(merged_row), "status_audit": 0
            })

        if master_provision:
            unique_master = {m['nomen']: m for m in master_provision}.values()
            sql_master = text("""
                INSERT INTO master_pelanggan (nomen, nama, ab, pcez) 
                VALUES (:nomen, :nama, :ab, :pcez) ON CONFLICT DO NOTHING
            """)
            db.session.execute(sql_master, list(unique_master))

        if sbrs_entries:
            sql_sbrs = text("""
                INSERT INTO data_sbrs (nomen, periode, nama, ab, kelurahan, pcez, bulan_ini, rata_rata, stand_meter, kategori_anomali, raw_data, status_audit)
                VALUES (:nomen, :periode, :nama, :ab, :kelurahan, :pcez, :bulan_ini, :rata_rata, :stand_meter, :kategori_anomali, CAST(:raw_data AS JSONB), :status_audit)
                ON CONFLICT (nomen, periode) DO UPDATE SET 
                    kategori_anomali = EXCLUDED.kategori_anomali, bulan_ini = EXCLUDED.bulan_ini, 
                    stand_meter = EXCLUDED.stand_meter, raw_data = EXCLUDED.raw_data
            """)
            db.session.execute(sql_sbrs, sbrs_entries)
            return len(sbrs_entries)
        return 0

    total_anomali = process_mega_file(file_spot, sbrs_logic, chunk_size=500)
    lookup_cust.clear()
    gc.collect()
    return jsonify({"status": "success", "message": f"Sinergi (SBRS) Sukses! {total_anomali} anomali lapangan dianalisa."})

# =========================================================================
# 9. LOGIKA ARRDEBT
# =========================================================================
def handle_arrdebt_upload(file_arrdebt):
    def arrdebt_logic(data_chunk):
        arr_entries = []
        tagihan_entries = []
        
        for row in data_chunk:
            nomen = clean_nomen(get_val(row, ['NOMEN']))
            if not nomen: continue
            
            periode = get_val(row, ['BILL_PERIODE'])
            if not periode: periode = "000000"
            nominal = parse_float(get_val(row, ['BILL_AMT', 'WATER']))
            
            arr_entries.append({"nomen": nomen, "periode": periode, "nominal": nominal, "raw_data": json.dumps(row)})
            tagihan_entries.append({"nomen": nomen, "periode": periode, "total_tagihan": nominal, "status_lunas": 0})

        if arr_entries:
            sql_arr = text("""
                INSERT INTO data_arrdebt (nomen, periode, nominal, raw_data)
                VALUES (:nomen, :periode, :nominal, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen, periode) DO UPDATE SET nominal = EXCLUDED.nominal, raw_data = EXCLUDED.raw_data
            """)
            db.session.execute(sql_arr, arr_entries)
            
            sql_tagihan = text("""
                INSERT INTO transaksi_tagihan (nomen, periode, total_tagihan, status_lunas)
                VALUES (:nomen, :periode, :total_tagihan, 0)
                ON CONFLICT (nomen, periode) DO UPDATE SET total_tagihan = EXCLUDED.total_tagihan, status_lunas = 0
            """)
            db.session.execute(sql_tagihan, tagihan_entries)
            return len(arr_entries)
        return 0

    total_arr = process_mega_file(file_arrdebt, arrdebt_logic, chunk_size=500)
    return jsonify({"status": "success", "message": f"Data ARRDEBT Sukses! {total_arr} tunggakan historis disuntikkan."})
