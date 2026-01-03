from flask import Blueprint, jsonify
from core.database import get_db_connection

# Mendefinisikan blueprint history
history_bp = Blueprint('history', __name__)

@history_bp.route('/history/list', methods=['GET'])
def get_upload_history():
    """
    Mengambil data riwayat upload dari database.
    Pastikan tabel 'upload_history' sudah ada di schema.sql Anda.
    """
    db = get_db_connection()
    try:
        # Query contoh untuk mengambil log aktivitas upload
        query = "SELECT filename, file_type, periode, status, created_at FROM upload_history ORDER BY created_at DESC"
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        # Jika tabel belum ada, kirim data kosong agar tidak crash
        return jsonify([])
