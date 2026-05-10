import pandas as pd
import numpy as np  
import os
import gc
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy.dialects.postgresql import insert
from models import db, MasterPelanggan, TransaksiTagihan, DataSBRS

importer_bp = Blueprint('importer', __name__)

# ==========================================
# FUNGSI HELPER UMUM
# ==========================================
def clean_nomen(val):
    if not val or pd.isna(val): return None
    s = str(val).strip().split('.')[0]
    return s[-8:].zfill(8)

def extract_periode(val):
    try:
        val = str(val).strip()
        if len(val) == 6 and val[2:].startswith('20'):
            return val[2:] + val[:2]
        return val[:6]
    except:
        return "202605"

def parse_float(val):
    """Konversi string ber-koma (1.660,00) menjadi float murni (1660.00) dari file MC"""
    try:
        if pd.isna(val) or val is None: return 0.0
        v_str = str(val).strip().replace('.', '').replace(',', '.')
        return float(v_str)
    except:
        return 0.0

def process_mega_file(file, logic_func, chunk_size=20000):
    """Mesin Turbo Chunking: Hemat RAM untuk file raksasa."""
    filename = secure_filename(file.filename)
    temp_path = os.path.join('instance', filename)
    
    if not os.path.exists('instance'):
        os.makedirs('instance')
        
    file.save(temp_path)

    try:
        # quotechar='"' penting untuk MC karena datanya diapit kutip ganda ("REG";"34")
        reader = pd.read_csv(
            temp_path, sep=';', dtype=str, chunksize=chunk_size, 
            low_memory=False, memory_map=True, quotechar='"'
        )
        total = 0
        for chunk in reader:
            chunk.columns = chunk.columns.str.strip().str.upper()
            chunk = chunk.replace({np.nan: None})
            
            added_count = logic_func(chunk)
            if added_count:
                total += added_count
                
            db.session.commit()
            db.session.expunge_all() 
            gc.collect() # Bersihkan sisa RAM Pandas
            
        return total
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

# ==========================================
# RUTE UTAMA (AUTO-DETECT SBRS / MC)
# ==========================================
@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    """Rute Utama: Menerima upload, deteksi SBRS vs MC, lempar ke fungsi yang benar."""
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')
    file_mc = request.files.get('file_mc') or request.files.get('file')

    try:
        if file_cust and file_spot:
            # 1. JIKA UPLOAD SBRS (Customer + Spotbill) -> Ke tabel DataSBRS
            return handle_sbrs_upload(file_cust, file_spot)
            
        elif file_mc:
            # 2. JIKA UPLOAD MC / BILLING (1 File) -> Ke tabel TransaksiTagihan (TOP 500)
            return handle_mc_upload(file_mc)
            
        else:
            return jsonify({"status": "error", "message": "File tidak lengkap! Masukkan 2 file untuk SBRS atau 1 file untuk MC."}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Terjadi Kesalahan Sistem: {str(e)}"}), 500


# ==========================================
# 1. LOGIKA KHUSUS SBRS (2 FILE)
# ==========================================
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
            except: 
                curr, prev, rata = 0, 0, 15.0

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
            if trbl_code in ['2D', '2E', '2F', '4E']: indikasi = "FRAUD: METER DICOLOK / BYPASS / SEGEL PUTUS"
            elif metode in ['30/PE', '40/PE', '35/PS']: indikasi = "WARNING: TEMBAK ANGKA (ESTIMASI)"
            elif skip_code in ['5G']: indikasi = "TOLAK BACA: PELANGGAN TIDAK IZINKAN"
            elif kat == "MINUS":
                if m3 < -50: indikasi = "TEKNIS: GANTI METER BELUM MUTASI"
                else: indikasi = "HUMAN ERROR: SALAH CATAT MUNDUR"
            elif kat == "ZERO":
                if skip_code == '3A': indikasi = "WAJAR: RUMAH KOSONG"
                elif trbl_code == '1B': indikasi = "TEKNIS: METER MATI"
                else: indikasi = "MENCURIGAKAN: ZERO TANPA KETERANGAN"
            elif kat == "EKSTREM":
                if m3 > (rata * 5) and m3 > 500: indikasi = "HUMAN ERROR: FATAL SALAH KETIK"
                else: indikasi = "INDIKASI BOCOR DALAM / USAHA BARU"
            elif kat == "TURUN":
                indikasi = "INDIKASI METER MELAMBAT / RUSAK"

            merged_row['INDIKASI_SINERGI'] = indikasi

            sbrs_entries.append({
                "nomen": nomen, "periode": extract_periode(merged_row.get('BILL_PERIOD') or '202605'),
                "nama": nama_pel, "ab": ab_pel, "kelurahan": merged_row.get('KEL') or merged_row.get('KELURAHAN', ''),
                "pcez": pc_ez, "bulan_ini": m3, "rata_rata": rata, "stand_meter": curr,
                "kategori_anomali": kat, "raw_data": merged_row, "status_audit": 0
            })

        if master_provision:
            unique_master = {m['nomen']: m for m in master_provision}.values()
            stmt_master = insert(MasterPelanggan).values(list(unique_master))
            db.session.execute(stmt_master.on_conflict_do_nothing(index_elements=['nomen']))
            db.session.flush() 

        if sbrs_entries:
            stmt_sbrs = insert(DataSBRS).values(sbrs_entries)
            upsert_sbrs = stmt_sbrs.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={k: getattr(stmt_sbrs.excluded, k) for k in sbrs_entries[0].keys() if k not in ['nomen', 'periode']}
            )
            db.session.execute(upsert_sbrs)
            return len(sbrs_entries)
            
        return 0

    total_anomali = process_mega_file(file_spot, sbrs_logic, chunk_size=20000)
    lookup_cust.clear()
    gc.collect()
    return jsonify({"status": "success", "message": f"Sinergi (SBRS) Sukses! {total_anomali} data masuk."})


