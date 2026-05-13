from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from workers.tasks import process_upload_task
import os
import uuid

importer_bp = Blueprint('importer', __name__)

@importer_bp.route('/tagihan', methods=['POST'])
def import_tagihan():
    """Menerima file dan mengirimnya ke Celery Worker."""
    # Ambil file dari form upload
    files = {
        'CID': request.files.get('file_cid'),
        'MC': request.files.get('file_mc'),
        'DAILY': request.files.get('file_daily')
    }

    uploaded_info = []
    for f_type, f_obj in files.items():
        if f_obj:
            # Gunakan folder storage/tmp yang aman (di luar static) [cite: 1542]
            filename = secure_filename(f"{f_type}_{uuid.uuid4().hex[:8]}_{f_obj.filename}")
            filepath = os.path.join('storage', 'tmp', filename)
            f_obj.save(filepath)
            
            # Pemicu Asinkron: User tidak perlu menunggu loading [cite: 2321, 2335]
            task = process_upload_task.delay(filepath, f_type)
            uploaded_info.append({"type": f_type, "task_id": task.id})

    if not uploaded_info:
        return jsonify({"status": "error", "message": "Tidak ada file yang diunggah"}), 400

    return jsonify({
        "status": "success", 
        "message": "File diterima dan sedang diproses di latar belakang.",
        "details": uploaded_info
    }), 202
