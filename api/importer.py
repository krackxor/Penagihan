import pandas as pd
import numpy as np  
import os
import gc
import json
import re
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy import text
from models import db, DataSBRS # Kita impor DataSBRS karena dia sudah lengkap di models.py

importer_bp = Blueprint('importer', __name__)

# ==========================================
# FUNGSI HELPER UMUM (SANGAT KRUSIAL)
# ==========================================
def clean_nomen(val):
    """Pembersih Nomen Sakti: Buang huruf 'K', buang spasi, ambil tepat 8 digit angka"""
    if not val or pd.isna(val): return None
    s = str(val).strip().upper().split('.')[0]
    s = s.replace('K', '')
    s = re.sub(r'[^0-9]', '', s) # Bersihkan karakter aneh
    if not s: return None
    return s[-8:].zfill(8)

def extract_periode(val):
    """Pintar membaca format MMYYYY (012026) atau Format Daily (1/4/26 0:00:00) -> 202601"""
    try:
        val = str(val).strip()
        if not val or val == 'None' or val == 'nan': return "000000"
        
        # Tangkap format Daily Collection: "1/4/26 0:00:00"
        if '/' in val:
            date_part = val.split(' ')[0]
            parts = date_part.split('/')
            if len(parts) == 3:
                m = parts[1].zfill(2)
                y = parts[2]
                if len(y) == 2: y = "20" + y
                return f"{y}{m}"
                
        # Tangkap format Master Bayar lama: "012026"
        if len(val) == 6 and val[2:].startswith('20'):
            return val[2:] + val[:2]
            
        return val[:6].replace('-', '')
    except: return "000000"

def parse_float(val):
    """Pintar mengubah 1.660,00 (Koma Indonesia) menjadi 1660.00 (Standar Database)"""
    try:
        if pd.isna(val) or val is None: return 0.0
        v_str = str(val).strip().replace('.', '').replace(',', '.')
        return float(v_str)
    except: return 0.0

def process_mega_file(file, logic_func, chunk_size=20000):
    """Mesin Turbo Chunking: Membaca jutaan baris tanpa bikin RAM Server jebol"""
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    if not os.path.exists('instance'): os.makedirs('instance')
    file.save(temp_path)

    try:
        reader = pd.read_csv(
            temp_path, sep=';', dtype=str, chunksize=chunk_size, 
            low_memory=False, memory_map=True, quotechar='"'
        )
        total = 0
        for chunk in reader:
            chunk.columns = chunk.columns.str.strip().str.upper()
            chunk = chunk.replace({np.nan: None})
            added_count = logic_func(chunk)
            if added_count: total += added_count
            
            db.session.commit()
            db.session.expunge_all() 
            gc.collect() 
        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

