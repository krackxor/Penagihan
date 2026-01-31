"""
Rute API - Sunter Dashboard Pro (V7.4 Ghost-Buster Fix)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ GHOST-BUSTER JOIN: Mengganti SQL Join dengan Python-Side Mapping. 
   Ini menjamin data Petugas "UNMAPPED" hilang karena sistem sekarang 
   bisa mencocokkan rute meskipun ada karakter spasi tersembunyi (\xa0).
2. Smart Autopilot V2: Sinkronisasi rute (PCEZ) tetap aktif.
3. Robust Save: Membersihkan input manual dari karakter aneh sebelum simpan.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse, clean_phone
import pandas as pd

# Inisialisasi Blueprint untuk modul Rute
rute_bp = Blueprint('rute', __name__)

def clean_pcez(value):
    """Pembersih Super untuk Kunci PCEZ (Menghapus \xa0 dan spasi)."""
    if not value: return ""
    return str(value).replace('\xa0', '').replace(' ', '').strip().upper()

@rute_bp.route('/list', methods=['GET'])
def get_rute_list():
    """
    [FUNGSI: LOGIKA GHOST-BUSTER]
    Kegunaan: Mengambil daftar rute dan mencocokkannya secara paksa via Python.
    Solusi: Mengatasi bug 'UNMAPPED' akibat karakter tersembunyi di database.
    """
    db = get_db_connection()
    try:
        # 1. Ambil Data Pelanggan (Target)
        query_mc = """
            SELECT 
                pcez,
                COUNT(id) as jml_pelanggan,
                MAX(periode) as periode_aktif
            FROM master_pelanggan
            WHERE periode = (SELECT MAX(periode) FROM master_pelanggan)
            GROUP BY pcez
            ORDER BY pcez ASC
        """
        rows_mc = db.execute(query_mc).fetchall()

        # 2. Ambil Data Mapping (Kamus Petugas)
        query_map = "SELECT pcez, petugas, no_admin FROM rute_petugas"
        rows_map = db.execute(query_map).fetchall()

        # 3. Buat Kamus Mapping Bersih di Python
        # Kunci dictionary dibersihkan total agar pasti cocok
        mapping_dict = {}
        for r in rows_map:
            key_clean = clean_pcez(r['pcez'])
            mapping_dict[key_clean] = {
                'petugas': r['petugas'],
                'no_admin': r['no_admin']
            }

        # 4. Gabungkan Data (Python Side Join)
        final_result = []
        for row in rows_mc:
            raw_pcez = row['pcez']
            clean_key = clean_pcez(raw_pcez) # Bersihkan kunci dari MC
            
            # Cari di kamus mapping
            mapped_data = mapping_dict.get(clean_key, {})
            
            petugas_name = mapped_data.get('petugas', 'UNMAPPED')
            # Fallback visual jika petugas kosong
            if not petugas_name or petugas_name == 'UNMAPPED':
                petugas_name = 'UNMAPPED'
            else:
                petugas_name = petugas_name.upper().strip()

            final_result.append({
                "pcez": raw_pcez, # Tampilkan apa adanya sesuai MC
                "petugas": petugas_name,
                "no_admin": mapped_data.get('no_admin', '-'),
                "jml_pelanggan": row['jml_pelanggan'],
                "periode_aktif": row['periode_aktif']
            })

        return jsonify(final_result)
    except Exception as e:
        print(f"❌ Error Rute List: {str(e)}")
        return APIResponse.error(message="Gagal memuat rute Ghost-Buster", details=str(e))
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
    
    # Standarisasi Input dengan Pembersih Super
    raw_pcez = request.form.get('pcez', '')
    pcez = clean_pcez(raw_pcez) # Hapus spasi hantu saat simpan manual
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
        # Bersihkan semua key PCEZ dari list input
        batch_data = [(clean_pcez(p), petugas, no_admin) for p in pcez_list]
        
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
    """
    db = get_db_connection()
    try:
        # Menggunakan TRIM di level Database sebagai pertahanan lapis pertama
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
