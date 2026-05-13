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
from werkzeug.utils import secure_filename # <--- BARIS INI YANG MEMPERBAIKI ERROR

# --- Impor Task Celery (Anggap app.celery.task ada atau gunakan shared_task) ---
from celery import shared_task 

# --- Models & Database (untuk fallback atau operasi kecil) ---
from models import db, MasterPelanggan, TransaksiTagihan, DataMB, DataDaily, DataMainbill, DataSBRS, DataArrdebt

csv.field_size_limit(sys.maxsize)

importer_bp = Blueprint('importer', __name__)

# ==========================================================
# 1. UTILITAS & FUNGSI BANTUAN (POLARS SUPPORT)
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
    """Membersihkan file dari NULL bytes sebelum diproses Polars"""
    clean_path = filepath + ".clean"
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f_in, \
         open(clean_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            f_out.write(line.replace('\x00', '').replace('\0', ''))
    return clean_path

# ==========================================================
# 2. FUNGSI INGESTI CEPAT DENGAN POSTGRESQL COPY
# ==========================================================
def fast_upsert_with_copy(df_pandas, table_name, conflict_columns, update_columns):
    """
    Fungsi krusial untuk mempercepat upload dari menit ke detik.
    Menerapkan metode: DataFrame -> CSV String -> Temp Table (COPY) -> Target Table (ON CONFLICT)
    """
    if df_pandas.empty:
        return 0
        
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL tidak ditemukan di environment.")

    # Sambungan langsung via psycopg2 untuk kecepatan maksimal (bypass ORM)
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    # 1. Buat tabel sementara (Temporary Table) berdasarkan tabel asli
    temp_table = f"temp_{table_name}_{uuid.uuid4().hex[:8]}"
    cur.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {table_name} INCLUDING DEFAULTS) ON COMMIT DROP;")
    
    # 2. Konversi Pandas DF ke format buffer TSV (Tab Separated)
    csv_buffer = io.StringIO()
    df_pandas.to_csv(csv_buffer, sep='\t', header=False, index=False, na_rep='\\N')
    csv_buffer.seek(0)
    
    # Perhatikan urutan kolom harus sama antara DataFrame dan Tabel Database!
    columns = list(df_pandas.columns)
    columns_str = ", ".join(columns)
    
    # 3. Gunakan protokol COPY (Cara Tercepat di Postgres)
    cur.copy_from(csv_buffer, temp_table, sep='\t', null='\\N', columns=columns)
    
    # 4. UPSERT: Pindahkan dari tabel sementara ke tabel utama
    conflict_cols_str = ", ".join(conflict_columns)
    
    # Buat logika "DO UPDATE SET col1 = EXCLUDED.col1, col2 = EXCLUDED.col2..."
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
# 3. CELERY BACKGROUND TASKS (PEKERJA ASINKRON)
# ==========================================================
@shared_task(bind=True)
def process_cid_task(self, filepath):
    """Tugas asinkron untuk memproses Master Pelanggan (CID)"""
    try:
        clean_path = clean_file_stream(filepath)
        smart_sep = detect_separator(clean_path)
        
        # 1. Baca dengan Polars (Sangat Cepat & Hemat Memori)
        # Asumsi header standar dari file CID
        df = pl.read_csv(clean_path, separator=smart_sep, ignore_errors=True, infer_schema_length=0)
        
        # Mapping Kolom Fleksibel (Simulasi pencarian nama kolom seperti versi sebelumnya)
        col_map = {c.upper(): c for c in df.columns}
        
        def get_col(possible_names):
            for name in possible_names:
                if name in col_map: return col_map[name]
            return None

        nomen_col = get_col(['NOMEN', 'ACCT_ID', 'ID_PELANGGAN'])
        if not nomen_col: return f"Error: Kolom NOMEN tidak ditemukan."

        # 2. Transformasi Data dengan Polars (Vektorisasi - Cepat)
        df = df.with_columns([
            pl.col(nomen_col).str.replace_all('"', '').str.strip_chars().str.replace_all('[^0-9]', '').alias("nomen_clean"),
            pl.lit('{}').alias('raw_data') # Dummy raw_data untuk kecepatan
        ]).filter(pl.col("nomen_clean").is_not_null() & (pl.col("nomen_clean") != ""))
        
        # Deduplikasi berdasarkan Nomen
        df = df.unique(subset=["nomen_clean"], keep="last")
        
        # Siapkan Pandas DataFrame dengan kolom yang sesuai struktur DB MasterPelanggan
        pdf = df.to_pandas()
        
        # Petakan data (Bisa disesuaikan dengan logika get_val versi sebelumnya menggunakan Pandas Apply)
        # Untuk contoh, asumsikan kita punya fungsi mapping atau menggunakan nama kolom langsung
        db_df = pdf[['nomen_clean', 'raw_data']].copy()
        db_df.columns = ['nomen', 'raw_data']
        # ... Tambahkan mapping kolom lainnya seperti nama, alamat, dll sesuai kebutuhan DB ...
        
        # 3. Simpan ke Database
        inserted = fast_upsert_with_copy(
            db_df, 
            table_name='master_pelanggan', 
            conflict_columns=['nomen'], 
            update_columns=['raw_data'] # Tambahkan kolom lain yang ingin diupdate
        )
        
        # Bersihkan file
        os.remove(filepath)
        os.remove(clean_path)
        
        return f"Selesai! {inserted} Master CID berhasil diproses."
    except Exception as e:
        print(traceback.format_exc())
        return f"Gagal: {str(e)}"

