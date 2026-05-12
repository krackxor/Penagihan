import os
import gc
import json
import re
import csv
import sys
from datetime import datetime
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from models import db, MasterPelanggan, TransaksiTagihan, DataMB, DataDaily, DataMainbill, DataSBRS, DataArrdebt

# Naikkan batas memori baca CSV untuk menghindari error pembacaan
csv.field_size_limit(sys.maxsize)

importer_bp = Blueprint('importer', __name__)

# ==========================================================
# 1. STRATEGI ANTI-GAGAL & DETEKSI PERIODE DARI TANGGAL
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
    """Mencari data dari berbagai kemungkinan nama kolom"""
    for k in possible_keys:
        if k in row_dict and row_dict[k] is not None:
            val = str(row_dict[k]).strip().replace('"', '')
            if val.lower() not in ['none', 'nan', 'null', '']: return val
    return default

def trim(val, length):
    """Mencegah error kepanjangan string di Postgres"""
    if not val: return ""
    return str(val)[:length]

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
    """
    LOGIKA UTAMA: Mendeteksi YYYYMM dari format tanggal DD/MM/YYYY atau MMYYYY.
    Contoh: 04/03/2026 -> 202603
    """
    try:
        val = str(val).replace('"', '').strip()
        if not val or val.lower() in ['none', 'nan', '']: return "000000"
        
        # 1. Cek format DD/MM/YYYY atau DD-MM-YYYY (misal 04/03/2026 atau 04-03-2026)
        match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', val)
        if match:
            d, m, y = match.groups()
            m = m.zfill(2)
            if len(y) == 2: y = "20" + y
            return f"{y}{m}"
            
        # 2. Cek format MMYYYY (misal 032026)
        if len(val) == 6 and val[:2].isdigit() and val[2:].isdigit():
            if 1 <= int(val[:2]) <= 12 and val[2:].startswith('20'):
                return val[2:] + val[:2]
        
        return val[:6].replace('-', '')
    except: return "000000"

def shift_period_plus_one(yyyymm):
    """N+1 Logic: Menggeser Maret (202603) menjadi April (202604) untuk periode laporan"""
    yyyymm_str = str(yyyymm).strip()
    if not yyyymm_str or len(yyyymm_str) != 6: return yyyymm_str
    try:
        y, m = int(yyyymm_str[:4]), int(yyyymm_str[4:])
        return f"{y+1}01" if m == 12 else f"{y}{m+1:02d}"
    except: return yyyymm_str

def parse_float(val):
    """SMART NUMBER PARSER: Pendeteksi otomatis Nominal Uang Anti-Gagal"""
    try:
        if not val: return 0.0
        v_str = str(val).replace('"', '').strip()
        
        # Hapus semua huruf 'Rp', spasi, dan karakter aneh (Sisakan angka, koma, titik, minus)
        v_str = re.sub(r'[^\d,\.-]', '', v_str)
        if not v_str: return 0.0
        
        # Logika Pemecah Format Uang Indo vs US
        if ',' in v_str and '.' in v_str:
            if v_str.rfind(',') > v_str.rfind('.'):
                v_str = v_str.replace('.', '').replace(',', '.')
            else:
                v_str = v_str.replace(',', '')
        elif ',' in v_str:
            v_str = v_str.replace(',', '.')
        elif '.' in v_str:
            if len(v_str) - v_str.rfind('.') - 1 != 2:
                v_str = v_str.replace('.', '')
                
        return float(v_str)
    except:
        return 0.0

def get_safe_json(row_dict):
    """Mencegah Postgres mati karena JSON raksasa."""
    try:
        if len(json.dumps(row_dict)) > 15000: 
            return {"info": "Data terpotong otomatis karena format file cacat dari pusat."}
        return row_dict
    except:
        return {}

def clean_file_stream(f):
    """Membuang Karakter Null Byte yang mematikan Postgres"""
    for line in f:
        yield line.replace('\x00', '').replace('\0', '')

