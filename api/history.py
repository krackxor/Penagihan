"""
History API Endpoints - Sunter Dashboard Pro (V7.3 Enterprise Edition)
Sinergi & Smart Update:
1. Ultimate Snapshot: Proteksi permanen data Nama, Nomet (Alfanumerik), dan Alamat.
2. Safe-Data Mapping: Menangani nilai NULL (COALESCE) secara ketat untuk mencegah Error 500.
3. WIB Timezone Guard: Standarisasi Asia/Jakarta (pytz) untuk audit waktu akurat.
4. NOMET Integrity: Menjamin nomor seri meteran dari MC tersimpan dalam riwayat kunjungan.
"""

import os
import pytz
import sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

# Inisialisasi Blueprint untuk modul History
history_bp = Blueprint('history', __name__)

# ==========================================
# 1. ANALISIS & AUDIT (KHUSUS LEVEL ADMIN)
# ==========================================

@history_bp.route('/list', methods=['GET'])
def get_history():
    """
    [FUNGSI: MONITORING LOG SISTEM]
    Kegunaan: Menampilkan histori import data Excel untuk audit Admin.
    Keamanan: COALESCE menjamin row_count dan status tidak NULL agar JSON tidak crash.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        # Menarik data riwayat upload (Smart Query V7.3)
        query = """
            SELECT 
                id, 
                COALESCE(file_name, 'Unknown_File') as file_name, 
                COALESCE(file_type, 'N/A') as file_type, 
                COALESCE(periode, '-') as periode, 
                COALESCE(row_count, 0) as row_count, 
                COALESCE(status, 'Unknown') as status, 
                created_at 
            FROM upload_history 
            ORDER BY created_at DESC LIMIT 100
        """
        rows = conn.execute(query).fetchall()
        
        history_list = [dict(row) for row in rows] if rows else []
        return APIResponse.success(data=history_list)
        
    except sqlite3.OperationalError:
        return APIResponse.error("Database belum siap atau tabel log hilang.", code=500)
    except Exception as e:
        print(f"❌ LOG ERROR HISTORY-LIST: {str(e)}")
        return APIResponse.error(f"Gagal memuat log sistem: {str(e)}", code=500)
    finally:
        conn.close()

# ==========================================
# 2. ENDPOINT OPERASIONAL (SNAPSHOT & TRACKING)
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """
    [FUNGSI: ENGINE ULTIMATE SNAPSHOT & GPS]
    Logika:
    1. Mengunci data fisik pelanggan (Nama, Alamat, NOMET) secara permanen.
    2. Menangkap koordinat GPS dan menyinkronkan waktu standar WIB.
    """
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_wib = datetime.now(tz_jkt)
    waktu_str = waktu_wib.strftime('%Y-%m-%d %H:%M:%S')

    nomen   = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil')
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    lat     = request.form.get('latitude')   
    lng     = request.form.get('longitude')  
    foto    = request.files.get('foto')

    if not nomen or not foto:
        return APIResponse.error("ID Pelanggan dan Foto wajib dilampirkan", code=400)

    conn = get_db_connection()
    try:
        # --- LANGKAH 1: SNAPSHOT DATA MASTER (Termasuk NOMET Alfanumerik) ---
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, nominal, kubik 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # --- LANGKAH 2: AGREGASI PIUTANG ARDEBT ---
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # --- LANGKAH 3: VERIFIKASI LEMBAR TUNGGAK (JCOUNT) ---
        nunggak_info = conn.execute("""
            SELECT COUNT(*) as total_lembar 
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan)
        """, (nomen,)).fetchone()
        
        # Validasi Data Fallback (NOMET Guard V7.3)
        val_nama       = p_info['nama'] if p_info else "Konsumen"
        val_nomet      = p_info['nomet'] if p_info else "-" # Mengambil NOMET dari MC
        val_alamat     = p_info['alamat'] if p_info else "-"
        val_mc         = p_info['nominal'] if p_info else 0
        val_ardebt     = a_info['total'] if a_info and a_info['total'] else 0
        val_kubik      = p_info['kubik'] if p_info else 0
        count_nunggak  = nunggak_info['total_lembar'] if nunggak_info else 0
        
        # --- LANGKAH 4: MANAJEMEN PENYIMPANAN FOTO ---
        filename = f"KUNJ_{nomen}_{waktu_wib.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan', filename)
        foto.save(upload_path)

        # --- LANGKAH 5: EKSEKUSI PENYIMPANAN SNAPSHOT ---
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, nomet, nama_snapshot, alamat_snapshot, petugas_name, no_hp, 
             keterangan, catatan, foto_path, mc, ardebt, volume, latitude, longitude, periode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, val_nomet, val_nama, val_alamat, petugas, no_hp, 
              hasil, catatan, filename, val_mc, val_ardebt, val_kubik, 
              lat, lng, waktu_wib.strftime('%m-%Y'), waktu_str))
        conn.commit()

        return jsonify({
            "status": "success",
            "message": "Snapshot & GPS Berhasil Dikunci",
            "wa_data": {
                "nomen": nomen, "nama": val_nama, "nomet": val_nomet, 
                "total": val_mc + val_ardebt, "status": hasil, 
                "waktu": waktu_str, "jcount": count_nunggak
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ ERROR SNAPSHOT SIMPAN: {str(e)}")
        return APIResponse.error(f"Gagal melakukan snapshot: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """ Menampilkan histori laporan berdasarkan data snapshot permanen. """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        query = """
            SELECT id, created_at as waktu, petugas_name, nomen, nomet,
                   nama_snapshot as nama, alamat_snapshot as alamat,
                   keterangan as hasil, catatan, foto_path,
                   mc, ardebt, latitude, longitude
            FROM kunjungan_petugas
            WHERE periode = ?
        """
        params = [periode]

        if role == 'petugas':
            query += " AND petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " ORDER BY created_at DESC").fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Gagal memuat feed aktivitas: {str(e)}", code=500)
    finally:
        conn.close()
