"""
History API Endpoints
Logic: 
1. Riwayat unggahan file.
2. Log kunjungan petugas mendetail.
3. Analisis tren pembayaran dan identifikasi pelanggan macet.

Author: Sunter Team
Updated: 2026-01-08
"""

from flask import Blueprint, jsonify, request
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

history_bp = Blueprint('history', __name__)

@history_bp.route('/list', methods=['GET'])
def get_history():
    """Mengambil daftar riwayat unggahan file terbaru."""
    conn = get_db_connection()
    try:
        # Mengambil 50 data terbaru dari tabel log unggahan
        query = "SELECT * FROM upload_history ORDER BY created_at DESC LIMIT 50"
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def get_history_kunjungan():
    """
    Mengambil log kunjungan petugas lapangan mendetail.
    Konsistensi: Menggabungkan data dengan Master Pelanggan (MC) atau Ardebt.
    """
    conn = get_db_connection()
    try:
        # Query menggabungkan log kunjungan dengan master pelanggan (Nama & Nominal)
        query = """
            SELECT 
                k.id, k.nomen, k.petugas_name, k.keterangan, k.foto_path,
                k.latitude, k.longitude, k.created_at, k.catatan,
                COALESCE(m.nama, (SELECT p.nama FROM master_pelanggan p WHERE p.nomen = k.nomen LIMIT 1), 'Pelanggan Ardebt') as nama,
                COALESCE(m.nominal, (SELECT SUM(jumlah) FROM ardebt WHERE nomen = k.nomen), 0) as nominal
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan m ON k.nomen = m.nomen AND m.tipe = 'MC'
            GROUP BY k.id
            ORDER BY k.created_at DESC
            LIMIT 100
        """
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@history_bp.route('/analisis-bayar', methods=['GET'])
def get_analisis_pembayaran():
    """Analisis Tren Pembayaran 3 Bulan Terakhir per Termin Tanggal."""
    conn = get_db_connection()
    try:
        # Logika: Menggabungkan MB (Undue) dan Collection (Current) dengan penanganan format tanggal
        query = """
            SELECT 
                nomen, tipe_pembayaran, periode,
                CASE 
                    WHEN CAST(strftime('%d', tgl_bayar) AS INTEGER) BETWEEN 1 AND 10 THEN 'Termin 1 (1-10)'
                    WHEN CAST(strftime('%d', tgl_bayar) AS INTEGER) BETWEEN 11 AND 20 THEN 'Termin 2 (11-20)'
                    ELSE 'Termin 3 (21-31)'
                END as termin,
                tgl_bayar
            FROM (
                SELECT nomen, 'Undue' as tipe_pembayaran, tgl_bayar, periode FROM master_bayar
                UNION ALL
                SELECT nomen, 'Current' as tipe_pembayaran, pay_dt as tgl_bayar, periode FROM collection_harian
            )
            WHERE tgl_bayar >= date('now', '-3 months')
            ORDER BY tgl_bayar DESC
        """
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@history_bp.route('/nomen-macet', methods=['GET'])
def get_nomen_macet():
    """Identifikasi Pelanggan Macet (Ranking Berdasarkan Akumulasi Ardebt)."""
    conn = get_db_connection()
    try:
        # Logika: Mengambil data MC terbaru dan mencocokkan ke akumulasi Ardebt
        query = """
            SELECT 
                p.nomen, p.nama, p.pcez,
                p.nominal as nominal_terakhir,
                COUNT(a.id) as record_bulan_macet,
                SUM(a.jumlah) as total_tunggakan_akumulasi
            FROM master_pelanggan p
            INNER JOIN ardebt a ON p.nomen = a.nomen
            WHERE p.tipe = 'MC' 
            AND p.periode = (SELECT MAX(periode) FROM master_pelanggan WHERE tipe='MC')
            GROUP BY p.nomen
            ORDER BY record_bulan_macet DESC, total_tunggakan_akumulasi DESC
            LIMIT 50
        """
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@history_bp.route('/delete-upload/<int:id>', methods=['DELETE'])
def delete_upload_history(id):
    """Menghapus catatan log unggahan."""
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM upload_history WHERE id = ?", (id,))
        conn.commit()
        return APIResponse.success(message="Log riwayat berhasil dihapus")
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()
