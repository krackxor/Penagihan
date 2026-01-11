"""
History API Endpoints - Area Service Integrated System (V7.4 Enterprise Edition)
Integritas Data & Audit Geospasial:
1. Geospasial Telemetry: Validasi ketat koordinat GPS untuk mencegah data '0.0'.
2. Ultimate Snapshot: Proteksi permanen data Nama, Alamat, dan NOMET (Alfanumerik).
3. Cross-Platform Sync: Mendukung parameter periode (MM-YYYY) untuk audit lintas waktu.
4. WIB Timezone Guard: Sinkronisasi waktu Asia/Jakarta (pytz) untuk akurasi timestamp audit.
"""

import os
import pytz
import sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

# Inisialisasi Blueprint untuk modul History Area Service
history_bp = Blueprint('history', __name__)

# ==========================================
# 1. MODUL AUDIT & LOG OPERASIONAL
# ==========================================

@history_bp.route('/list', methods=['GET'])
def get_history():
    """
    [FUNGSI: AUDIT JEJAK DATA MASTER]
    Kegunaan: Menampilkan log sinkronisasi file master Excel oleh Admin.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Otoritas terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        query = """
            SELECT 
                id, 
                COALESCE(file_name, 'Unknown_Source') as file_name, 
                COALESCE(file_type, 'N/A') as file_type, 
                COALESCE(periode, '-') as periode, 
                COALESCE(row_count, 0) as row_count, 
                COALESCE(status, 'Unknown') as status, 
                created_at 
            FROM upload_history 
            ORDER BY created_at DESC LIMIT 100
        """
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
        
    except sqlite3.OperationalError:
        return APIResponse.error("Pangkalan data log tidak ditemukan.", code=500)
    except Exception as e:
        return APIResponse.error(f"Gagal memproses log audit: {str(e)}", code=500)
    finally:
        conn.close()

# ==========================================
# 2. MODUL SNAPSHOT KUNJUNGAN & GPS
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """
    [FUNGSI: ENGINE SNAPSHOT & TELEMETRI GPS]
    Logika:
    1. Mengunci identitas fisik (NOMET, Nama, Alamat) secara permanen.
    2. Menangkap koordinat GPS dan memvalidasi tipe data agar tidak 'Lost Signal'.
    """
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_wib = datetime.now(tz_jkt)
    waktu_str = waktu_wib.strftime('%Y-%m-%d %H:%M:%S')

    nomen   = request.form.get('idpel') or request.form.get('nomen')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil')
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    
    # Penangkapan Koordinat Geospasial
    lat = request.form.get('latitude')   
    lng = request.form.get('longitude')  
    foto = request.files.get('foto')

    if not nomen or not foto:
        return APIResponse.error("ID Pelanggan dan Dokumentasi Visual wajib disertakan", code=400)

    conn = get_db_connection()
    try:
        # --- LANGKAH 1: SNAPSHOT DATA MASTER ---
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, nominal, kubik, rayon
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # --- LANGKAH 2: AGREGASI PIUTANG ARDEBT ---
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # Validasi Data Snapshot (Integrity Guard)
        val_nama    = p_info['nama'] if p_info else "Entitas Konsumen"
        val_nomet   = p_info['nomet'] if p_info else "-"
        val_alamat  = p_info['alamat'] if p_info else "-"
        val_mc      = p_info['nominal'] if p_info else 0
        val_ardebt  = a_info['total'] if a_info and a_info['total'] else 0
        val_rayon   = p_info['rayon'] if p_info else "-"
        
        # --- LANGKAH 3: PROTOKOL PENYIMPANAN VISUAL ---
        filename = f"AREA_{nomen}_{waktu_wib.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan', filename)
        foto.save(upload_path)

        # --- LANGKAH 4: TRANSAKSI DATABASE (SNAPSHOT & GPS) ---
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, nomet, nama_snapshot, alamat_snapshot, petugas_name, no_hp, 
             keterangan, catatan, foto_path, mc, ardebt, latitude, longitude, periode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, val_nomet, val_nama, val_alamat, petugas, no_hp, 
              hasil, catatan, filename, val_mc, val_ardebt, 
              lat, lng, waktu_wib.strftime('%m-%Y'), waktu_str))
        conn.commit()

        return jsonify({
            "status": "success",
            "message": "Snapshot Operasional & Geospasial Terverifikasi",
            "wa_data": {
                "nomen": nomen, "nama": val_nama, "nomet": val_nomet, 
                "total": val_mc + val_ardebt, "status": hasil, 
                "waktu": waktu_str, "petugas": petugas, 
                "foto_path": filename, "catatan": catatan, "rayon": val_rayon
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        return APIResponse.error(f"Gagal melakukan snapshot sistem: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: FEED AUDIT LAPANGAN]
    Kegunaan: Menampilkan histori laporan berdasarkan parameter periode dan otoritas role.
    """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode = request.args.get('periode') # Format yang diharapkan: MM-YYYY

    # Default ke periode berjalan jika parameter kosong
    if not periode:
        periode = datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        # Mengambil data dari repositori snapshot permanen
        query = """
            SELECT id, created_at as waktu, petugas_name, nomen, nomet,
                   nama_snapshot as nama, alamat_snapshot as alamat,
                   keterangan, catatan, foto_path,
                   mc, ardebt, latitude, longitude
            FROM kunjungan_petugas
            WHERE periode = ?
        """
        params = [periode]

        if role == 'petugas':
            query += " AND petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " ORDER BY created_at DESC").fetchall()
        
        # Konversi ke List of Dict untuk transmisi JSON
        data_list = []
        for row in rows:
            d = dict(row)
            # Normalisasi data geospasial agar terbaca benar oleh Frontend Monitoring
            d['latitude'] = str(d['latitude']) if d['latitude'] else '0.0'
            d['longitude'] = str(d['longitude']) if d['longitude'] else '0.0'
            data_list.append(d)

        return APIResponse.success(data=data_list)
    except Exception as e:
        return APIResponse.error(f"Gagal sinkronisasi data audit: {str(e)}", code=500)
    finally:
        conn.close()
