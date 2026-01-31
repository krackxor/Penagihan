"""
Rute API - Sunter Dashboard Pro (V7.3 Sinergi Intelligence)
Sinergi & Smart Update:
1. Smart Autopilot V2: Sinkronisasi rute (PCEZ) dari Master Pelanggan dengan proteksi duplikasi.
2. Case-Insensitive Sync: Standarisasi UPPER(TRIM()) pada nama petugas untuk sinkronisasi Ardebt.
3. Load Balancing: Menghitung distribusi beban kerja pelanggan per petugas secara akurat.
4. WhatsApp Territory Link: Integrasi nomor admin wilayah untuk pelaporan otomatis.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse, clean_phone

# Inisialisasi Blueprint untuk modul Rute
rute_bp = Blueprint('rute', __name__)

@rute_bp.route('/list', methods=['GET'])
def get_rute_list():
    """
    [FUNGSI: LOGIKA AUTOPILOT]
    Kegunaan: Mengambil daftar rute (PCEZ) aktif dan beban kerja petugas.
    Sinergi: Menggabungkan data Master Pelanggan terbaru dengan Mapping Rute.
    """
    db = get_db_connection()
    try:
        # Query Sinergi V7.3: Menangani sinkronisasi petugas yang tidak kedeteksi 
        # dengan standarisasi UPPER dan TRIM pada relasi JOIN.
        query = """
            SELECT 
                m.pcez, 
                COALESCE(UPPER(TRIM(r.petugas)), 'UNMAPPED') as petugas, 
                COALESCE(r.no_admin, '-') as no_admin,
                COUNT(m.id) as jml_pelanggan,
                MAX(m.periode) as periode_aktif
            FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON TRIM(m.pcez) = TRIM(r.pcez)
            WHERE m.periode = (SELECT MAX(periode) FROM master_pelanggan)
            GROUP BY m.pcez
            ORDER BY m.pcez ASC
        """
        rows = db.execute(query).fetchall()
        
        # Format list dictionary untuk konsumsi Frontend Dashboard
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        print(f"❌ Error Rute List: {str(e)}")
        return APIResponse.error(message="Gagal memuat rute Autopilot", details=str(e))
    finally:
        db.close()

@rute_bp.route('/save', methods=['POST'])
def save_rute_manual():
    """
    [FUNGSI: SMART MAPPING MANUAL]
    Kegunaan: Mengunci satu rute PCEZ ke satu petugas spesifik.
    Keamanan: Hanya untuk Level Admin.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak: Membutuhkan Level Administrator", code=403)

    db = get_db_connection()
    
    # Standarisasi Input: Menghapus spasi dan memaksa UPPER agar sinkron dengan tabel User/Ardebt
    pcez = request.form.get('pcez', '').strip()
    petugas = request.form.get('petugas', '').strip().upper()
    no_admin = clean_phone(request.form.get('no_admin', '628123456789'))

    if not pcez or not petugas:
        return APIResponse.error("ID Rute (PCEZ) dan Nama Petugas wajib diisi")

    try:
        # Gunakan TRIM pada pcez untuk memastikan integritas data
        db.execute("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (pcez, petugas, no_admin))
        db.commit()
        return APIResponse.success(message=f"Sinergi Berhasil: Rute {pcez} dikunci ke {petugas}")
    except Exception as e:
        return APIResponse.error(message="Gagal sinkronisasi rute manual", details=str(e))
    finally:
        db.close()

@rute_bp.route('/ mass-update', methods=['POST'])
def mass_update_petugas():
    """
    [FUNGSI: BATCH PROCESSING]
    Kegunaan: Mengalokasikan banyak rute ke satu petugas (Smart Update).
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas: Hubungi Admin Pusat", code=403)

    data = request.get_json()
    pcez_list = data.get('pcez_list', [])
    petugas = data.get('petugas', '').strip().upper()
    no_admin = clean_phone(data.get('no_admin', '628123456789'))

    if not pcez_list or not petugas:
        return APIResponse.error("Data alokasi rute atau petugas tidak valid")

    db = get_db_connection()
    try:
        # Persiapan batch data untuk eksekusi berperforma tinggi dengan pembersihan spasi
        batch_data = [(p.strip(), petugas, no_admin) for p in pcez_list]
        
        db.executemany("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, batch_data)
        
        db.commit()
        return APIResponse.success(message=f"Smart Update: {len(pcez_list)} rute dialokasikan ke {petugas}")
    except Exception as e:
        if db: db.rollback()
        return APIResponse.error(message="Gagal proses batch update", details=str(e))
    finally:
        db.close()

@rute_bp.route('/sync-autopilot', methods=['POST'])
def sync_from_mc():
    """
    [FUNGSI: AUTOPILOT SYNC V2]
    Kegunaan: Mendeteksi rute baru dari file Excel MC secara otomatis.
    Logika: Mendaftarkan PCEZ unik yang ada di pelanggan tetapi belum ada di mapping rute.
    """
    db = get_db_connection()
    try:
        # Sinergi V7.3: Menambahkan pembersihan spasi saat deteksi rute baru
        db.execute("""
            INSERT OR IGNORE INTO rute_petugas (pcez, petugas, updated_at)
            SELECT DISTINCT TRIM(pcez), 'UNMAPPED', CURRENT_TIMESTAMP
            FROM master_pelanggan
            WHERE pcez IS NOT NULL AND pcez != ''
            AND TRIM(pcez) NOT IN (SELECT TRIM(pcez) FROM rute_petugas)
        """)
        db.commit()
        return APIResponse.success(message="Autopilot: Daftar Rute telah disinkronkan dengan Master Pelanggan")
    except Exception as e:
        print(f"❌ Error Sync Autopilot: {str(e)}")
        return APIResponse.error(message="Gagal autopilot sinkronisasi", details=str(e))
    finally:
        db.close()
