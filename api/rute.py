"""
Rute API - Sunter Dashboard Pro (V7.4 Sinergi Intelligence)
Sinergi & Smart Update:
1. Smart Autopilot V2: Sinkronisasi rute (PCEZ) dari Master Pelanggan dengan proteksi duplikasi.
2. ✅ ENHANCED: PCEZ Filter - Memastikan hanya format rute (092/01) yang masuk ke sistem mapping.
3. Case-Insensitive Sync: Standarisasi UPPER(TRIM()) pada nama petugas untuk sinkronisasi Ardebt.
4. Load Balancing: Menghitung distribusi beban kerja pelanggan per petugas secara akurat.
5. WhatsApp Territory Link: Integrasi nomor admin wilayah untuk pelaporan otomatis.
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
        # Query Sinergi V7.4: Menambahkan filter LIKE '%/%' untuk memastikan 
        # hanya format 092/01 yang ditampilkan, bukan kode Rayon murni.
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
            AND m.pcez LIKE '%/%' 
            GROUP BY m.pcez
            ORDER BY m.pcez ASC
        """
        rows = db.execute(query).fetchall()
        
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
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak: Membutuhkan Level Administrator", code=403)

    db = get_db_connection()
    
    pcez = request.form.get('pcez', '').strip()
    petugas = request.form.get('petugas', '').strip().upper()
    no_admin = clean_phone(request.form.get('no_admin', '628123456789'))

    if not pcez or not petugas:
        return APIResponse.error("ID Rute (PCEZ) dan Nama Petugas wajib diisi")

    try:
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

@rute_bp.route('/mass-update', methods=['POST'])
def mass_update_petugas():
    """
    [FUNGSI: BATCH PROCESSING]
    Kegunaan: Mengalokasikan banyak rute ke satu petugas.
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
    [FUNGSI: AUTOPILOT SYNC V2.1]
    Kegunaan: Mendeteksi rute baru (format 092/01) dari Master Pelanggan secara otomatis.
    """
    db = get_db_connection()
    try:
        # Sinergi V7.4: Menambahkan filter WHERE pcez LIKE '%/%' agar sistem 
        # hanya menarik data rute asli, mengabaikan kode Rayon (34092).
        db.execute("""
            INSERT OR IGNORE INTO rute_petugas (pcez, petugas, updated_at)
            SELECT DISTINCT TRIM(pcez), 'UNMAPPED', CURRENT_TIMESTAMP
            FROM master_pelanggan
            WHERE pcez IS NOT NULL 
            AND pcez LIKE '%/%' 
            AND TRIM(pcez) NOT IN (SELECT TRIM(pcez) FROM rute_petugas)
        """)
        db.commit()
        return APIResponse.success(message="Autopilot: Daftar Rute (092/01) telah disinkronkan")
    except Exception as e:
        print(f"❌ Error Sync Autopilot: {str(e)}")
        return APIResponse.error(message="Gagal autopilot sinkronisasi", details=str(e))
    finally:
        db.close()
