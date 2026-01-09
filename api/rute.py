"""
Rute API - Sunter Dashboard Pro
Sinergi:
1. Mapping PCEZ ke Petugas secara manual atau massal.
2. Integrasi No Admin WA untuk tembusan laporan otomatis per wilayah.
3. Sinkronisasi otomatis dari master data pelanggan (MC).
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse, clean_phone

rute_bp = Blueprint('rute', __name__)

@rute_bp.route('/list', methods=['GET'])
def get_rute_list():
    """
    Mengambil semua daftar rute (PCEZ) dari master pelanggan.
    Sinergi: Menghitung jumlah pelanggan per rute secara real-time.
    """
    db = get_db_connection()
    try:
        # Query Sinergi: Menampilkan semua PCEZ yang ada di master_pelanggan 
        # digabung dengan informasi petugas dari rute_petugas.
        query = """
            SELECT 
                m.pcez, 
                COALESCE(r.petugas, 'None') as petugas, 
                COALESCE(r.no_admin, '-') as no_admin,
                COUNT(m.id) as jml_pelanggan
            FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            WHERE m.periode = (SELECT MAX(periode) FROM master_pelanggan)
            GROUP BY m.pcez
            ORDER BY m.pcez ASC
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(message="Gagal memuat daftar rute", details=str(e))
    finally:
        db.close()

@rute_bp.route('/save', methods=['POST'])
def save_rute_manual():
    """Simpan mapping petugas dan nomor admin untuk satu kode PCEZ."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak: Hanya Admin", code=403)

    db = get_db_connection()
    pcez = request.form.get('pcez')
    petugas = request.form.get('petugas', '').strip().upper()
    # Sanitasi nomor WA menggunakan helper clean_phone
    no_admin = clean_phone(request.form.get('no_admin', '628123456789'))

    if not pcez or not petugas:
        return APIResponse.error("Kode PCEZ dan Nama Petugas wajib diisi")

    try:
        db.execute("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (pcez, petugas, no_admin))
        db.commit()
        return APIResponse.success(message=f"Rute {pcez} berhasil dimapping ke {petugas}")
    except Exception as e:
        return APIResponse.error(message="Gagal menyimpan rute", details=str(e))
    finally:
        db.close()

@rute_bp.route('/mass-update', methods=['POST'])
def mass_update_petugas():
    """
    Update banyak rute (PCEZ) sekaligus ke satu petugas (Batch Processing).
    Sinergi: Mempercepat alokasi wilayah kerja baru.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    data = request.get_json()
    pcez_list = data.get('pcez_list', [])
    petugas = data.get('petugas', '').strip().upper()
    # Opsional: update no_admin massal jika disertakan
    no_admin = clean_phone(data.get('no_admin', '628123456789'))

    if not pcez_list or not petugas:
        return APIResponse.error("Data alokasi tidak lengkap")

    db = get_db_connection()
    try:
        # Gunakan executemany untuk performa transaksi yang lebih cepat
        batch_data = [(p, petugas, no_admin) for p in pcez_list]
        db.executemany("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, batch_data)
        
        db.commit()
        return APIResponse.success(message=f"Berhasil mengalokasikan {len(pcez_list)} rute ke {petugas}")
    except Exception as e:
        db.rollback()
        return APIResponse.error(message="Gagal update massal", details=str(e))
    finally:
        db.close()
