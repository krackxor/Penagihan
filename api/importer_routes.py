from flask import Blueprint, request
from werkzeug.utils import secure_filename
from workers.tasks import process_upload_task
import os
import uuid

importer_bp = Blueprint('importer', __name__)

@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    # Identifikasi file mana yang dikirim (CID, MC, atau DAILY)
    f_type = ""
    f_obj = None
    
    if 'file_cid' in request.files:
        f_type, f_obj = 'CID', request.files['file_cid']
    elif 'file_mc' in request.files:
        f_type, f_obj = 'MC', request.files['file_mc']
    elif 'file_daily' in request.files:
        f_type, f_obj = 'DAILY', request.files['file_daily']

    if f_obj and f_obj.filename != '':
        filename = secure_filename(f"{f_type}_{uuid.uuid4().hex[:6]}_{f_obj.filename}")
        filepath = os.path.join('storage', 'tmp', filename)
        f_obj.save(filepath)
        
        # Kirim ke Celery Worker
        process_upload_task.delay(filepath, f_type)
        
        # Respon HTML untuk HTMX (PENTING: Harus string/HTML, bukan JSON)
        return f'''
        <div class="alert alert-success p-2 mb-0 mt-2 small">
            <i class="fas fa-check-circle me-1"></i> {f_type} Berhasil diunggah! Sedang diproses...
        </div>
        '''

    return '<div class="alert alert-danger p-2 mb-0 mt-2 small">Gagal: File tidak ditemukan</div>'
