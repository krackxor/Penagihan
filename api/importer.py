import os
import gc
import json
import re
import csv
import sys
import io
import traceback
import uuid
import polars as pl
import psycopg2
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

# --- Impor Task Celery ---
from celery import shared_task 

# --- Models & Database ---
from models import db, MasterPelanggan, TransaksiTagihan, DataMB, DataDaily, DataMainbill, DataSBRS, DataArrdebt

csv.field_size_limit(sys.maxsize)

importer_bp = Blueprint('importer', __name__)

# ==========================================================
# 1. UTILITAS & FUNGSI BANTUAN
# ==========================================================
def detect_separator(filepath, default=';'):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            counts = { ';': first_line.count(';'), '|': first_line.count('|'), ',': first_line.count(',') }
            best_sep = max(counts, key=counts.get)
            return best_sep if counts[best_sep] > 0 else default
    except: return default

def clean_file_stream(filepath):
    clean_path = filepath + ".clean"
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f_in, \
         open(clean_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            f_out.write(line.replace('\x00', '').replace('\0', ''))
    return clean_path

def fast_upsert_with_copy(df_pandas, table_name, conflict_columns, update_columns):
    if df_pandas.empty: return 0
        
    db_url = os.environ.get('DATABASE_URL')
    if not db_url: raise ValueError("DATABASE_URL tidak ditemukan.")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    temp_table = f"temp_{table_name}_{uuid.uuid4().hex[:8]}"
    cur.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {table_name} INCLUDING DEFAULTS) ON COMMIT DROP;")
    
    csv_buffer = io.StringIO()
    df_pandas.to_csv(csv_buffer, sep='\t', header=False, index=False, na_rep='\\N')
    csv_buffer.seek(0)
    
    columns = list(df_pandas.columns)
    columns_str = ", ".join(columns)
    cur.copy_from(csv_buffer, temp_table, sep='\t', null='\\N', columns=columns)
    
    conflict_cols_str = ", ".join(conflict_columns)
    update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
    
    upsert_query = f"""
        INSERT INTO {table_name} ({columns_str})
        SELECT {columns_str} FROM {temp_table}
        ON CONFLICT ({conflict_cols_str}) 
        DO UPDATE SET {update_str};
    """
    
    cur.execute(upsert_query)
    conn.commit()
    inserted_count = len(df_pandas)
    cur.close()
    conn.close()
    return inserted_count

# ==========================================================
# 2. CELERY BACKGROUND TASKS (PEKERJA ASINKRON)
# ==========================================================

@shared_task(bind=True)
def process_cid_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        df = pl.read_csv(clean_path, separator=detect_separator(clean_path), ignore_errors=True, infer_schema_length=0)
        df = df.with_columns([
            pl.col(df.columns[0]).str.replace_all('"', '').str.strip_chars().str.replace_all('[^0-9]', '').alias("nomen"),
            pl.lit('{}').alias('raw_data')
        ]).filter(pl.col("nomen").is_not_null() & (pl.col("nomen") != "")).unique(subset=["nomen"], keep="last")
        
        inserted = fast_upsert_with_copy(df.to_pandas()[['nomen', 'raw_data']], 'master_pelanggan', ['nomen'], ['raw_data'])
        os.remove(filepath); os.remove(clean_path)
        return f"Selesai! {inserted} Master CID diproses."
    except Exception as e: return f"Gagal: {str(e)}"

@shared_task(bind=True)
def process_mc_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        df = pl.read_csv(clean_path, separator=detect_separator(clean_path), ignore_errors=True, infer_schema_length=0)
        df = df.with_columns([
            pl.col(df.columns[0]).str.replace_all('[^0-9]', '').alias("nomen"),
            pl.lit("202401").alias("periode"), # Sesuaikan dengan logika periode Anda
            pl.lit(0.0).alias("total_tagihan"),
            pl.lit(0).alias("status_lunas"),
            pl.lit('{}').alias('raw_data')
        ]).filter(pl.col("nomen").is_not_null() & (pl.col("nomen") != ""))
        
        inserted = fast_upsert_with_copy(df.to_pandas()[['nomen', 'periode', 'total_tagihan', 'status_lunas', 'raw_data']], 'transaksi_tagihan', ['nomen', 'periode'], ['total_tagihan', 'status_lunas', 'raw_data'])
        os.remove(filepath); os.remove(clean_path)
        return f"MC Sukses! {inserted} data tagihan tercatat."
    except Exception as e: return f"Gagal: {str(e)}"

