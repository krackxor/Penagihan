import os
import gc
import json
import re
import polars as pl
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy import text
from models import db, DataSBRS

importer_bp = Blueprint('importer', __name__)

# ==========================================
# FUNGSI HELPER UMUM & AUTO-SNIFFER (CERDAS)
# ==========================================
def detect_separator(filepath, default='|'):
    """Deteksi otomatis pemisah kolom dengan membaca baris pertama file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            # Hitung kandidat separator
            counts = {
                '|': first_line.count('|'),
                ';': first_line.count(';'),
                ',': first_line.count(',')
            }
            # Cari separator dengan jumlah penggunaan terbanyak di baris pertama
            best_sep = max(counts, key=counts.get)
            
            # Pastikan separator memang ada
            if counts[best_sep] > 0:
                return best_sep
            return default
    except Exception:
        return default

def clean_nomen(val):
    """Membersihkan Nomen: Ambil 8 digit angka terakhir, bebas huruf/spasi"""
    if not val or val is None: return None
    s = str(val).strip().upper().split('.')[0]
    s = s.replace('K', '')
    s = re.sub(r'[^0-9]', '', s)
    if not s: return None
    return s[-8:].zfill(8)

def extract_periode(val):
    """Membaca periode asli dari berbagai sumber text (Output standar YYYYMM)"""
    try:
        val = str(val).strip()
        if not val or val == 'None' or val == 'nan': return "000000"
        
        # Format Daily Collection: "1/4/26 0:00:00" atau "01/04/2026"
        if '/' in val:
            date_part = val.split(' ')[0]
            parts = date_part.split('/')
            if len(parts) == 3:
                m = parts[1].zfill(2)
                y = parts[2]
                if len(y) == 2: y = "20" + y
                return f"{y}{m}"
                
        # Format MB lama: "012026" -> Jadi "202601"
        if len(val) == 6 and val[2:].startswith('20'):
            return val[2:] + val[:2]
            
        return val[:6].replace('-', '')
    except: return "000000"

def shift_period_plus_one(yyyymm):
    """
    AUTO TIME-SHIFT V18.
    Tagihan Maret (202603) selalu dibayar/ditagih pada April (202604).
    Ini menggeser bulan +1 untuk sinkronisasi target vs realisasi.
    """
    yyyymm_str = str(yyyymm).strip()
    if not yyyymm_str or len(yyyymm_str) != 6: return yyyymm_str
    try:
        year, month = int(yyyymm_str[:4]), int(yyyymm_str[4:])
        if month == 12: return f"{year+1}01"
        return f"{year}{month+1:02d}"
    except: return yyyymm_str

def parse_float(val):
    try:
        if val is None or str(val).strip() == '': return 0.0
        v_str = str(val).strip().replace('.', '').replace(',', '.')
        return float(v_str)
    except: return 0.0

def process_mega_file(file, logic_func, chunk_size=20000, default_sep='|'):
    """Mesin Polars Batched Reader untuk Hemat RAM (V18 Standard) dilengkapi Sniffer"""
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    if not os.path.exists('instance'): os.makedirs('instance')
    file.save(temp_path)

    # Deteksi pemisah (separator) cerdas secara otomatis
    smart_sep = detect_separator(temp_path, default=default_sep)

    try:
        reader = pl.read_csv_batched(
            temp_path, separator=smart_sep, infer_schema_length=0, 
            quote_char='"', batch_size=chunk_size, ignore_errors=True
        )
        total = 0
        batches = reader.next_batches(1)
        
        while batches:
            chunk = batches[0]
            # Standarisasi header huruf besar tanpa spasi depan/belakang
            chunk = chunk.rename({col: col.strip().upper() for col in chunk.columns})
            
            added_count = logic_func(chunk)
            if added_count: total += added_count
            
            db.session.commit()
            db.session.expunge_all() 
            gc.collect() 
            
            batches = reader.next_batches(1)
            
        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

# ==========================================
# RUTE UTAMA UPLOAD SAKTI V18
# ==========================================
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
        print(traceback.format_exc()) # Log ke Docker jika error
        return jsonify({"status": "error", "message": f"Fatal System Error: {str(e)}"}), 500


# =========================================================================
# 1. LOGIKA SBRS
# =========================================================================
def handle_sbrs_upload(file_cust, file_spot):
    cust_filename = secure_filename(file_cust.filename)
    cust_temp_path = os.path.join('instance', cust_filename)
    file_cust.save(cust_temp_path)
    
    # Deteksi pemisah khusus untuk file customer.txt
    smart_sep_cust = detect_separator(cust_temp_path, default=';')

    lookup_cust = {}
    cust_reader = pl.read_csv_batched(cust_temp_path, separator=smart_sep_cust, infer_schema_length=0, quote_char='"', batch_size=50000)
    c_batches = cust_reader.next_batches(1)
    
    while c_batches:
        c_chunk = c_batches[0]
        c_chunk = c_chunk.rename({col: col.strip().upper() for col in c_chunk.columns})
        col_key_c = 'CMR_ACCOUNT' if 'CMR_ACCOUNT' in c_chunk.columns else 'NOMEN'
        
        if col_key_c in c_chunk.columns:
            for row in c_chunk.to_dicts():
                nk = clean_nomen(row.get(col_key_c))
                if nk: lookup_cust[nk] = row
        c_batches = cust_reader.next_batches(1)
    
    if os.path.exists(cust_temp_path): os.remove(cust_temp_path)

    def sbrs_logic(df_spot_chunk):
        col_key_s = 'NOMEN' if 'NOMEN' in df_spot_chunk.columns else 'CMR_ACCOUNT'
        if col_key_s not in df_spot_chunk.columns: return 0
        
        master_provision = [] 
        sbrs_entries = []

        for spot_row in df_spot_chunk.to_dicts():
            nomen = clean_nomen(spot_row.get(col_key_s))
            if not nomen: continue
            
            cust_data = lookup_cust.get(nomen, {})
            merged_row = spot_row.copy()
            merged_row.update(cust_data)
            
            nama_pel = merged_row.get('CMR_NAME') or merged_row.get('NAMA') or 'Pelanggan Baru'
            ab_pel = merged_row.get('AB') or merged_row.get('CC') or 'AB Sunter'
            pc_ez = merged_row.get('PCEZBK') or (str(merged_row.get('PC','') or '') + str(merged_row.get('EZ','') or ''))
            
            master_provision.append({"nomen": nomen, "nama": nama_pel, "ab": ab_pel, "pcez": pc_ez})

            def get_val(key):
                key_l = key.lower()
                for k, v in merged_row.items():
                    if str(k).lower() == key_l: return v
                return None

            try:
                curr = float(get_val('CURR_READ_1') or get_val('END_READ_STAN') or 0)
                prev = float(get_val('PREV_READ_1') or get_val('CMR_PREV_READ') or 0)
                raw_rata = get_val('Estimation_Value') or get_val('AVG_CONSUMPTION')
                rata = float(raw_rata) if raw_rata else 15.0
            except: curr, prev, rata = 0, 0, 15.0

            m3 = curr - prev
            skip_code = str(get_val('cmr_skip_code') or '').strip().upper()
            trbl_code = str(get_val('cmr_trbl1_code') or '').strip().upper()
            metode = str(get_val('Read_Method') or get_val('cmr_read_code') or '').strip().upper()

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
            
            sbrs_entries.append({
                "nomen": nomen, "periode": extract_periode(merged_row.get('BILL_PERIOD') or '202605'),
                "nama": nama_pel, "ab": ab_pel, "kelurahan": merged_row.get('KEL') or merged_row.get('KELURAHAN', ''),
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

    total_anomali = process_mega_file(file_spot, sbrs_logic, chunk_size=20000, default_sep=';')
    lookup_cust.clear()
    gc.collect()
    return jsonify({"status": "success", "message": f"Sinergi (SBRS) Sukses! {total_anomali} anomali lapangan dianalisa."})

# =========================================================================
# 2. LOGIKA ARRDEBT
# =========================================================================
def handle_arrdebt_upload(file_arrdebt):
    def arrdebt_logic(df_chunk):
        arr_entries = []
        tagihan_entries = []
        
        for row in df_chunk.to_dicts():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            periode = str(row.get('BILL_PERIODE', '')).strip()
            if not periode: periode = "000000"
            nominal = parse_float(row.get('BILL_AMT') or row.get('WATER'))
            
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

    total_arr = process_mega_file(file_arrdebt, arrdebt_logic, default_sep=';')
    return jsonify({"status": "success", "message": f"Data ARRDEBT Sukses! {total_arr} tunggakan historis disuntikkan."})


# =========================================================================
# 3. LOGIKA MASTER CID 
# =========================================================================
def handle_cid_upload(file_cid):
    def cid_logic(df_chunk):
        cid_entries = []
        for row in df_chunk.to_dicts():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            cid_entries.append({
                "nomen": nomen,
                "norek": str(row.get('NOREK', '')).strip(),
                "nama": str(row.get('NAMA', 'Pelanggan')).strip(),
                "status": str(row.get('STATUS', '')).strip(),
                "tipeplggn": str(row.get('TIPEPLGGN', '')).strip(),
                "custclass": str(row.get('CUSTCLASS', '')).strip(),
                "tarif": str(row.get('TARIFF') or row.get('TARIF', '')).strip(),
                "alamat": str(row.get('ALAMAT', '')).strip(),
                "kodepos": str(row.get('KODEPOS', '')).strip(),
                "kelurahan": str(row.get('KELURAHAN', '')).strip(),
                "kecamatan": str(row.get('KECAMATAN', '')).strip(),
                "kota": str(row.get('KOTA / KABUPATEN', '')).strip(),
                "ab": str(row.get('AB', 'AB Sunter')).strip(),
                "regional": str(row.get('REGIONAL', '')).strip(),
                "cc": str(row.get('CC', '')).strip(),
                "kode_pa_pc": str(row.get('KODE PA/PC', '')).strip(),
                "zona_novak": str(row.get('ZONA_NOVAK', '')).strip(),
                "pcez": str(row.get('PCEZ', '')).strip(),
                "rayon": str(row.get('KODE PA/PC') or str(row.get('PCEZ', ''))[:2] or '').strip(),
                "cycle": str(row.get('CYCLE', '')).strip(),
                "merk": str(row.get('MERK', '')).strip(),
                "serial": str(row.get('SERIAL', '')).strip(),
                "hp": str(row.get('HP', '')).strip(),
                "tlp": str(row.get('TLP', '')).strip(),
                "wa": str(row.get('WA', '')).strip(),
                "email": str(row.get('EMAIL', '')).strip(),
                "fax": str(row.get('FAX', '')).strip(),
                "latitude": str(row.get('LATITUDE', '')).strip(),
                "longitude": str(row.get('LONGITUDE', '')).strip(),
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

    # PERHATIAN: Baris TRUNCATE di bawah ini telah DIMATIKAN untuk mencegah error Server Closed Connection.
    # db.session.execute(text("TRUNCATE TABLE master_pelanggan CASCADE"))
    total = process_mega_file(file_cid, cid_logic, default_sep='|')
    return jsonify({"status": "success", "message": f"Master CID Sukses! {total} pelanggan diperbarui (Full 28 Kolom)."})


# =========================================================================
# 4. LOGIKA MC (MASTER CETAK) -> AUTO TIME-SHIFT
# =========================================================================
def handle_mc_upload(file_mc):
    def mc_logic(df_chunk):
        mc_entries = []
        for row in df_chunk.to_dicts():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            # Deteksi Akurat Periode
            if 'TAHUN2' in row and 'NAMA_BLN2' in row and str(row['TAHUN2']).strip():
                tahun = str(row['TAHUN2']).strip()
                bulan = str(row['NAMA_BLN2']).strip().zfill(2)
                periode_target = f"{tahun}{bulan}"
            else:
                periode_asli = extract_periode(row.get('PERIODE') or row.get('BLNTAG'))
                periode_target = shift_period_plus_one(periode_asli)

            mc_entries.append({
                "nomen": nomen,
                "periode": periode_target,
                "alm1_pel": str(row.get('ALM1_PEL', '')).strip(),
                "zona_novak": str(row.get('ZONA_NOVAK', '')).strip(),
                "notagihan": str(row.get('NOTAGIHAN', '')).strip(),
                "total_tagihan": parse_float(row.get('NOMINAL') or row.get('REK_AIR')),
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

    total = process_mega_file(file_mc, mc_logic, default_sep='|')
    return jsonify({"status": "success", "message": f"MC Tagihan Sukses! {total} data Tagihan tercatat."})


# =========================================================================
# 5. LOGIKA MASTER BAYAR (MB)
# =========================================================================
def handle_mb_upload(file_mb):
    def mb_logic(df_chunk):
        mb_entries = []
        lunas_entries = []
        
        for row in df_chunk.to_dicts():
            nomen = clean_nomen(row.get('NOMEN') or row.get('CMR_ACCOUNT'))
            if not nomen: continue
            
            bulan_rek_raw = str(row.get('BULAN_REK') or '').strip()
            periode_asli = extract_periode(bulan_rek_raw if bulan_rek_raw else row.get('PERIODE'))
            periode_target = shift_period_plus_one(periode_asli)
            
            mb_entries.append({
                "nomen": nomen,
                "periode": periode_target,
                "bulan_rek": bulan_rek_raw,
                "tgl_bayar": str(row.get('TGL_BAYAR', '')).strip(),
                "nominal": parse_float(row.get('NOMINAL') or row.get('RPBAYAR')),
                "denda": parse_float(row.get('DENDA')),
                "lks_bayar": str(row.get('LKS_BAYAR', '')).strip(),
                "notagihan": str(row.get('NOTAGIHAN', '')).strip(),
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
            
            sql_lunas = text("UPDATE transaksi_tagihan SET status_lunas = 1 WHERE nomen = :n AND periode = :p")
            db.session.execute(sql_lunas, lunas_entries)
            return len(mb_entries)
        return 0

    total_bayar = process_mega_file(file_mb, mb_logic, default_sep='|')
    return jsonify({"status": "success", "message": f"Master Bayar (MB) Sukses! {total_bayar} dilunaskan."})


# =========================================================================
# 6. LOGIKA KOLEKSI HARIAN (DAILY DATA) -> DIGABUNG KE TABEL DATA_MB
# =========================================================================
def handle_daily_upload(file_daily):
    def daily_logic(df_chunk):
        mb_entries = []
        lunas_entries = []
        
        for row in df_chunk.to_dicts():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            # Dari file Daily, BILL_PERIOD berformat: '01/03/2026'
            # Kita ekstrak jadi format standar (202603) lalu di-shift (+1 Bulan) -> 202604
            bill_period_raw = str(row.get('BILL_PERIOD', '')).strip()
            periode_asli = extract_periode(bill_period_raw)
            periode_target = shift_period_plus_one(periode_asli)
            
            # Format bulan rek (MMYYYY) untuk kolom bulan_rek di data_mb
            bulan_rek_val = ""
            if bill_period_raw and '/' in bill_period_raw:
                parts = bill_period_raw.split('/')
                if len(parts) == 3:
                    y = parts[2]
                    if len(y) == 2: y = "20" + y
                    bulan_rek_val = f"{parts[1].zfill(2)}{y}"

            mb_entries.append({
                "nomen": nomen,
                "periode": periode_target,
                "bulan_rek": bulan_rek_val,
                "tgl_bayar": str(row.get('PAY_DT', '')).strip(),
                "nominal": parse_float(row.get('PAY_AMT')),
                "denda": 0, # Daily biasanya tidak ada denda terpisah, atau gabung di raw
                "lks_bayar": str(row.get('PAY_LOC', '')).strip(),
                "notagihan": str(row.get('BILL_ID', '')).strip(),
                "raw_data": json.dumps(row)
            })
            
            if str(row.get('PAY_STATUS_FLG', '')).strip() == '1':
                lunas_entries.append({"n": nomen, "p": periode_target})
            
        if mb_entries:
            # Kita simpan data Harian ke dalam data_mb agar fungsi Daily engine Anda terbaca sempurna
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

    total = process_mega_file(file_daily, daily_logic, default_sep='|')
    return jsonify({"status": "success", "message": f"Koleksi Harian Sukses! {total} pembayaran disinkronkan ke DB."})


# =========================================================================
# 7. LOGIKA MAINBILL
# =========================================================================
def handle_mainbill_upload(file_mainbill):
    def mainbill_logic(df_chunk):
        mb_entries = []
        for row in df_chunk.to_dicts():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            # Ekstrak dari END_READ (DD/MM/YYYY)
            end_read_raw = str(row.get('END_READ', '')).strip()
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
                "jenis_pelanggan": str(row.get('JENIS_PELANGGAN', '')).strip(),
                "cc": str(row.get('CC', '')).strip(),
                "pcezbk": str(row.get('PCEZBK', '')).strip(),
                "tarif": str(row.get('TARIF', '')).strip(),
                "bill_cycle": str(row.get('BILL_CYCLE', '')).strip(),
                "read_method": str(row.get('READ_METHOD', '')).strip(),
                "konsumsi": parse_float(row.get('KONSUMSI')),
                "tagihan_air": parse_float(row.get('TAGIHAN_AIR')),
                "start_read": str(row.get('START_READ', '')).strip(),
                "start_read_stan": str(row.get('START_READ_STAN', '')).strip(),
                "end_read": end_read_raw,
                "hari_baca": str(row.get('HARI_BACA', '')).strip(),
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

    total = process_mega_file(file_mainbill, mainbill_logic, default_sep='|')
    return jsonify({"status": "success", "message": f"MainBill Sukses! {total} rincian meter lapangan disimpan."})