def process_mega_file(file, logic_func, chunk_size=250, default_sep=';'):
    """MESIN PURE PYTHON STREAMING"""
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    if not os.path.exists('instance'): os.makedirs('instance')
    file.save(temp_path)

    smart_sep = detect_separator(temp_path, default=default_sep)
    total = 0

    try:
        with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(clean_file_stream(f), delimiter=smart_sep, quotechar='"')
            
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
            
            cid_entries.append({
                "nomen": trim(nomen, 50),
                "norek": trim(get_val(row, ['NOREK', 'NO_REK']), 50),
                "nama": trim(get_val(row, ['NAMA', 'NAMA_PEL', 'NAMA_PELANGGAN'], 'Pelanggan Baru'), 150),
                "status": trim(get_val(row, ['STATUS']), 50),
                "tipeplggn": trim(tipe_bersih, 50),
                "custclass": trim(get_val(row, ['CUSTCLASS', 'CUST_CLASS']), 100),
                "tarif": trim(get_val(row, ['TARIFF', 'TARIF', 'GOL_TARIF']), 20),
                "alamat": get_val(row, ['ALAMAT', 'ALM1_PEL']),
                "kodepos": trim(get_val(row, ['KODEPOS', 'KODE_POS']), 10),
                "kelurahan": trim(get_val(row, ['KELURAHAN', 'KEL']), 100),
                "kecamatan": trim(get_val(row, ['KECAMATAN', 'KEC']), 100),
                "kota": trim(get_val(row, ['KOTA / KABUPATEN', 'KOTA', 'KABUPATEN']), 100),
                "ab": trim(get_val(row, ['AB', 'WILAYAH'], 'AB Sunter'), 50),
                "regional": trim(get_val(row, ['REGIONAL', 'REGION']), 50),
                "cc": trim(get_val(row, ['CC']), 20),
                "kode_pa_pc": trim(get_val(row, ['KODE PA/PC', 'KODE_PA_PC', 'PC']), 20),
                "zona_novak": trim(get_val(row, ['ZONA_NOVAK', 'ZONA']), 50),
                "pcez": trim(get_val(row, ['PCEZ', 'PCEZBK']), 20),
                "rayon": trim(get_val(row, ['RAYON', 'KODE PA/PC', 'PCEZ']), 50),
                "cycle": trim(get_val(row, ['CYCLE', 'BILL_CYCLE']), 20),
                "merk": trim(get_val(row, ['MERK', 'MERK_METER']), 50),
                "serial": trim(get_val(row, ['SERIAL', 'NO_METER', 'NOMET']), 100),
                "hp": trim(get_val(row, ['HP', 'NO_HP']), 50),
                "tlp": trim(get_val(row, ['TLP', 'TELEPON']), 50),
                "wa": trim(get_val(row, ['WA', 'WHATSAPP']), 50),
                "email": trim(get_val(row, ['EMAIL']), 100),
                "fax": trim(get_val(row, ['FAX']), 50),
                "latitude": trim(get_val(row, ['LATITUDE', 'LAT']), 50),
                "longitude": trim(get_val(row, ['LONGITUDE', 'LONG']), 50),
                "raw_data": get_safe_json(row) 
            })
            
        if cid_entries:
            stmt = insert(MasterPelanggan).values(cid_entries)
            update_dict = {c.name: getattr(stmt.excluded, c.name) for c in MasterPelanggan.__table__.columns if c.name != 'nomen'}
            stmt = stmt.on_conflict_do_update(index_elements=['nomen'], set_=update_dict)
            db.session.execute(stmt)
            return len(cid_entries)
        return 0

    total = process_mega_file(file_cid, cid_logic, chunk_size=250)
    return jsonify({"status": "success", "message": f"Master CID Sukses! {total} pelanggan diperbarui."})

