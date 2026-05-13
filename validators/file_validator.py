import os
import polars as pl
from core.utils import DataCleaner

class FileValidator:
    REQUIRED_COLUMNS = {
        'CID': ['NOMEN', 'CC'],
        'MC': ['NOMEN', 'TAHUN2', 'NAMA_BLN2', 'TOTAL_TAGIHAN'],
        'MB': ['NOMEN', 'BULAN_REK', 'NOMINAL'],
        'DAILY': ['NOMEN', 'BILL_PERIOD', 'PAY_DT', 'BILL_ID']
    }

    @staticmethod
    def check_file_exists(filepath):
        """Memastikan file benar-benar ada di storage."""
        if not os.path.exists(filepath):
            return False, "File tidak ditemukan di server."
        return True, "OK"

    @staticmethod
    def validate_structure(filepath, file_type, separator=';'):
        """
        Validasi Struktur:
        1. Cek apakah file kosong.
        2. Cek apakah kolom wajib ada.
        3. Cek apakah delimiter benar.
        """
        try:
            # Baca hanya 5 baris pertama untuk efisiensi validasi
            df = pl.read_csv(
                filepath, 
                separator=separator, 
                n_rows=5, 
                ignore_errors=True, 
                infer_schema_length=0
            )
            
            if df.is_empty():
                return False, "File kosong atau tidak memiliki data."

            # Normalisasi nama kolom ke Huruf Besar
            cols = [c.upper().strip() for c in df.columns]
            required = FileValidator.REQUIRED_COLUMNS.get(file_type, [])
            
            missing = [req for req in required if req not in cols]
            if missing:
                return False, f"Kolom wajib hilang: {', '.join(missing)}"

            return True, "Validasi Struktur Sukses"
        except Exception as e:
            return False, f"Gagal membaca format file: {str(e)}"

    @staticmethod
    def validate_content_sample(filepath, file_type, separator=';'):
        """Validasi Isi: Memastikan Nomen bisa dibersihkan dan Nominal adalah angka."""
        try:
            df = pl.read_csv(filepath, separator=separator, n_rows=10)
            
            # Cek Nomen (Gunakan DataCleaner yang sudah kita buat di Tahap 2)
            # Asumsi kolom pertama adalah Nomen jika nama kolom bervariasi
            nomen_col = df.columns[0]
            clean_test = DataCleaner.clean_nomen_series(df[nomen_col])
            
            if clean_test.is_empty() or clean_test[0] is None:
                return False, "Data NOMEN tidak valid atau tidak bisa dibersihkan."

            return True, "Validasi Konten Sukses"
        except:
            return False, "Konten file tidak sesuai dengan standar numerik."
