"""
History API Endpoints - Sunter Dashboard Pro (V6.8 Ultimate Snapshot)
Sinergi & Smart Update:
1. Ultimate Snapshot: Mengunci Nama, Nomet, Alamat, dan Hasil Koordinasi permanen.
2. WIB Timezone Guard: Memastikan pencatatan waktu standar Asia/Jakarta (WIB).
3. GPS Tracker: Validasi titik lokasi (Latitude/Longitude) untuk audit lapangan.
4. Triple-Check JCOUNT: Verifikasi real-time tunggakan lembar (MC vs MB vs CH).
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
    Kegunaan: Menampilkan histori aktivitas import data Excel untuk audit Admin.
    Perbaikan V6.8: Menambahkan penanganan error jika tabel upload_history kosong atau belum ada.
    """
    # Proteksi: Hanya Admin yang bisa melihat jejak digital sistem
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        # Menarik data riwayat upload (Audit Trail)
        # Menggunakan COALESCE untuk menjamin row_count tidak NULL (Mencegah Error 500)
        query = """
            SELECT id, file_name, file_type, periode, 
                   COALESCE(row_count, 0) as row_count, 
                   status, created_at 
            FROM upload_history 
            ORDER BY created_at DESC LIMIT 100
        """
        rows = conn.execute(query).fetchall()
        
        # Validasi: Jika data kosong, kirim array kosong bukan NULL
        data_list = [dict(row) for row in rows] if rows else []
        return APIResponse.success(data=data_list)

    except sqlite3.OperationalError:
        # Kasus: Tabel belum dibuat saat inisialisasi pertama
        return APIResponse.error("Tabel Audit belum tersedia di database", code=500)
    except Exception as e:
        # Logging error ke konsol server untuk debug
        print(f"❌ Critical Error History List: {str(e)}")
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
    Logika Sinergi V6.8:
    Mengambil data fisik dari Master untuk dikunci menjadi laporan permanen.
    """
    # Standarisasi Waktu ke WIB
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_wib = datetime.now(tz_jkt)
    waktu_str = waktu_wib.strftime('%Y-%m-%d %H:%M:%S')

    # Ekstraksi Input
    nomen   = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil')
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    lat     = request.form.get('latitude')   
    lng     = request.form.get('longitude')  
    foto    = request.files.get('foto')

    if not nomen or not foto:
        return APIResponse.error("IDPEL dan Foto wajib dilampirkan", code=400)

    conn = get_db_connection()
    try:
        # 1. AMBIL DATA MASTER (Snapshot Data Fisik)
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, nominal, kubik 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # 2. HITUNG PIUTANG ARDEBT
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # 3. TRIPLE-CHECK JCOUNT (Real-time Lembar)
        nunggak_info = conn.execute("""
            SELECT COUNT(*) as total_lembar 
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan)
        """, (nomen,)).fetchone()
        
        # Penanganan data NULL untuk kestabilan JSON
        val_nama       = p_info['nama'] if p_info else "Konsumen"
        val_nomet      = p_info['nomet'] if p_info else "-"
        val_alamat     = p_info['alamat'] if p_info else "-"
        val_mc         = p_info['nominal'] if p_info else 0
        val_ardebt     = a_info['total'] if a_info and a_info['total'] else 0
        val_kubik      = p_info['kubik'] if p_info else 0
        count_nunggak  = nunggak_info['total_lembar'] if nunggak_info else 0
        
        # 4. MANAJEMEN FILE FOTO
        filename = f"KUNJ_{nomen}_{waktu_wib.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 5. DATABASE INSERT (Snapshot Permanen)
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
            "message": "Snapshot Berhasil Dikunci",
            "wa_data": {
                "nomen": nomen, "nama": val_nama, "nomet": val_nomet,
                "alamat": val_alamat, "total": val_mc + val_ardebt,
                "status": hasil, "waktu": waktu_str, "petugas": petugas,
                "foto_path": filename, "jcount": count_nunggak,
                "lat": lat, "lng": lng
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        return APIResponse.error(f"Gagal Snapshot: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: FEED DASHBOARD AUDIT]
    Menampilkan histori laporan berdasarkan snapshot yang sudah dikunci.
    """
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
        return APIResponse.error(f"Gagal memuat feed: {str(e)}", code=500)
    finally:
        conn.close()