# =========================================================================
# 4. LOGIKA MC (MASTER CETAK) - TGL_CATAT DETECTOR
# =========================================================================
def handle_mc_upload(file_mc):
    def mc_logic(data_chunk):
        mc_entries = []
        for row in data_chunk:
            nomen = clean_nomen(get_val(row, ['NOMEN', 'ACCT_ID']))
            if not nomen: continue
            
            # Mendeteksi dari TGL_CATAT untuk memastikan presisi bulan (Misal: 04/03/2026 -> 202603)
            tgl_catat = get_val(row, ['TGL_CATAT', 'TANGGAL_BACA', 'PERIODE', 'BLNTAG'])
            periode_asli = extract_periode(tgl_catat)
            
            # Gunakan N+1: Data Maret (202603) disimpan sebagai periode 202604
            periode_target = shift_period_plus_one(periode_asli)

            mc_entries.append({
                "nomen": trim(nomen, 50),
                "periode": trim(periode_target, 10),
                "alm1_pel": get_val(row, ['ALM1_PEL', 'ALAMAT']),
                "zona_novak": trim(get_val(row, ['ZONA_NOVAK', 'ZONA']), 50),
                "notagihan": trim(get_val(row, ['NOTAGIHAN', 'NO_TAGIHAN']), 50),
                "total_tagihan": parse_float(get_val(row, ['NOMINAL', 'REK_AIR', 'TOTAL_TAGIHAN', 'TAGIHAN'])),
                "status_lunas": 0,
                "raw_data": get_safe_json(row)
            })
            
        if mc_entries:
            stmt = insert(TransaksiTagihan).values(mc_entries)
            stmt = stmt.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={
                    'alm1_pel': stmt.excluded.alm1_pel,
                    'zona_novak': stmt.excluded.zona_novak,
                    'notagihan': stmt.excluded.notagihan,
                    'total_tagihan': stmt.excluded.total_tagihan,
                    'status_lunas': 0,
                    'raw_data': stmt.excluded.raw_data
                }
            )
            db.session.execute(stmt)
            return len(mc_entries)
        return 0

    total = process_mega_file(file_mc, mc_logic, chunk_size=250)
    return jsonify({"status": "success", "message": f"MC Tagihan Sukses! {total} data Tagihan tercatat."})

