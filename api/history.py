from flask import Blueprint, jsonify, request
from core.database import get_db_connection

# Inisialisasi Blueprint untuk riwayat
history_bp = Blueprint('history', __name__)

@history_bp.route('/history/list', methods=['GET'])
def get_history():
    """
    Mengambil daftar riwayat unggahan file dari tabel upload_history.
    Digunakan oleh admin untuk memantau data apa saja yang sudah masuk.
    """
    try:
        db = get_db_connection()
        # Mengambil 50 data terbaru
        query = "SELECT * FROM upload_history ORDER BY created_at DESC LIMIT 50"
        rows = db.execute(query).fetchall()
        
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@history_bp.route('/history/kunjungan', methods=['GET'])
def get_history_kunjungan():
    """
    Mengambil data riwayat kunjungan petugas lapangan secara mendetail.
    Menggabungkan data kunjungan dengan data pelanggan untuk menampilkan nama dan nominal.
    """
    try:
        db = get_db_connection()
        # Query menggabungkan log kunjungan dengan master pelanggan tipe MC
        query = """
            SELECT 
                k.id,
                k.nomen,
                k.petugas_name,
                k.keterangan,
                k.foto_path,
                k.latitude,
                k.longitude,
                k.created_at,
                m.nama,
                m.nominal
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.tipe = 'MC'
            ORDER BY k.created_at DESC
            LIMIT 100
        """
        rows = db.execute(query).fetchall()
        
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@history_bp.route('/history/delete-upload/<int:id>', methods=['DELETE'])
def delete_upload_history(id):
    """
    Menghapus satu baris riwayat unggahan berdasarkan ID.
    Hanya menghapus catatan log, tidak menghapus data di tabel master.
    """
    try:
        db = get_db_connection()
        db.execute("DELETE FROM upload_history WHERE id = ?", (id,))
        db.commit()
        return jsonify({"status": "success", "message": "Riwayat berhasil dihapus"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
