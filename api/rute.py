"""
Rute API - Sunter Dashboard Pro (V7.2 Sinergi Intelligence)
Sinergi & Smart Update:
1. Smart Autopilot: Otomatis mendeteksi rute (PCEZ) baru dari Master Pelanggan (MC) tanpa input manual.
2. Case-Insensitive Guard: Menstandarisasi nama petugas (UPPER) agar sinkron dengan tabel User & Ardebt.
3. Geo-Sync: Menghitung beban kerja (jumlah pelanggan) per petugas secara real-time.
4. WhatsApp Territory Link: Menjamin nomor admin wilayah selalu tersinkronisasi untuk laporan otomatis.
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
    Kegunaan: Mengambil semua daftar rute (PCEZ) yang aktif di periode terbaru.
    Sinergi: Otomatis menyatukan data rute dari MC dengan mapping petugas yang ada. 
    Jika rute baru muncul di MC, sistem akan menampilkannya sebagai 'UNMAPPED'.
    """
    db = get_db_connection()
    try:
        # Query Sinergi V7.2: Menggunakan COALESCE agar tidak ada nilai NULL yang merusak tampilan Frontend.
        # Filter periode menggunakan subquery agar selalu merujuk ke data terbaru yang diupload.
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
        # Log error mendetail untuk memudahkan troubleshooting Admin
        print(f"❌ Error Rute List: {str(e)}")
        return APIResponse.error(message="Gagal memuat rute Autopilot", details=str(e))
    finally:
        db.close()

@rute_bp.route('/save', methods=['POST'])
def save_rute_manual():
    """
    [FUNGSI: SMART MAPPING MANUAL]
    Kegunaan: Simpan mapping petugas dan nomor admin untuk satu kode PCEZ tertentu.
    Akses: Khusus Level Admin.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak: Membutuhkan Level Administrator", code=403)

    db = get_db_connection()
    
    # Standarisasi Input: Menghapus spasi dan memaksa Huruf Besar (UPPER) agar sinkron dengan Ardebt
    pcez = request.form.get('pcez', '').strip()
    petugas = request.form.get('petugas', '').strip().upper()
    
    # Sanitasi nomor WA menggunakan helper clean_phone agar selalu berformat 628xxx
    no_admin = clean_phone(request.form.get('no_admin', '628123456789'))

    if not pcez or not petugas:
        return APIResponse.error("ID Rute (PCEZ) dan Nama Petugas tidak boleh kosong")

    try:
        # INSERT OR REPLACE: Menjamin satu PCEZ hanya dipegang satu petugas (Primary Key Guard)
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
    [FUNGSI: BATCH PROCESSING - SMART UPDATE]
    Kegunaan: Mengalokasikan banyak rute ke satu petugas sekaligus (Efisiensi Tinggi).
    Sinergi: Sangat berguna saat pergantian shift atau reorganisasi wilayah pcez.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas: Hubungi Admin Pusat", code=403)

    # Mengambil data JSON dari body request
    data = request.get_json()
    pcez_list = data.get('pcez_list', [])
    petugas = data.get('petugas', '').strip().upper()
    no_admin = clean_phone(data.get('no_admin', '628123456789'))

    if not pcez_list or not petugas:
        return APIResponse.error("Data alokasi rute atau petugas tidak valid")

    db = get_db_connection()
    try:
        # Persiapan batch data untuk eksekusi massal (executemany)
        batch_data = [(p.strip(), petugas, no_admin) for p in pcez_list]
        
        db.executemany("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, batch_data)
        
        db.commit()
        return APIResponse.success(message=f"Smart Update: {len(pcez_list)} rute berhasil dialokasikan ke {petugas}")
    except Exception as e:
        if db: db.rollback() # Batalkan transaksi jika gagal di tengah jalan
        return APIResponse.error(message="Gagal proses batch update rute", details=str(e))
    finally:
        db.close()

@rute_bp.route('/sync-autopilot', methods=['POST'])
def sync_from_mc():
    """
    [FUNGSI: AUTOPILOT SYNC]
    Kegunaan: Sinkronisasi rute otomatis berdasarkan data Master Pelanggan (MC) terbaru.
    Logika: Mencari PCEZ unik yang ada di MC tetapi belum terdaftar di tabel rute, 
    lalu menambahkannya sebagai status 'UNMAPPED'.
    """
    db = get_db_connection()
    try:
        # Sinergi V7.2: INSERT OR IGNORE mencegah error jika data sudah ada
        db.execute("""
            INSERT OR IGNORE INTO rute_petugas (pcez, petugas, updated_at)
            SELECT DISTINCT pcez, 'UNMAPPED', CURRENT_TIMESTAMP
            FROM master_pelanggan
            WHERE pcez IS NOT NULL AND pcez != ''
            AND pcez NOT IN (SELECT pcez FROM rute_petugas)
        """)
        db.commit()
        return APIResponse.success(message="Autopilot: Database Rute telah disinkronkan dengan Master Pelanggan")
    except Exception as e:
        print(f"❌ Error Sync Autopilot: {str(e)}")
        return APIResponse.error(message="Gagal autopilot sinkronisasi", details=str(e))
    finally:
        db.close()
