from flask import Blueprint, request
from werkzeug.utils import secure_filename
from workers.tasks import process_upload_task
from extensions import celery
import os
import uuid

# Inisialisasi Blueprint untuk modul Importer
importer_bp = Blueprint('importer', __name__)

@importer_bp.route('/smart-upload', methods=['POST'])
def smart_upload():
    """
    Endpoint pintu tunggal untuk mengunggah file CID, MC, MB, atau DAILY.
    Sistem akan mendeteksi tipe file secara otomatis di latar belakang.
    """
    f_obj = request.files.get('file_main')
    
    if not f_obj or f_obj.filename == '':
        return '<div class="alert alert-danger p-2 small">Pilih file terlebih dahulu!</div>'

    # 1. Pastikan folder penyimpanan aman tersedia (bukan di static/ agar terproteksi)
    upload_dir = os.path.join('storage', 'tmp')
    os.makedirs(upload_dir, exist_ok=True)

    # 2. Amankan nama file dengan UUID untuk mencegah tabrakan data (Collision)
    ext = os.path.splitext(f_obj.filename)[1]
    filename = secure_filename(f"UPLOAD_{uuid.uuid4().hex[:8]}{ext}")
    filepath = os.path.join(upload_dir, filename)
    f_obj.save(filepath)

    # 3. Kirim tugas ke Celery Worker secara asinkron agar UI tidak freeze
    task = process_upload_task.delay(filepath)

    # 4. Berikan respon instan berupa Progress Bar yang akan di-update oleh HTMX
    return f'''
    <div hx-get="/api/import/status/{task.id}" hx-trigger="every 1s" hx-target="this" hx-swap="outerHTML">
        <div class="progress mt-3" style="height: 25px;">
            <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
                 style="width: 20%">Menganalisis Kolom File...</div>
        </div>
    </div>
    '''

@importer_bp.route('/status/<task_id>')
def task_status(task_id):
    """
    Endpoint pengecekan status tugas (Polling) untuk memperbarui tampilan progress bar.
    """
    # Mengambil hasil tugas dari Redis
    res = celery.AsyncResult(task_id)
    
    if res.state == 'PROGRESS':
        info = res.info
        percent = info.get('percent', 0)
        status_text = info.get('status', 'Memproses...')
        file_type = info.get('type', 'Data')
        
        return f'''
        <div hx-get="/api/import/status/{task_id}" hx-trigger="every 1s" hx-target="this" hx-swap="outerHTML">
            <div class="d-flex justify-content-between small mb-1">
                <span class="fw-bold text-primary">Memproses {file_type}: {status_text}</span>
                <span>{percent}%</span>
            </div>
            <div class="progress" style="height: 25px;">
                <div class="progress-bar bg-info progress-bar-striped progress-bar-animated" 
                     style="width: {percent}%"></div>
            </div>
        </div>
        '''
        
    elif res.state == 'SUCCESS':
        data = res.result
        # Cek jika ada error logika di dalam task
        if isinstance(data, dict) and data.get('status') == 'FAILURE':
            return f'<div class="alert alert-danger mt-3 small"><b>Gagal:</b> {data.get("message")}</div>'
            
        # Tampilkan laporan keberhasilan dengan jumlah data
        return f'''
        <div class="alert alert-success mt-3 shadow-sm border-start border-4 border-success bounce-in">
            <div class="d-flex align-items-center">
                <i class="fas fa-check-circle fa-2x me-3"></i>
                <div>
                    <h6 class="mb-0 fw-bold">Sinkronisasi {data.get('type')} Selesai!</h6>
                    <small>Total <b>{data.get('count', 0):,}</b> baris data berhasil disuntikkan ke database.</small>
                </div>
            </div>
        </div>
        '''
        
    elif res.state == 'FAILURE':
        # Penanganan jika worker mengalami crash
        return f'''
        <div class="alert alert-danger mt-3 small text-center">
            <i class="fas fa-exclamation-triangle me-2"></i>
            <b>Kesalahan Sistem:</b> {str(res.info)}
        </div>
        '''
    
    # Kondisi saat tugas baru saja dibuat (Pending)
    return f'''
    <div hx-get="/api/import/status/{task_id}" hx-trigger="every 1s" hx-target="this" hx-swap="outerHTML">
        <div class="progress mt-3">
            <div class="progress-bar bg-secondary" style="width: 10%">Menunggu Antrean...</div>
        </div>
    </div>
    '''