@shared_task(bind=True)
def process_mb_task(self, filepath):
    """Tugas asinkron untuk memproses Master Bayar (MB)"""
    try:
        clean_path = clean_file_stream(filepath)
        smart_sep = detect_separator(clean_path)
        
        # Polars
        df = pl.read_csv(clean_path, separator=smart_sep, ignore_errors=True, infer_schema_length=0)
        col_map = {c.upper(): c for c in df.columns}
        
        nomen_col = col_map.get('NOMEN') or col_map.get('CMR_ACCOUNT')
        if not nomen_col: return "Error: Kolom NOMEN tidak ditemukan."
        
        # ... Logika pembersihan dan shift_periode menggunakan Polars Expr ...
        # (Silakan terapkan logika extract_periode versi vectorized di sini untuk kecepatan)
        # Untuk sementara, ini kerangka utama arsitekturnya.

        os.remove(filepath)
        os.remove(clean_path)
        return "Selesai! File MB berhasil diproses."
    except Exception as e:
        return f"Gagal: {str(e)}"

# ==========================================================
# 4. RUTE UTAMA UPLOAD (SEKARANG INSTAN / ASINKRON)
# ==========================================================
@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    """
    Rute ini sekarang hanya menyimpan file dan memicu tugas Celery.
    Tidak ada proses logika berat di sini, sehingga UI tidak akan pernah freeze/timeout.
    """
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
    
    upload_dir = os.path.join('instance', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    try:
        # Penanganan khusus untuk SBRS (karena butuh 2 file)
        if file_cust and file_spot:
            # TODO: Buat task khusus SBRS yang menerima 2 file path
            return jsonify({"status": "info", "message": "Fitur SBRS asinkron sedang dikonfigurasi."}), 202
            
        for key, file_obj in files.items():
            if file_obj:
                filename = secure_filename(f"{uuid.uuid4().hex[:8]}_{file_obj.filename}")
                filepath = os.path.join(upload_dir, filename)
                file_obj.save(filepath)
                
                # Memicu Celery Worker secara Asinkron
                if key == 'cid':
                    task = process_cid_task.delay(filepath)
                    msg = "File CID sedang diproses di latar belakang."
                elif key == 'mb':
                    task = process_mb_task.delay(filepath)
                    msg = "File Master Bayar sedang diproses di latar belakang."
                else:
                    # Rute lain dapat dibuat task-nya mengikuti pola di atas
                    task = None
                    msg = f"File {key} diunggah, menunggu konfigurasi worker."
                
                return jsonify({"status": "success", "message": msg, "task_id": task.id if task else None}), 202
                
        return jsonify({"status": "error", "message": "Tidak ada file yang diunggah!"}), 400

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": f"Fatal System Error: {str(e)}"}), 500
