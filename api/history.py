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

# --- TAMBAHAN BARU: ANALISIS HISTORY & NOMEN MACET ---

@history_bp.route('/history/analisis-bayar', methods=['GET'])
def get_analisis_pembayaran():
    """
    1. Analisis Pembayaran 3 bulan terakhir berdasarkan termin tanggal:
       - Termin 1: Tanggal 1-10
       - Termin 2: Tanggal 11-20
       - Termin 3: Tanggal 21-31
    """
    try:
        db = get_db_connection()
        # Logika: Menggabungkan MB (Undue) dan Collection (Current) 3 bulan terakhir
        query = """
            SELECT 
                nomen,
                tipe_pembayaran,
                periode,
                CASE 
                    WHEN CAST(strftime('%d', tgl_bayar) AS INTEGER) BETWEEN 1 AND 10 THEN 'Termin 1 (1-10)'
                    WHEN CAST(strftime('%d', tgl_bayar) AS INTEGER) BETWEEN 11 AND 20 THEN 'Termin 2 (11-20)'
                    ELSE 'Termin 3 (21-31)'
                END as termin,
                tgl_bayar
            FROM (
                SELECT nomen, 'Undue' as tipe_pembayaran, tgl_bayar, periode FROM master_bayar
                UNION ALL
                SELECT nomen, pay_dt as tgl_bayar, 'Current' as tipe_pembayaran, periode FROM collection_harian
            )
            WHERE tgl_bayar >= date('now', '-3 months')
            ORDER BY tgl_bayar DESC
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@history_bp.route('/history/nomen-macet', methods=['GET'])
def get_nomen_macet():
    """
    2. Identifikasi 'Nomen Macet' dengan membandingkan data MC terbaru 
       terhadap histori pembayaran yang masuk Ardebt (Tunggakan Berekor).
    """
    try:
        db = get_db_connection()
        # Logika: Mengambil data MC periode terbaru dan mencocokkan ke tabel Ardebt
        query = """
            SELECT 
                p.nomen, 
                p.nama, 
                p.pcez,
                p.nominal as nominal_tagihan,
                COUNT(a.id) as jumlah_bulan_macet,
                SUM(a.jumlah) as total_tunggakan_ardebt
            FROM master_pelanggan p
            INNER JOIN ardebt a ON p.nomen = a.nomen
            WHERE p.tipe = 'MC' 
            AND p.periode = (SELECT MAX(periode) FROM master_pelanggan WHERE tipe='MC')
            GROUP BY p.nomen
            ORDER BY jumlah_bulan_macet DESC, total_tunggakan_ardebt DESC
            LIMIT 50
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
