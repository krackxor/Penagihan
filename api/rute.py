"""
Rute API - Sunter Dashboard Pro
Sinergi & Smart Update:
1. Smart Autopilot: Otomatis mendeteksi rute (PCEZ) baru dari Master Pelanggan (MC) tanpa input manual.
2. Geo-Sync: Menghitung beban kerja (jumlah pelanggan) per petugas secara real-time.
3. WhatsApp Territory Link: Menjamin nomor admin wilayah selalu tersinkronisasi untuk laporan otomatis.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse, clean_phone

rute_bp = Blueprint('rute', __name__)

@rute_bp.route('/list', methods=['GET'])
def get_rute_list():
    """
    LOGIKA AUTOPILOT:
    Mengambil semua daftar rute (PCEZ) yang aktif di periode terbaru.
    Sinergi: Otomatis menyatukan data rute dari MC dengan mapping petugas yang ada.
    """
    db = get_db_connection()
    try:
        # Query Sinergi: Menampilkan semua PCEZ unik dari master_pelanggan 
        # digabung dengan informasi petugas. Jika rute baru muncul di MC, 
        # sistem akan menampilkannya sebagai 'UNMAPPED' secara otomatis.
        query = """
            SELECT 
                m.pcez, 
                COALESCE(r.petugas, 'UNMAPPED') as petugas, 
                COALESCE(r.no_admin, '-') as no_admin,
                COUNT(m.id) as jml_pelanggan,
                MAX(m.periode) as periode_aktif
            FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            WHERE m.periode = (SELECT MAX(periode) FROM master_pelanggan)
            GROUP BY m.pcez
            ORDER BY m.pcez ASC
        """
        rows = db.execute(query).fetchall()
        
        # Mengembalikan data dalam format list dictionary untuk konsumsi Frontend
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        # Error logging untuk memudahkan audit sistem
        return APIResponse.error(message="Gagal memuat rute Autopilot", details=str(e))
    finally:
        db.close()

@rute_bp.route('/save', methods=['POST'])
def save_rute_manual():
    """
    SMART MAPPING MANUAL:
    Simpan mapping petugas dan nomor admin untuk satu kode PCEZ tertentu.
    Akses: Khusus Admin.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak: Membutuhkan Level Administrator", code=403)

    db = get_db_connection()
    # Mengambil data dari form dan menstandarisasi format teks (Upper Case)
    pcez = request.form.get('pcez')
    petugas = request.form.get('petugas', '').strip().upper()
    
    # Sanitasi nomor WA menggunakan helper clean_phone agar selalu berformat 628xxx
    no_admin = clean_phone(request.form.get('no_admin', '628123456789'))

    if not pcez or not petugas:
        return APIResponse.error("ID Rute (PCEZ) dan Nama Petugas tidak boleh kosong")

    try:
        # INSERT OR REPLACE menjamin tidak ada duplikasi kode PCEZ di database
        db.execute("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (pcez, petugas, no_admin))
        db.commit()
        return APIResponse.success(message=f"Sinergi Berhasil: Rute {pcez} dikunci ke petugas {petugas}")
    except Exception as e:
        return APIResponse.error(message="Gagal sinkronisasi rute manual", details=str(e))
    finally:
        db.close()

@rute_bp.route('/mass-update', methods=['POST'])
def mass_update_petugas():
    """
    BATCH PROCESSING (SMART UPDATE):
    Mengalokasikan banyak rute ke satu petugas dalam satu kali klik.
    Sinergi: Sangat berguna saat pergantian shift atau reorganisasi wilayah.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas: Hubungi Admin Pusat", code=403)

    # Mengambil data JSON dari body request
    data = request.get_json()
    pcez_list = data.get('pcez_list', [])
    petugas = data.get('petugas', '').strip().upper()
    
    # Nomor admin wilayah untuk tembusan WhatsApp
    no_admin = clean_phone(data.get('no_admin', '628123456789'))

    if not pcez_list or not petugas:
        return APIResponse.error("Data alokasi rute atau petugas tidak valid")

    db = get_db_connection()
    try:
        # Persiapan data batch untuk transaksi efisien
        batch_data = [(p, petugas, no_admin) for p in pcez_list]
        
        # Eksekusi massal menggunakan executemany (Performa Tinggi)
        db.executemany("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, batch_data)
        
        db.commit()
        return APIResponse.success(message=f"Smart Update: {len(pcez_list)} rute berhasil dialokasikan ke {petugas}")
    except Exception as e:
        db.rollback() # Membatalkan semua perubahan jika terjadi error di tengah jalan
        return APIResponse.error(message="Gagal proses batch update rute", details=str(e))
    finally:
        db.close()

@rute_bp.route('/sync-autopilot', methods=['POST'])
def sync_from_mc():
    """
    FUNGSI AUTOPILOT EKSTRA:
    Sinkronisasi rute otomatis berdasarkan data MC terbaru.
    Mencari PCEZ yang belum terdaftar di rute_petugas dan menambahkannya sebagai draft.
    """
    db = get_db_connection()
    try:
        # Menambahkan rute baru yang ditemukan di Master Pelanggan namun belum ada di Mapping
        db.execute("""
            INSERT OR IGNORE INTO rute_petugas (pcez, petugas, updated_at)
            SELECT DISTINCT pcez, 'UNMAPPED', CURRENT_TIMESTAMP
            FROM master_pelanggan
            WHERE pcez NOT IN (SELECT pcez FROM rute_petugas)
        """)
        db.commit()
        return APIResponse.success(message="Autopilot: Database Rute telah disinkronkan dengan Master Pelanggan")
    except Exception as e:
        return APIResponse.error(message="Gagal autopilot sinkronisasi", details=str(e))
    finally:
        db.close()
