"""
History API Endpoints - Area Service Integrated System (V7.5 Enterprise Edition)
Integritas Data & Audit Geospasial:
1. Smart Periode Parser: Konversi otomatis format YYYY-MM (HTML5) ke MM-YYYY (DB Standard).
2. Geospasial Telemetry: Validasi ketat koordinat GPS untuk mencegah data '0.0' atau NULL.
3. Ultimate Snapshot: Proteksi permanen data Nama, Alamat, dan NOMET (Alfanumerik).
4. WIB Timezone Guard: Sinkronisasi waktu Asia/Jakarta untuk akurasi audit.
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
    """ Menampilkan log sinkronisasi file master Excel oleh Admin. """
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
    """ [FUNGSI: ENGINE SNAPSHOT & TELEMETRI GPS] """
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_wib = datetime.now(tz_jkt)
    waktu_str = waktu_wib.strftime('%Y-%m-%d %H:%M:%S')

    nomen   = request.form.get('idpel') or request.form.get('nomen')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil')
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    
    # Penangkapan Koordinat Geospasial (Default ke 0.0 jika transmisi gagal)
    lat = request.form.get('latitude') or '0.0'
    lng = request.form.get('longitude') or '0.0'
    foto = request.files.get('foto')

    if not nomen or not foto:
        return APIResponse.error("ID Pelanggan dan Dokumentasi Visual wajib disertakan", code=400)

    conn = get_db_connection()
    try:
        # --- LANGKAH 1: SNAPSHOT DATA MASTER (Proteksi Data Fisik) ---
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, nominal, kubik, rayon, pcez
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # --- LANGKAH 2: AGREGASI PIUTANG ARDEBT ---
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # Validasi Data Snapshot (Integrity Mapping)
        val_nama    = p_info['nama'] if p_info else "Entitas Konsumen"
        val_nomet   = p_info['nomet'] if p_info else "-"
        val_alamat  = p_info['alamat'] if p_info else "-"
        val_mc      = p_info['nominal'] if p_info else 0
        val_ardebt  = a_info['total'] if a_info and a_info['total'] else 0
        val_pcez    = p_info['pcez'] if p_info else "-"
        
        # --- LANGKAH 3: PROTOKOL PENYIMPANAN VISUAL ---
        filename = f"AREA_{nomen}_{waktu_wib.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan', filename)
        foto.save(upload_path)

        # --- LANGKAH 4: TRANSAKSI DATABASE ---
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
                "waktu": waktu_str, "petugas": petugas, "pcez": val_pcez,
                "latitude": lat, "longitude": lng
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        return APIResponse.error(f"Gagal melakukan snapshot sistem: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """ [FUNGSI: FEED AUDIT LAPANGAN DENGAN SMART PERIODE PARSER] """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode_raw = request.args.get('periode') # Input bisa YYYY-MM (Web) atau MM-YYYY (Manual)

    # --- LOGIKA SINKRONISASI PERIODE ---
    if periode_raw and "-" in periode_raw:
        parts = periode_raw.split('-')
        # Jika format YYYY-MM (Kalender HTML5), ubah menjadi MM-YYYY untuk DB
        if len(parts[0]) == 4:
            periode = f"{parts[1]}-{parts[0]}"
        else:
            periode = periode_raw
    else:
        periode = datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
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
        
        # --- NORMALISASI DATA UNTUK FRONTEND ---
        data_list = []
        for row in rows:
            d = dict(row)
            # Menjamin koordinat selalu valid untuk JavaScript (mencegah Kegagalan Transmisi)
            d['latitude'] = str(d['latitude']) if (d['latitude'] and d['latitude'] != 'None') else '0.0'
            d['longitude'] = str(d['longitude']) if (d['longitude'] and d['longitude'] != 'None') else '0.0'
            data_list.append(d)

        return APIResponse.success(data=data_list)
    except Exception as e:
        return APIResponse.error(f"Gagal sinkronisasi data audit: {str(e)}", code=500)
    finally:
        conn.close()