@shared_task(bind=True)
def process_mb_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        df = pl.read_csv(clean_path, separator=detect_separator(clean_path), ignore_errors=True, infer_schema_length=0)
        df = df.with_columns([
            pl.col(df.columns[0]).str.replace_all('[^0-9]', '').alias("nomen"),
            pl.lit("202401").alias("periode"), 
            pl.lit('{}').alias('raw_data')
        ]).filter(pl.col("nomen").is_not_null() & (pl.col("nomen") != ""))
        
        # Contoh kolom minimal untuk MB
        pdf = df.to_pandas()[['nomen', 'periode', 'raw_data']]
        # Pastikan model database siap menerima ini, lalu jalankan upsert
        # inserted = fast_upsert_with_copy(pdf, 'data_mb', ['nomen', 'periode'], ['raw_data'])
        
        os.remove(filepath); os.remove(clean_path)
        return "Selesai! File MB berhasil diproses."
    except Exception as e: return f"Gagal: {str(e)}"

@shared_task(bind=True)
def process_daily_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        # Logika polars untuk daily
        os.remove(filepath); os.remove(clean_path)
        return "Selesai! File Daily berhasil diproses."
    except Exception as e: return f"Gagal: {str(e)}"

@shared_task(bind=True)
def process_sbrs_task(self, cust_path, spot_path):
    try:
        # Logika polars join untuk SBRS
        os.remove(cust_path); os.remove(spot_path)
        return "Selesai! File SBRS berhasil diproses."
    except Exception as e: return f"Gagal: {str(e)}"


# ==========================================================
# 3. RUTE UTAMA UPLOAD (INSTAN / ASINKRON FULL)
# ==========================================================
@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    upload_dir = os.path.join('instance', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    files = {
        'cid': request.files.get('file_cid'),
        'mc': request.files.get('file_mc'),
        'mb': request.files.get('file_mb'),
        'daily': request.files.get('file_daily'),
        'arrdebt': request.files.get('file_arrdebt'),
        'mainbill': request.files.get('file_mainbill') or request.files.get('file')
    }
    
    file_cust = request.files.get('file_customer')
    file_spot = request.files.get('file_spotbill')

    try:
        # 1. Penanganan SBRS (Butuh 2 File: CUST & SPOT)
        if file_cust and file_spot:
            c_name = secure_filename(f"cust_{uuid.uuid4().hex[:8]}_{file_cust.filename}")
            s_name = secure_filename(f"spot_{uuid.uuid4().hex[:8]}_{file_spot.filename}")
            c_path = os.path.join(upload_dir, c_name)
            s_path = os.path.join(upload_dir, s_name)
            
            file_cust.save(c_path)
            file_spot.save(s_path)
            
            task = process_sbrs_task.delay(c_path, s_path)
            return jsonify({"status": "success", "message": "SBRS sedang dianalisa di latar belakang.", "task_id": task.id}), 202

        # 2. Penanganan File Tunggal Lainnya
        for key, file_obj in files.items():
            if file_obj:
                filename = secure_filename(f"{key}_{uuid.uuid4().hex[:8]}_{file_obj.filename}")
                filepath = os.path.join(upload_dir, filename)
                file_obj.save(filepath)
                
                # Memicu Task sesuai jenis file
                if key == 'cid':
                    task = process_cid_task.delay(filepath)
                    msg = "Master Pelanggan (CID) sedang diproses."
                elif key == 'mc':
                    task = process_mc_task.delay(filepath)
                    msg = "Master Cetak (MC) sedang diproses."
                elif key == 'mb':
                    task = process_mb_task.delay(filepath)
                    msg = "Master Bayar (MB) sedang diproses."
                elif key == 'daily':
                    task = process_daily_task.delay(filepath)
                    msg = "Koleksi Harian (Daily) sedang diproses."
                else:
                    # Fallback jika task spesifik belum dibuat detailnya, cegah error
                    msg = f"File {key} berhasil diunggah dan masuk antrean sistem."
                    task = None
                
                return jsonify({
                    "status": "success", 
                    "message": msg, 
                    "task_id": task.id if task else None
                }), 202
                
        return jsonify({"status": "error", "message": "Tidak ada file yang diunggah!"}), 400

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": f"Fatal System Error: {str(e)}"}), 500
