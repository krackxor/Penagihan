import os
import io
import uuid
import traceback
import psycopg2
import polars as pl
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from celery import shared_task

# --- Models & Database ---
from models import db

importer_bp = Blueprint('importer', __name__)

# ==========================================================
# 1. UTILITAS & FUNGSI BANTUAN
# ==========================================================

def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL tidak ditemukan.")
    return psycopg2.connect(db_url)

def detect_separator(filepath, default=';'):
    """Mendeteksi pemisah CSV/TXT secara otomatis"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            counts = { ';': first_line.count(';'), '|': first_line.count('|'), ',': first_line.count(',') }
            best_sep = max(counts, key=counts.get)
            return best_sep if counts[best_sep] > 0 else default
    except: return default

def clean_file_stream(filepath):
    """Menghapus karakter null (NUL bytes) yang sering bikin error pembacaan file"""
    clean_path = filepath + ".clean"
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f_in, \
         open(clean_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            f_out.write(line.replace('\x00', '').replace('\0', ''))
    return clean_path

def find_column(df_columns, possible_names):
    """Mencari nama kolom yang cocok terlepas dari huruf besar/kecil atau spasi"""
    col_map = {c.upper().strip(): c for c in df_columns}
    for name in possible_names:
        if name.upper() in col_map: return col_map[name.upper()]
    return df_columns[0] # Fallback ke kolom pertama jika tidak ketemu

def safe_parse_periode(val):
    """Konversi format tanggal kotor '1/3/2026 00:00:00' menjadi format database '202603'"""
    if not val: return "000000"
    try:
        # Ambil bagian tanggalnya saja dan ganti strip jadi miring
        date_part = str(val).split(" ")[0].replace("-", "/")
        parts = date_part.split("/")
        if len(parts) >= 3:
            y = parts[2]
            if len(y) == 2: y = "20" + y
            return f"{y}{parts[1].zfill(2)}"
        
        # Jika formatnya MMYYYY (misal: 122026 dari MB)
        v = str(val).strip()
        if len(v) == 6 and v[2:].startswith('20'):
            return v[2:] + v[:2]
    except: pass
    return "000000"

# ==========================================================
# 2. CORE ENGINE: FAST UPSERT (POSTGRESQL COPY)
# ==========================================================

def fast_upsert(df_pandas, table_name, conflict_cols, update_cols):
    """Fungsi ajaib untuk memasukkan 60.000 data dalam hitungan detik"""
    if df_pandas.empty: return 0
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        temp_table = f"temp_{table_name}_{uuid.uuid4().hex[:8]}"
        cur.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {table_name} INCLUDING DEFAULTS) ON COMMIT DROP")
        
        # Stream data ke buffer (TSV)
        f = io.StringIO()
        df_pandas.to_csv(f, sep='\t', header=False, index=False, na_rep='\\N')
        f.seek(0)
        
        # Injeksi Super Cepat dengan COPY
        cur.copy_from(f, temp_table, sep='\t', null='\\N', columns=list(df_pandas.columns))
        
        # Logika Update (ON CONFLICT DO UPDATE)
        set_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
        cols_str = ", ".join(df_pandas.columns)
        
        cur.execute(f"""
            INSERT INTO {table_name} ({cols_str})
            SELECT {cols_str} FROM {temp_table}
            ON CONFLICT ({", ".join(conflict_cols)}) 
            DO UPDATE SET {set_clause}
        """)
        conn.commit()
        return len(df_pandas)
    finally:
        cur.close()
        conn.close()

# ==========================================================
# 3. CELERY TASKS: PROSES DATA LATAR BELAKANG
# ==========================================================

@shared_task(bind=True)
def process_cid_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        df = pl.read_csv(clean_path, separator=detect_separator(clean_path), ignore_errors=True, infer_schema_length=0)
        cols = df.columns
        
        n_col = find_column(cols, ['NOMEN', 'ACCT_ID', 'ID_PELANGGAN'])
        cc_col = find_column(cols, ['CC', 'UNIT'])
        
        # SMART NOMEN
        df = df.with_columns([
            pl.col(n_col).cast(pl.Utf8).str.replace_all(r'[^0-9]', '').str.strip_chars_start("0").alias("nomen_clean"),
            pl.col(cc_col).cast(pl.Utf8).alias("cc_clean"),
            pl.lit('{}').alias("raw_data")
        ]).filter(pl.col("nomen_clean").is_not_null() & (pl.col("nomen_clean") != ""))
        
        df = df.unique(subset=["nomen_clean"], keep="last")
        pdf = df.to_pandas()[['nomen_clean', 'cc_clean', 'raw_data']]
        pdf.columns = ['nomen', 'cc', 'raw_data']
        
        inserted = fast_upsert(pdf, 'master_pelanggan', ['nomen'], ['cc', 'raw_data'])
        os.remove(filepath); os.remove(clean_path)
        return f"CID Sukses: {inserted} Pelanggan diperbarui."
    except Exception as e: return f"Gagal CID: {str(e)}"

@shared_task(bind=True)
def process_mc_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        df = pl.read_csv(clean_path, separator=detect_separator(clean_path), ignore_errors=True, infer_schema_length=0)
        cols = df.columns
        
        n_col = find_column(cols, ['NOMEN', 'ACCT_ID'])
        t_col = find_column(cols, ['TAHUN2'])
        b_col = find_column(cols, ['NAMA_BLN2'])
        tagihan_col = find_column(cols, ['NOMINAL', 'REK_AIR', 'TOTAL_TAGIHAN'])
        
        df = df.with_columns([
            pl.col(n_col).cast(pl.Utf8).str.replace_all(r'[^0-9]', '').str.strip_chars_start("0").alias("nomen_clean"),
            (pl.col(t_col).cast(pl.Utf8) + pl.col(b_col).cast(pl.Utf8).str.zfill(2)).alias("periode_clean"),
            pl.col(tagihan_col).cast(pl.Utf8).str.replace(',', '.').cast(pl.Float64, strict=False).fill_null(0).alias("total_tagihan_clean"),
            pl.lit(0).alias("status_lunas"),
            pl.lit('{}').alias("raw_data")
        ]).filter(pl.col("nomen_clean").is_not_null() & (pl.col("nomen_clean") != ""))
        
        pdf = df.to_pandas()[['nomen_clean', 'periode_clean', 'total_tagihan_clean', 'status_lunas', 'raw_data']]
        pdf.columns = ['nomen', 'periode', 'total_tagihan', 'status_lunas', 'raw_data']
        
        inserted = fast_upsert(pdf, 'transaksi_tagihan', ['nomen', 'periode'], ['total_tagihan', 'raw_data'])
        os.remove(filepath); os.remove(clean_path)
        return f"MC Sukses: {inserted} Target Tagihan dicatat."
    except Exception as e: return f"Gagal MC: {str(e)}"

@shared_task(bind=True)
def process_mb_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        df = pl.read_csv(clean_path, separator=detect_separator(clean_path), ignore_errors=True, infer_schema_length=0)
        cols = df.columns
        
        n_col = find_column(cols, ['NOMEN', 'CMR_ACCOUNT'])
        per_col = find_column(cols, ['BULAN_REK', 'BulanRek'])
        nom_col = find_column(cols, ['NOMINAL', 'PAY_AMT', 'TOTAL_BAYAR'])
        
        # Smart Nomen & Smart Periode
        df = df.with_columns([
            pl.col(n_col).cast(pl.Utf8).str.replace_all(r'[^0-9]', '').str.strip_chars_start("0").alias("nomen_clean"),
            pl.col(per_col).map_elements(safe_parse_periode, return_dtype=pl.Utf8).alias("periode_clean"),
            pl.col(per_col).cast(pl.Utf8).alias("bulan_rek_clean"),
            pl.col(nom_col).cast(pl.Utf8).str.replace(',', '.').cast(pl.Float64, strict=False).fill_null(0).alias("nominal_clean"),
            pl.lit('{}').alias("raw_data")
        ]).filter(pl.col("nomen_clean").is_not_null() & (pl.col("nomen_clean") != ""))
        
        pdf = df.to_pandas()[['nomen_clean', 'periode_clean', 'bulan_rek_clean', 'nominal_clean', 'raw_data']]
        pdf.columns = ['nomen', 'periode', 'bulan_rek', 'nominal', 'raw_data']
        
        inserted = fast_upsert(pdf, 'data_mb', ['nomen', 'periode'], ['bulan_rek', 'nominal', 'raw_data'])
        
        # AUTO LUNAS
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE transaksi_tagihan t SET status_lunas = 1 FROM data_mb m WHERE t.nomen = m.nomen AND t.periode = m.periode")
        conn.commit()
        cur.close(); conn.close()

        os.remove(filepath); os.remove(clean_path)
        return f"MB Sukses: {inserted} Pelunasan Undue diproses."
    except Exception as e: return f"Gagal MB: {str(e)}"

@shared_task(bind=True)
def process_daily_task(self, filepath):
    try:
        clean_path = clean_file_stream(filepath)
        df = pl.read_csv(clean_path, separator=detect_separator(clean_path), ignore_errors=True, infer_schema_length=0)
        cols = df.columns
        
        n_col = find_column(cols, ['NOMEN', 'ACCT_ID'])
        b_per_col = find_column(cols, ['BILL_PERIOD', 'PERIODE_DTTM'])
        p_amt_col = find_column(cols, ['PAY_AMT', 'NOMINAL'])
        p_dt_col = find_column(cols, ['PAY_DT', 'TGL_BAYAR'])
        b_id_col = find_column(cols, ['BILL_ID', 'NOTAGIHAN'])
        
        # Smart Nomen & Smart Periode
        df = df.with_columns([
            pl.col(n_col).cast(pl.Utf8).str.replace_all(r'[^0-9]', '').str.strip_chars_start("0").alias("nomen_clean"),
            pl.col(b_per_col).map_elements(safe_parse_periode, return_dtype=pl.Utf8).alias("periode_clean"),
            pl.col(p_amt_col).cast(pl.Utf8).str.replace(',', '.').cast(pl.Float64, strict=False).fill_null(0).alias("nominal_clean"),
            pl.col(p_dt_col).cast(pl.Utf8).alias("pay_dt_clean"),
            pl.col(b_id_col).cast(pl.Utf8).alias("bill_id_clean"),
            pl.lit('{}').alias('raw_data')
        ]).filter(pl.col("nomen_clean").is_not_null() & (pl.col("nomen_clean") != ""))

        pdf = df.to_pandas()[['nomen_clean', 'periode_clean', 'pay_dt_clean', 'nominal_clean', 'bill_id_clean', 'raw_data']]
        pdf.columns = ['nomen', 'periode', 'pay_dt', 'pay_amt', 'bill_id', 'raw_data']
        
        inserted = fast_upsert(pdf, 'data_daily', ['nomen', 'bill_id'], ['periode', 'pay_dt', 'pay_amt', 'raw_data'])

        # AUTO LUNAS
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE transaksi_tagihan t
            SET status_lunas = 1
            FROM data_daily d
            WHERE t.nomen = d.nomen 
            AND t.periode = d.periode
        """)
        conn.commit()
        cur.close(); conn.close()

        os.remove(filepath); os.remove(clean_path)
        return f"Daily Sukses: {inserted} Koleksi Harian (Current) diproses."
    except Exception as e: return f"Gagal Daily: {str(e)}"