# ==========================================
# 2. LOGIKA KHUSUS MC / BILLING (TOP 500)
# ==========================================
def handle_mc_upload(file_mc):
    def mc_logic(df_chunk):
        master_provision = []
        mc_entries = []
        
        for _, row in df_chunk.iterrows():
            nomen = clean_nomen(row.get('NOMEN'))
            if not nomen: continue
            
            # PENGAMBILAN DATA MC UNTUK MASTER
            nama_pel = str(row.get('NAMA_PEL', 'Pelanggan')).strip()
            ab_pel = str(row.get('AB', 'AB Sunter')).strip()
            pc_ez = str(row.get('PCEZ', '')).strip()
            kelurahan = str(row.get('KELURAHAN', '')).strip()
            alamat = str(row.get('ALM1_PEL', '')).strip()
            rayon = str(row.get('RAYON', '')).strip()
            
            # Penggabungan TAHUN dan MASA jadi YYYYMM (ex: 2026 + 03 -> 202603)
            tahun = str(row.get('TAHUN1', ''))
            masa = str(row.get('MASA', '')).zfill(2)
            periode = f"{tahun}{masa}" if len(tahun)==4 and len(masa)==2 else "202604"
            
            # AMBIL NOMINAL UNTUK TOP 500
            nominal = parse_float(row.get('NOMINAL') or row.get('REK_AIR') or 0)
            
            master_provision.append({
                "nomen": nomen, "nama": nama_pel, "ab": ab_pel, "pcez": pc_ez,
                "kelurahan": kelurahan, "alamat": alamat, "rayon": rayon
            })
            
            # SIMPAN KE RUMAH YANG BENAR: TransaksiTagihan
            mc_entries.append({
                "nomen": nomen,
                "periode": periode,
                "nominal": nominal,
                "status_lunas": 0
            })
            
        # SINKRONISASI DATABASE
        if master_provision:
            unique_master = {m['nomen']: m for m in master_provision}.values()
            stmt_master = insert(MasterPelanggan).values(list(unique_master))
            db.session.execute(stmt_master.on_conflict_do_nothing(index_elements=['nomen']))
            db.session.flush()

        if mc_entries:
            stmt_mc = insert(TransaksiTagihan).values(mc_entries)
            # Update data jika pelanggan & periode sudah ada
            upsert_mc = stmt_mc.on_conflict_do_update(
                index_elements=['nomen', 'periode'],
                set_={"nominal": stmt_mc.excluded.nominal, "status_lunas": 0}
            )
            db.session.execute(upsert_mc)
            return len(mc_entries)
            
        return 0

    total_mc = process_mega_file(file_mc, mc_logic, chunk_size=20000)
    return jsonify({"status": "success", "message": f"Sinergi (MC) Sukses! {total_mc} data Tagihan (Top 500) berhasil disinkronisasi."})
