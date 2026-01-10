"""
History API Endpoints - Sunter Dashboard Pro (V6.8 Ultimate Snapshot)
Sinergi & Smart Update:
1. Ultimate Snapshot: Mengunci Nama, Nomet, Alamat, dan Hasil Koordinasi permanen.
2. WIB Timezone Guard: Memastikan pencatatan waktu standar Asia/Jakarta (WIB).
3. GPS Tracker: Validasi titik lokasi (Latitude/Longitude) untuk audit lapangan.
4. Triple-Check JCOUNT: Verifikasi real-time tunggakan lembar (MC vs MB vs CH).
"""

import os
import pytz # Library untuk standarisasi zona waktu Indonesia (WIB)
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
    """
    # Proteksi: Hanya Admin yang bisa melihat jejak digital sistem
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT id, file_name, file_type, periode, row_count, status, created_at 
            FROM upload_history ORDER BY created_at DESC LIMIT 100
        """).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
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
    1. Timezone Locking: Mengambil waktu presisi WIB (Asia/Jakarta).
    2. Data Snapshot: Mengambil data fisik (Nama, Alamat, Nomet) dari Master untuk dikunci.
    3. GPS Tracking: Menangkap koordinat petugas sebagai bukti kunjungan otentik.
    4. Database Persistence: Menyimpan semua data ke dalam satu baris laporan permanen.
    """
    # Pengaturan Waktu WIB (Indonesia)
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_wib = datetime.now(tz_jkt)
    waktu_str = waktu_wib.strftime('%Y-%m-%d %H:%M:%S')

    # Ekstraksi Input dari Form HP Petugas
    nomen   = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil') # Snapshot Hasil Koordinasi
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    lat     = request.form.get('latitude')   
    lng     = request.form.get('longitude')  
    foto    = request.files.get('foto')

    # Validasi Dasar: IDPEL dan Foto tidak boleh kosong
    if not nomen or not foto:
        return APIResponse.error("IDPEL dan Foto wajib dilampirkan", code=400)

    conn = get_db_connection()
    try:
        # 1. AMBIL DATA MASTER (Untuk dikunci ke dalam Snapshot)
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, nominal, kubik, pcez 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # 2. HITUNG PIUTANG LAMA (Ardebt)
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # 3. TRIPLE-CHECK JCOUNT (Verifikasi Lembar Nunggak Real-time)
        nunggak_info = conn.execute("""
            SELECT COUNT(*) as total_lembar 
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan)
        """, (nomen,)).fetchone()
        
        # Mapping Data Snapshot (Mengunci data fisik saat ini)
        val_nama       = p_info['nama'] if p_info else "Konsumen"
        val_nomet      = p_info['nomet'] if p_info else "-"
        val_alamat     = p_info['alamat'] if p_info else "-"
        val_mc         = p_info['nominal'] if p_info else 0
        val_ardebt     = a_info['total'] if a_info and a_info['total'] else 0
        val_kubik      = p_info['kubik'] if p_info else 0
        count_nunggak  = nunggak_info['total_lembar'] if nunggak_info else 0
        
        # 4. PENYIMPANAN FOTO: Menggunakan Nomen + Timestamp agar tidak duplikat
        filename = f"KUNJ_{nomen}_{waktu_wib.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 5. DATABASE INSERT (Ultimate Persistence)
        # Semua data snapshot (Nama, Alamat, Nomet) disimpan ke kolom khusus di kunjungan_petugas
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, nomet, nama_snapshot, alamat_snapshot, petugas_name, no_hp, 
             keterangan, catatan, foto_path, mc, ardebt, volume, latitude, longitude, periode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, val_nomet, val_nama, val_alamat, petugas, no_hp, 
              hasil, catatan, filename, val_mc, val_ardebt, val_kubik, 
              lat, lng, waktu_wib.strftime('%m-%Y'), waktu_str))
        conn.commit()

        # Output JSON: Data ini akan digunakan oleh JavaScript untuk Share WhatsApp
        return jsonify({
            "status": "success",
            "message": "Snapshot Laporan & GPS Berhasil Dikunci",
            "wa_data": {
                "nomen": nomen,
                "nama": val_nama,
                "nomet": val_nomet,
                "alamat": val_alamat,
                "total": val_mc + val_ardebt,
                "status": hasil,
                "waktu": waktu_str,
                "petugas": petugas,
                "foto_path": filename,
                "jcount": count_nunggak,
                "lat": lat, "lng": lng
            }
        })
    except Exception as e:
        return APIResponse.error(f"Gagal Snapshot: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: FEED DASHBOARD AUDIT]
    Kegunaan: Menampilkan seluruh histori laporan berdasarkan snapshot yang sudah dikunci.
    """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        # Mengambil data langsung dari kolom snapshot agar data tetap tampil meski Master dihapus
        query = """
            SELECT 
                id, created_at as waktu, petugas_name, nomen, nomet,
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