# ==========================================================
# 4. RUTE UTAMA UPLOAD (INSTAN / ASINKRON FULL)
# ==========================================================

@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    upload_dir = os.path.join('instance', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    
    # Pemetaan jenis file ke fungsi Worker
    mappings = {
        'file_cid': ('CID', process_cid_task),
        'file_mc': ('MC', process_mc_task),
        'file_mb': ('MB', process_mb_task),
        'file_daily': ('DAILY', process_daily_task)
    }
    
    try:
        # Loop semua input file yang datang dari form
        for req_key, (type_label, task_func) in mappings.items():
            file_obj = request.files.get(req_key)
            if file_obj and file_obj.filename:
                # Simpan dengan penamaan unik anti-bentrok
                filename = secure_filename(f"{type_label}_{uuid.uuid4().hex[:8]}_{file_obj.filename}")
                filepath = os.path.join(upload_dir, filename)
                file_obj.save(filepath)
                
                # Picu Worker Celery secara latar belakang (.delay)
                task = task_func.delay(filepath)
                
                return jsonify({
                    "status": "success", 
                    "message": f"Data {type_label} sedang disinkronisasi di latar belakang.", 
                    "task_id": task.id
                }), 202

        # Jika tidak ada file yang cocok
        return jsonify({"status": "error", "message": "Tidak ada file yang didukung untuk diunggah!"}), 400

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": f"Fatal System Error: {str(e)}"}), 500
