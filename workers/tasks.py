from extensions import celery
from services.importer_service import ImporterService
import polars as pl
import os

@celery.task(bind=True)
def process_upload_task(self, filepath):
    try:
        # 1. DETEKSI OTOMATIS TIPE FILE
        self.update_state(state='PROGRESS', meta={'percent': 10, 'status': 'Menganalisis Kolom...'})
        
        # Baca header saja (1 baris)
        df_header = pl.read_csv(filepath, separator=';', n_rows=1, ignore_errors=True)
        cols = [c.upper() for c in df_header.columns]
        
        file_type = "UNKNOWN"
        if "TAHUN2" in cols and "TOTAL_TAGIHAN" in cols:
            file_type = "MC"
        elif "PAY_DT" in cols or "BILL_ID" in cols:
            file_type = "DAILY"
        elif "PETUGAS_RL" in cols or "NOREK" in cols:
            file_type = "CID"
        elif "BULAN_REK" in cols and "NOMINAL" in cols:
            file_type = "MB"

        if file_type == "UNKNOWN":
            raise Exception(f"Format file tidak dikenali. Kolom terdeteksi: {cols}")

        # 2. PROSES BERDASARKAN TIPE
        self.update_state(state='PROGRESS', meta={'percent': 30, 'type': file_type})
        
        # Panggil service yang sudah ada
        success, result = ImporterService.process_file_to_db(filepath, file_type)
        
        if success:
            return {'status': 'SUCCESS', 'type': file_type, 'count': result}
        else:
            raise Exception(result)

    except Exception as e:
        return {'status': 'FAILURE', 'message': str(e)}
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
