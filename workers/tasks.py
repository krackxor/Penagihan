from extensions import celery
from services.importer_service import ImporterService
import os

@celery.task(bind=True)
def process_upload_task(self, filepath, file_type):
    """
    Task Celery untuk memproses file di latar belakang.
    Ini memanggil ImporterService agar logika bisnis tetap terpusat.
    """
    try:
        self.update_state(state='PROGRESS', meta={'status': f'Memproses {file_type}...'})
        
        # Panggil Service untuk mengolah data
        success, message = ImporterService.process_file_to_db(filepath, file_type)
        
        if success:
            return {'status': 'SUCCESS', 'message': message}
        else:
            raise Exception(message)
            
    except Exception as e:
        self.update_state(state='FAILURE', meta={'status': str(e)})
        return {'status': 'FAILURE', 'message': str(e)}