# ==========================================
# RUTE UTAMA (RADAR DETEKSI 6 JENIS FILE)
# ==========================================
@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')
    file_mc = request.files.get('file_mc')
    file_daily = request.files.get('file_daily')
    file_cid = request.files.get('file_cid')
    file_arrdebt = request.files.get('file_arrdebt')
    file_mainbill = request.files.get('file_mainbill') or request.files.get('file')

    try:
        if file_cust and file_spot: return handle_sbrs_upload(file_cust, file_spot) # 1. SBRS
        elif file_mc: return handle_mc_upload(file_mc) # 2. Master Cetak (Top 500)
        elif file_daily: return handle_daily_collection(file_daily) # 3. Master Bayar
        elif file_cid: return handle_cid_upload(file_cid) # 4. Master CID Pelanggan
        elif file_arrdebt: return handle_arrdebt_upload(file_arrdebt) # 5. Tunggakan
        elif file_mainbill: return handle_mainbill_upload(file_mainbill) # 6. Data Fix
        else: return jsonify({"status": "error", "message": "Format file tidak dikenali!"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# =========================================================================
# 1. LOGIKA SBRS (ANALISA LAPANGAN - SPOTBILL & CUSTOMER)
# =========================================================================
def handle_sbrs_upload(file_cust, file_spot):
    cust_filename = secure_filename(file_cust.filename)
    cust_temp_path = os.path.join('instance', cust_filename)
    file_cust.save(cust_temp_path)
    
    lookup_cust = {}
    cust_reader = pd.read_csv(cust_temp_path, sep=';', dtype=str, chunksize=50000, low_memory=False, quotechar='"')
    for c_chunk in cust_reader:
        c_chunk.columns = c_chunk.columns.str.strip().str.upper()
        c_chunk = c_chunk.replace({np.nan: None})
        col_key_c = 'CMR_ACCOUNT' if 'CMR_ACCOUNT' in c_chunk.columns else 'NOMEN'
        if col_key_c not in c_chunk.columns: continue
        for _, row in c_chunk.iterrows():
            nk = clean_nomen(row.get(col_key_c))
            if nk: lookup_cust[nk] = row.to_dict()
    
    if os.path.exists(cust_temp_path): os.remove(cust_temp_path)

    def sbrs_logic(df_spot_chunk):
        col_key_s = 'NOMEN' if 'NOMEN' in df_spot_chunk.columns else 'CMR_ACCOUNT'
        if col_key_s not in df_spot_chunk.columns: return 0
        
        master_provision = [] 
        sbrs_entries = []

        for _, spot_row in df_spot_chunk.iterrows():
            nomen = clean_nomen(spot_row.get(col_key_s))
            if not nomen: continue
            
            cust_data = lookup_cust.get(nomen, {})
            merged_row = spot_row.to_dict()
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

    total_anomali = process_mega_file(file_spot, sbrs_logic, chunk_size=20000)
    lookup_cust.clear()
    gc.collect()
    return jsonify({"status": "success", "message": f"Sinergi (SBRS) Sukses! {total_anomali} anomali lapangan dianalisa."})

# =========================================================================
# 2. LOGIKA MC (MASTER CETAK) -> SUMBER UTAMA TOP 500
# =========================================================================
def handle_mc_upload(file_mc):
    def mc_logic(df_chunk):
        master_provision = []
        mc_entries = []
        
        for _, row in df_chunk.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            nama_pel = str(row.get('NAMA_PEL', 'Pelanggan')).strip()
            kelurahan = str(row.get('KELURAHAN') or row.get('ALM3_PEL') or '').strip()
            pcez_raw = str(row.get('PCEZ') or row.get('ZONA_NOVAK') or '').strip()
            pcez = pcez_raw[-5:] if len(pcez_raw) > 5 else pcez_raw
            cc_raw = str(row.get('CC') or (pcez_raw[:2] if len(pcez_raw) >= 2 else '')).strip()
            ab_pel = 'AB Sunter' if cc_raw in ['34', '35'] else str(row.get('AB', 'AB Sunter')).strip()
            alamat = str(row.get('ALM1_PEL', '')).strip()
            rayon = str(row.get('RAYON') or pcez[:2] or '').strip()
            
            tahun = str(row.get('TAHUN1', ''))
            masa = str(row.get('MASA', '')).zfill(2)
            periode = f"{tahun}{masa}" if len(tahun)==4 else "202604"
            nominal = parse_float(row.get('NOMINAL') or row.get('REK_AIR'))
            
            master_provision.append({
                "nomen": nomen, "nama": nama_pel, "ab": ab_pel, "pcez": pcez,
                "kelurahan": kelurahan, "alamat": alamat, "rayon": rayon,
                "raw_data": json.dumps(row.to_dict())
            })
            
            mc_entries.append({
                "nomen": nomen, "periode": periode, "nominal": nominal, 
                "raw_data": json.dumps(row.to_dict())
            })
            
        if master_provision:
            unique_master = {m['nomen']: m for m in master_provision}.values()
            sql_master = text("""
                INSERT INTO master_pelanggan (nomen, nama, ab, pcez, kelurahan, alamat, rayon, raw_data)
                VALUES (:nomen, :nama, :ab, :pcez, :kelurahan, :alamat, :rayon, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen) DO UPDATE SET 
                    nama=EXCLUDED.nama, ab=EXCLUDED.ab, pcez=EXCLUDED.pcez, 
                    kelurahan=EXCLUDED.kelurahan, alamat=EXCLUDED.alamat, rayon=EXCLUDED.rayon, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql_master, list(unique_master))

        if mc_entries:
            sql_mc = text("""
                INSERT INTO transaksi_tagihan (nomen, periode, nominal, status_lunas, raw_data)
                VALUES (:nomen, :periode, :nominal, 0, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen, periode) DO UPDATE SET 
                    nominal=EXCLUDED.nominal, status_lunas=0, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql_mc, mc_entries)
            return len(mc_entries)
        return 0

    total = process_mega_file(file_mc, mc_logic)
    return jsonify({"status": "success", "message": f"MC Tagihan Sukses! {total} data berhasil masuk ke daftar Top 500."})

# =========================================================================
# 3. LOGIKA MASTER BAYAR (MB) -> PENYAPU BERSIH TOP 500
# =========================================================================
def handle_daily_collection(file_daily):
    def mb_logic(df_chunk):
        mb_entries = []
        lunas_entries = []
        
        for _, row in df_chunk.iterrows():
            nomen_raw = row.get('NOMEN') or row.get('CMR_ACCOUNT')
            nomen = clean_nomen(nomen_raw) 
            if not nomen: continue
            
            raw_periode = str(row.get('BULAN_REK') or row.get('BILL_PERIOD') or '')
            periode = extract_periode(raw_periode)
            tgl_bayar = str(row.get('TGL_BAYAR') or row.get('PAY_DT') or '').strip()
            nominal = parse_float(row.get('NOMINAL') or row.get('PAY_AMT'))
            denda = parse_float(row.get('DENDA'))
            lks_bayar = str(row.get('LKS_BAYAR') or row.get('PAY_LOC') or '').strip()
            
            mb_entries.append({
                "nomen": nomen, "periode": periode, "tgl_bayar": tgl_bayar,
                "nominal": nominal, "denda": denda, "lks_bayar": lks_bayar,
                "raw_data": json.dumps(row.to_dict())
            })
            lunas_entries.append({"n": nomen, "p": periode})
            
        if mb_entries:
            sql_mb = text("""
                INSERT INTO data_mb (nomen, periode, tgl_bayar, nominal, denda, lks_bayar, raw_data)
                VALUES (:nomen, :periode, :tgl_bayar, :nominal, :denda, :lks_bayar, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen, periode) DO UPDATE SET 
                    tgl_bayar = EXCLUDED.tgl_bayar, nominal = EXCLUDED.nominal,
                    denda = EXCLUDED.denda, lks_bayar = EXCLUDED.lks_bayar, raw_data = EXCLUDED.raw_data
            """)
            db.session.execute(sql_mb, mb_entries)
            
            sql_lunas = text("UPDATE transaksi_tagihan SET status_lunas = 1 WHERE nomen = :n AND periode = :p")
            db.session.execute(sql_lunas, lunas_entries)
            
        return len(mb_entries)

    total_bayar = process_mega_file(file_daily, mb_logic)
    return jsonify({"status": "success", "message": f"Daily Collection Sukses! {total_bayar} data dilunaskan dari Top 500."})

# =========================================================================
# 4. LOGIKA MASTER CID -> BUKU INDUK PELANGGAN
# =========================================================================
def handle_cid_upload(file_cid):
    def cid_logic(df_chunk):
        cid_entries = []
        for _, row in df_chunk.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            nama = str(row.get('NAMA', 'Pelanggan')).strip()
            ab = str(row.get('AB', 'AB Sunter')).strip()
            pcez = str(row.get('PCEZ', '')).strip()
            kelurahan = str(row.get('KELURAHAN', '')).strip()
            alamat = str(row.get('ALAMAT', '')).strip()
            tarif = str(row.get('TARIFF') or row.get('TARIF', '')).strip()
            rayon = str(row.get('KODE PA/PC') or pcez[:2] or '').strip()
            
            cid_entries.append({
                "nomen": nomen, "nama": nama, "ab": ab, "pcez": pcez,
                "kelurahan": kelurahan, "alamat": alamat, "rayon": rayon,
                "tarif": tarif, "raw_data": json.dumps(row.to_dict())
            })
            
        if cid_entries:
            sql_cid = text("""
                INSERT INTO master_pelanggan (nomen, nama, ab, pcez, kelurahan, alamat, rayon, tarif, raw_data)
                VALUES (:nomen, :nama, :ab, :pcez, :kelurahan, :alamat, :rayon, :tarif, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen) DO UPDATE SET 
                    nama=EXCLUDED.nama, ab=EXCLUDED.ab, pcez=EXCLUDED.pcez, 
                    kelurahan=EXCLUDED.kelurahan, alamat=EXCLUDED.alamat, 
                    rayon=EXCLUDED.rayon, tarif=EXCLUDED.tarif, raw_data=EXCLUDED.raw_data
            """)
            db.session.execute(sql_cid, cid_entries)
            return len(cid_entries)
        return 0

    total = process_mega_file(file_cid, cid_logic)
    return jsonify({"status": "success", "message": f"Master CID Sukses! {total} pelanggan diperbarui (Full JSONB)."})

# =========================================================================
# 5. LOGIKA ARRDEBT -> DATA TUNGGAKAN LAMA
# =========================================================================
def handle_arrdebt_upload(file_arrdebt):
    def arrdebt_logic(df_chunk):
        arr_entries = []
        tagihan_entries = []
        
        for _, row in df_chunk.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            periode = str(row.get('BILL_PERIODE', '')).strip()
            if not periode: periode = "000000"
            nominal = parse_float(row.get('BILL_AMT') or row.get('WATER'))
            
            arr_entries.append({"nomen": nomen, "periode": periode, "nominal": nominal, "raw_data": json.dumps(row.to_dict())})
            tagihan_entries.append({"nomen": nomen, "periode": periode, "nominal": nominal, "status_lunas": 0})

        if arr_entries:
            sql_arr = text("""
                INSERT INTO data_arrdebt (nomen, periode, nominal, raw_data)
                VALUES (:nomen, :periode, :nominal, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen, periode) DO UPDATE SET nominal = EXCLUDED.nominal, raw_data = EXCLUDED.raw_data
            """)
            db.session.execute(sql_arr, arr_entries)
            
            sql_tagihan = text("""
                INSERT INTO transaksi_tagihan (nomen, periode, nominal, status_lunas)
                VALUES (:nomen, :periode, :nominal, 0)
                ON CONFLICT (nomen, periode) DO UPDATE SET nominal = EXCLUDED.nominal, status_lunas = 0
            """)
            db.session.execute(sql_tagihan, tagihan_entries)
            
        return len(arr_entries)

    total_arr = process_mega_file(file_arrdebt, arrdebt_logic)
    return jsonify({"status": "success", "message": f"Data ARRDEBT Sukses! {total_arr} tunggakan historis disuntikkan ke Top 500."})

# =========================================================================
# 6. LOGIKA MAINBILL -> DATA FIX SBRS
# =========================================================================
def handle_mainbill_upload(file_mainbill):
    def mainbill_logic(df_chunk):
        mb_entries = []
        for _, row in df_chunk.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            p_raw = str(row.get('PERIODE_DTTM', ''))
            try:
                date_parts = p_raw.split('-')
                months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
                periode = f"20{date_parts[2][:2]}{months.get(date_parts[1])}"
            except: periode = "202604"

            total_tagihan = parse_float(row.get('TOTAL_TAGIHAN'))
            konsumsi = parse_float(row.get('KONSUMSI'))
            
            mb_entries.append({
                "nomen": nomen, "periode": periode, "total_tagihan": total_tagihan,
                "konsumsi": konsumsi, "raw_data": json.dumps(row.to_dict())
            })
            
        if mb_entries:
            sql = text("""
                INSERT INTO data_mainbill (nomen, periode, total_tagihan, konsumsi, raw_data)
                VALUES (:nomen, :periode, :total_tagihan, :konsumsi, CAST(:raw_data AS JSONB))
                ON CONFLICT (nomen, periode) DO UPDATE SET total_tagihan = EXCLUDED.total_tagihan, konsumsi = EXCLUDED.konsumsi, raw_data = EXCLUDED.raw_data
            """)
            db.session.execute(sql, mb_entries)
            return len(mb_entries)
        return 0

    total = process_mega_file(file_mainbill, mainbill_logic)
    return jsonify({"status": "success", "message": f"MainBill Sukses! {total} data fix berhasil disimpan di database."})
