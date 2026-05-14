from extensions import celery
from services.importer_service import ImporterService
import polars as pl
import os
import traceback

@celery.task(bind=True)
def process_upload_task(self, filepath):
    """
    Tugas asinkron untuk mendeteksi jenis file secara otomatis,
    memproses data menggunakan Polars, dan menyuntikkannya ke database.
    """
    try:
        # 1. TAHAP DETEKSI: Menganalisis header kolom file
        self.update_state(state='PROGRESS', meta={'percent': 10, 'status': 'Menganalisis Kolom...'})
        
        # Membaca hanya baris pertama untuk identifikasi (Efisien untuk file besar)
        df_header = pl.read_csv(filepath, separator=';', n_rows=1, ignore_errors=True)
        cols = [c.upper() for c in df_header.columns]
        
        file_type = "UNKNOWN"
        
        # Logika Identifikasi berdasarkan nama kolom spesifik
        if "TAHUN2" in cols and "TOTAL_TAGIHAN" in cols:
            file_type = "MC"
        elif "PAY_DT" in cols or "BILL_ID" in cols:
            file_type = "DAILY"
        elif "PETUGAS_RL" in cols or "NOREK" in cols:
            file_type = "CID"
        elif "BULAN_REK" in cols and "NOMINAL" in cols:
            file_type = "MB"

        if file_type == "UNKNOWN":
            raise Exception(f"Format file tidak dikenali. Kolom terdeteksi: {cols[:5]}")

        # 2. TAHAP PROSES: Eksekusi Logika Bisnis di Service Layer
        self.update_state(state='PROGRESS', meta={
            'percent': 30, 
            'type': file_type, 
            'status': f'Memproses {file_type}...'
        })
        
        # Memanggil ImporterService yang menggunakan Polars & PostgreSQL COPY
        success, result = ImporterService.process_file_to_db(filepath, file_type)
        
        if success:
            # Mengembalikan status sukses beserta jumlah baris yang berhasil di-ingest
            return {
                'status': 'SUCCESS', 
                'type': file_type, 
                'count': result
            }
        else:
            # Jika ada kegagalan logika di tingkat service
            raise Exception(result)

    except Exception as e:
        # Menangkap error dan mengirimkan pesan ke frontend
        return {
            'status': 'FAILURE', 
            'message': str(e),
            'trace': traceback.format_exc()
        }
    finally:
        # 3. TAHAP PEMBERSIHAN: Menghapus file sementara agar tidak memenuhi storage
        if os.path.exists(filepath):
            os.remove(filepath)