# =========================================================================
# 5. LOGIKA MASTER BAYAR (MB) - TGL_BAYAR DETECTOR
# =========================================================================
def handle_mb_upload(file_mb):
    def mb_logic(data_chunk):
        mb_entries = []
        lunas_entries = []
        for row in data_chunk:
            nomen = clean_nomen(get_val(row, ['NOMEN', 'CMR_ACCOUNT']))
            if not nomen: continue
            
            # Mendeteksi dari TGL_BAYAR (Contoh: 31/03/2026 -> 202603)
            tgl_bayar_raw = get_val(row, ['TGL_BAYAR', 'PAY_DT'])
            periode_asli = extract_periode(tgl_bayar_raw)
            
            # Geser N+1 agar sesuai dengan periode tagihan MC di DB
            periode_target = shift_period_plus_one(periode_asli)
            
            mb_entries.append({
                "nomen": trim(nomen, 50),
                "periode": trim(periode_target, 10),
                "bulan_rek": trim(get_val(row, ['BULAN_REK', 'BulanRek']), 20),
                "tgl_bayar": trim(tgl_bayar_raw, 50),
                "nominal": parse_float(get_val(row, ['NOMINAL', 'RPBAYAR', 'PAY_AMT', 'TOTAL_BAYAR'])),
                "denda": parse_float(get_val(row, ['DENDA', 'PENALTY'])),
                "lks_bayar": trim(get_val(row, ['LKS_BAYAR', 'PAY_LOC']), 100),
                "notagihan": trim(get_val(row, ['NOTAGIHAN', 'BILL_ID']), 50),
                "raw_data": get_safe_json(row)
            })
            lunas_entries.append({"n": trim(nomen, 50), "p": trim(periode_target, 10)})
            
        if mb_entries:
            stmt = insert(DataMB).values(mb_entries)
            stmt = stmt.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={
                    'bulan_rek': stmt.excluded.bulan_rek,
                    'tgl_bayar': stmt.excluded.tgl_bayar,
                    'nominal': stmt.excluded.nominal,
                    'denda': stmt.excluded.denda,
                    'lks_bayar': stmt.excluded.lks_bayar,
                    'notagihan': stmt.excluded.notagihan,
                    'raw_data': stmt.excluded.raw_data
                }
            )
            db.session.execute(stmt)
            
            if lunas_entries:
                sql_lunas = text("UPDATE transaksi_tagihan SET status_lunas = 1 WHERE nomen = :n AND periode = :p")
                db.session.execute(sql_lunas, lunas_entries)
            return len(mb_entries)
        return 0

    total_bayar = process_mega_file(file_mb, mb_logic, chunk_size=250)
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
            
            bill_period_raw = get_val(row, ['BILL_PERIOD', 'PERIODE_DTTM'])
            periode_asli = extract_periode(bill_period_raw)
            periode_target = shift_period_plus_one(periode_asli)

            daily_entries.append({
                "nomen": trim(nomen, 50),
                "periode": trim(periode_target, 10),
                "pay_dt": trim(get_val(row, ['PAY_DT', 'TGL_BAYAR']), 50),
                "bill_period": trim(bill_period_raw, 50),
                "pay_amt": parse_float(get_val(row, ['PAY_AMT', 'NOMINAL', 'TOTAL_BAYAR'])),
                "pay_status_flg": trim(get_val(row, ['PAY_STATUS_FLG', 'STATUS_FLG']), 20),
                "bill_type": trim(get_val(row, ['BILL_TYPE', 'JENIS']), 50),
                "typecust1": trim(tipe_bersih, 50),
                "pay_loc": trim(get_val(row, ['PAY_LOC', 'LKS_BAYAR']), 100),
                "bill_id": trim(get_val(row, ['BILL_ID', 'NOTAGIHAN']), 50),
                "ab": trim(get_val(row, ['AB', 'WILAYAH']), 50),
                "status": trim(get_val(row, ['STATUS']), 50),
                "raw_data": get_safe_json(row)
            })
            
            status_flag = get_val(row, ['PAY_STATUS_FLG', 'STATUS_FLG'])
            if status_flag in ['1', '50', 'LUNAS']:
                lunas_entries.append({"n": trim(nomen, 50), "p": trim(periode_target, 10)})
            
        if daily_entries:
            stmt = insert(DataDaily).values(daily_entries)
            stmt = stmt.on_conflict_do_update(
                index_elements=['nomen', 'bill_id'],
                set_={
                    'periode': stmt.excluded.periode,
                    'pay_dt': stmt.excluded.pay_dt,
                    'bill_period': stmt.excluded.bill_period,
                    'pay_amt': stmt.excluded.pay_amt,
                    'pay_status_flg': stmt.excluded.pay_status_flg,
                    'bill_type': stmt.excluded.bill_type,
                    'typecust1': stmt.excluded.typecust1,
                    'pay_loc': stmt.excluded.pay_loc,
                    'ab': stmt.excluded.ab,
                    'status': stmt.excluded.status,
                    'raw_data': stmt.excluded.raw_data
                }
            )
            db.session.execute(stmt)
            
            if lunas_entries:
                sql_lunas = text("UPDATE transaksi_tagihan SET status_lunas = 1 WHERE nomen = :n AND periode = :p")
                db.session.execute(sql_lunas, lunas_entries)
            return len(daily_entries)
        return 0

    total = process_mega_file(file_daily, daily_logic, chunk_size=250)
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
                "nomen": trim(nomen, 50),
                "periode": trim(periode_target, 10),
                "jenis_pelanggan": trim(get_val(row, ['JENIS_PELANGGAN', 'TYPECUST1']), 100),
                "cc": trim(get_val(row, ['CC']), 20),
                "pcezbk": trim(get_val(row, ['PCEZBK', 'PCEZ']), 20),
                "tarif": trim(get_val(row, ['TARIF', 'TARIFF']), 20),
                "bill_cycle": trim(get_val(row, ['BILL_CYCLE', 'CYCLE']), 20),
                "read_method": trim(get_val(row, ['READ_METHOD']), 50),
                "konsumsi": parse_float(get_val(row, ['KONSUMSI', 'VOL'])),
                "tagihan_air": parse_float(get_val(row, ['TAGIHAN_AIR', 'REK_AIR'])),
                "start_read": trim(get_val(row, ['START_READ']), 50),
                "start_read_stan": trim(get_val(row, ['START_READ_STAN', 'STAN_AWAL']), 50),
                "end_read": trim(end_read_raw, 50),
                "hari_baca": trim(get_val(row, ['HARI_BACA', 'HB']), 20),
                "raw_data": get_safe_json(row)
            })
            
        if mb_entries:
            stmt = insert(DataMainbill).values(mb_entries)
            stmt = stmt.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={
                    'jenis_pelanggan': stmt.excluded.jenis_pelanggan,
                    'cc': stmt.excluded.cc,
                    'pcezbk': stmt.excluded.pcezbk,
                    'tarif': stmt.excluded.tarif,
                    'bill_cycle': stmt.excluded.bill_cycle,
                    'read_method': stmt.excluded.read_method,
                    'konsumsi': stmt.excluded.konsumsi,
                    'tagihan_air': stmt.excluded.tagihan_air,
                    'start_read': stmt.excluded.start_read,
                    'start_read_stan': stmt.excluded.start_read_stan,
                    'end_read': stmt.excluded.end_read,
                    'hari_baca': stmt.excluded.hari_baca,
                    'raw_data': stmt.excluded.raw_data
                }
            )
            db.session.execute(stmt)
            return len(mb_entries)
        return 0

    total = process_mega_file(file_mainbill, mainbill_logic, chunk_size=250)
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
        reader = csv.DictReader(clean_file_stream(f), delimiter=smart_sep_cust, quotechar='"')
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
            
            master_provision.append({"nomen": trim(nomen, 50), "nama": trim(nama_pel, 150), "ab": trim(ab_pel, 50), "pcez": trim(pc_ez, 20)})

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
                "nomen": trim(nomen, 50), "periode": trim(periode_sbrs, 10),
                "nama": trim(nama_pel, 150), "ab": trim(ab_pel, 50), "kelurahan": trim(gv(['KEL', 'KELURAHAN']), 100),
                "pcez": trim(pc_ez, 20), "bulan_ini": m3, "rata_rata": rata, "stand_meter": curr,
                "kategori_anomali": trim(kat, 50), "raw_data": get_safe_json(merged_row), "status_audit": 0
            })

        if master_provision:
            stmt_master = insert(MasterPelanggan).values(master_provision)
            stmt_master = stmt_master.on_conflict_do_nothing()
            db.session.execute(stmt_master)

        if sbrs_entries:
            stmt = insert(DataSBRS).values(sbrs_entries)
            stmt = stmt.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={
                    'kategori_anomali': stmt.excluded.kategori_anomali,
                    'bulan_ini': stmt.excluded.bulan_ini,
                    'stand_meter': stmt.excluded.stand_meter,
                    'raw_data': stmt.excluded.raw_data
                }
            )
            db.session.execute(stmt)
            return len(sbrs_entries)
        return 0

    total_anomali = process_mega_file(file_spot, sbrs_logic, chunk_size=250)
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
            
            arr_entries.append({"nomen": trim(nomen, 50), "periode": trim(periode, 10), "nominal": nominal, "raw_data": get_safe_json(row)})
            tagihan_entries.append({"nomen": trim(nomen, 50), "periode": trim(periode, 10), "total_tagihan": nominal, "status_lunas": 0})

        if arr_entries:
            stmt = insert(DataArrdebt).values(arr_entries)
            stmt = stmt.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={
                    'nominal': stmt.excluded.nominal,
                    'raw_data': stmt.excluded.raw_data
                }
            )
            db.session.execute(stmt)
            
            stmt_tagihan = insert(TransaksiTagihan).values(tagihan_entries)
            stmt_tagihan = stmt_tagihan.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={
                    'total_tagihan': stmt_tagihan.excluded.total_tagihan,
                    'status_lunas': 0
                }
            )
            db.session.execute(stmt_tagihan)
            return len(arr_entries)
        return 0

    total_arr = process_mega_file(file_arrdebt, arrdebt_logic, chunk_size=250)
    return jsonify({"status": "success", "message": f"Data ARRDEBT Sukses! {total_arr} tunggakan historis disuntikkan."})
