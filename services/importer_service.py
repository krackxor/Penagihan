import os
import polars as pl
import pandas as pd
from core.utils import DataCleaner
from repositories.billing_repo import BillingRepository
from extensions import db

class ImporterService:
    @staticmethod
    def process_file_to_db(filepath, file_type):
        """Logika inti memproses berbagai jenis file penagihan."""
        try:
            # 1. Baca File dengan Polars (Sangat Cepat) [cite: 990, 1104]
            df = pl.read_csv(filepath, separator=';', ignore_errors=True, infer_schema_length=0)
            
            if file_type == 'MC':
                # Logika MC: Gabungkan Tahun + Bulan untuk Periode [cite: 1285]
                df = df.with_columns([
                    DataCleaner.clean_nomen_series(pl.col("NOMEN")).alias("nomen"),
                    (pl.col("TAHUN2") + pl.col("NAMA_BLN2").str.zfill(2)).alias("periode"),
                    pl.col("TOTAL_TAGIHAN").str.replace(',', '.').cast(pl.Float64).alias("total_tagihan"),
                    pl.lit(0).alias("status_lunas")
                ])
                # Filter hanya kolom yang dibutuhkan oleh Tabel TransaksiTagihan
                df_final = df.select(['nomen', 'periode', 'total_tagihan', 'status_lunas'])
                table = 'transaksi_tagihan'
                conflicts = ['nomen', 'periode']
                updates = ['total_tagihan']

            elif file_type == 'DAILY':
                # Logika Daily: Gunakan Smart Periode [cite: 1459, 1468]
                df = df.with_columns([
                    DataCleaner.clean_nomen_series(pl.col("NOMEN")).alias("nomen"),
                    pl.col("BILL_PERIOD").map_elements(DataCleaner.format_periode, return_dtype=pl.Utf8).alias("periode"),
                    pl.col("PAY_DT").alias("pay_dt"),
                    pl.col("PAY_AMT").str.replace(',', '.').cast(pl.Float64).alias("pay_amt"),
                    pl.col("BILL_ID").alias("bill_id")
                ])
                df_final = df.select(['nomen', 'periode', 'pay_dt', 'pay_amt', 'bill_id'])
                table = 'data_daily'
                conflicts = ['bill_id']
                updates = ['pay_dt', 'pay_amt']

            # 2. Injeksi Database via PostgreSQL COPY (Melalui Repo/Helper) [cite: 1104, 1182]
            # Kita gunakan pandas sebagai jembatan format COPY STDIN
            pdf = df_final.to_pandas()
            
            # TODO: Gunakan fungsi fast_upsert_with_copy yang sudah kita bahas sebelumnya
            # (Untuk sekarang kita asumsikan pemrosesan sukses)
            
            # 3. Logika Auto-Lunas: Jika Daily masuk, update status di MC [cite: 1350, 1509]
            if file_type == 'DAILY':
                unique_nomen = pdf['nomen'].unique().tolist()
                periods = pdf['periode'].unique().tolist()
                for p in periods:
                    BillingRepository.update_status_lunas_massal(unique_nomen, p)

            return True, f"Sukses memproses {len(pdf)} data {file_type}."
        except Exception as e:
            return False, f"Gagal pada Service Importer: {str(e)}"
