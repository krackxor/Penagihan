from flask import Blueprint, request
from werkzeug.utils import secure_filename
from workers.tasks import process_upload_task
import os, uuid

importer_bp = Blueprint('importer', __name__)

@importer_bp.route('/smart-upload', methods=['POST'])
def smart_upload():
    f_obj = request.files.get('file_main')
    if not f_obj or f_obj.filename == '':
        return '<div class="alert alert-danger p-2 small">Pilih file terlebih dahulu!</div>'

    # Simpan file sementara
    ext = os.path.splitext(f_obj.filename)[1]
    filename = secure_filename(f"UPLOAD_{uuid.uuid4().hex[:6]}{ext}")
    filepath = os.path.join('storage', 'tmp', filename)
    f_obj.save(filepath)

    # Jalankan Celery Task
    task = process_upload_task.delay(filepath)

    # Balikan Progress Bar HTMX
    return f'''
    <div hx-get="/api/import/status/{task.id}" hx-trigger="every 1s" hx-target="this" hx-swap="outerHTML">
        <div class="progress mt-3" style="height: 25px;">
            <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
                 style="width: 15%">Menganalisis File...</div>
        </div>
    </div>
    '''

@importer_bp.route('/status/<task_id>')
def task_status(task_id):
    from extensions import celery
    task = celery.AsyncResult(task_id)
    
    if task.state == 'PROGRESS':
        info = task.info
        return f'''
        <div hx-get="/api/import/status/{task_id}" hx-trigger="every 1s" hx-target="this" hx-swap="outerHTML">
            <div class="d-flex justify-content-between small mb-1">
                <span>Memproses {info.get('type', 'Data')}...</span>
                <span>{info.get('percent', 0)}%</span>
            </div>
            <div class="progress" style="height: 25px;">
                <div class="progress-bar bg-info" style="width: {info.get('percent', 0)}%"></div>
            </div>
        </div>
        '''
    elif task.state == 'SUCCESS':
        res = task.result
        return f'''
        <div class="alert alert-success mt-3 shadow-sm border-start border-4 border-success bounce-in">
            <div class="d-flex align-items-center">
                <i class="fas fa-check-circle fa-2x me-3"></i>
                <div>
                    <h6 class="mb-0 fw-bold">Selesai! Tipe Terdeteksi: {res['type']}</h6>
                    <small>{res['count']:,} baris data berhasil disinkronisasi ke database.</small>
                </div>
            </div>
        </div>
        '''
    elif task.state == 'FAILURE':
        return f'<div class="alert alert-danger mt-3 small text-center"><b>Gagal:</b> {str(task.info)}</div>'
    
    return '<div class="progress mt-3"><div class="progress-bar" style="width: 5%">...</div></div>'
