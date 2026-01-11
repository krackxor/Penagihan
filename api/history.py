"""
History API Endpoints - Sunter Dashboard Pro (V6.8 Ultimate Snapshot)
Sinergi & Smart Update:
1. Ultimate Snapshot: Mengunci Nama, Nomet, Alamat, dan Hasil Koordinasi permanen.
2. WIB Timezone Guard: Memastikan pencatatan waktu standar Asia/Jakarta (WIB).
3. GPS Tracker: Validasi titik lokasi (Latitude/Longitude) untuk audit lapangan.
4. Triple-Check JCOUNT: Verifikasi real-time tunggakan lembar (MC vs MB vs CH).
"""

import os
import pytz  # Library untuk standarisasi zona waktu Indonesia (WIB)
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

# Inisialisasi Blueprint untuk modul History agar dapat diregistrasi di app.py
history_bp = Blueprint('history', __name__)

# ==========================================
# 1. ANALISIS & AUDIT (KHUSUS LEVEL ADMIN)
# ==========================================

@history_bp.route('/list', methods=['GET'])
def get_history():
    """
    [FUNGSI: MONITORING LOG SISTEM]
    Kegunaan: Menampilkan histori aktivitas import data Excel untuk audit Admin.
    Logika: Mengambil record dari tabel upload_history untuk melacak siapa dan kapan data diupload.
    """
    # Proteksi Keamanan: Hanya Admin yang diizinkan mengakses log sistem
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        # Menarik data riwayat upload terbaru dengan batasan 100 baris
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
    1. Timezone Locking: Menggunakan pytz untuk menjamin waktu Indonesia Barat (WIB).
    2. Data Snapshot: Menduplikasi data master (Nama/Alamat/Nomet) ke tabel kunjungan 
       agar record bersifat permanen meskipun data master bulan depan dihapus.
    3. GPS Tracking: Menangkap koordinat petugas sebagai bukti otentik kunjungan.
    4. JCOUNT Logic: Menghitung jumlah lembar tunggakan secara real-time saat laporan dibuat.
    """
    # Standarisasi Waktu ke Asia/Jakarta (WIB)
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_wib = datetime.now(tz_jkt)
    waktu_str = waktu_wib.strftime('%Y-%m-%d %H:%M:%S')

    # Ekstraksi Data dari FormData HP Petugas
    nomen   = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil')  # Status koordinasi (Janji Bayar/Tutup/dll)
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    lat     = request.form.get('latitude')   
    lng     = request.form.get('longitude')  
    foto    = request.files.get('foto')

    # Validasi Input Krusial: IDPEL dan Foto tidak boleh kosong
    if not nomen or not foto:
        return APIResponse.error("IDPEL dan Foto wajib dilampirkan", code=400)

    conn = get_db_connection()
    try:
        # --- LANGKAH 1: PENGAMBILAN DATA MASTER UNTUK SNAPSHOT ---
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, nominal, kubik, pcez 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # --- LANGKAH 2: HITUNG TOTAL TUNGGAKAN LAMA (ARDEBT) ---
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # --- LANGKAH 3: TRIPLE-CHECK JCOUNT (LEMBAR REAL-TIME) ---
        # Memastikan lembar yang dihitung adalah yang benar-benar belum lunas di MB maupun CH
        nunggak_info = conn.execute("""
            SELECT COUNT(*) as total_lembar 
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan)
        """, (nomen,)).fetchone()
        
        # Mapping Variabel Snapshot (Fallback ke default jika data master tidak ditemukan)
        val_nama       = p_info['nama'] if p_info else "Konsumen"
        val_nomet      = p_info['nomet'] if p_info else "-"
        val_alamat     = p_info['alamat'] if p_info else "-"
        val_mc         = p_info['nominal'] if p_info else 0
        val_ardebt     = a_info['total'] if a_info and a_info['total'] else 0
        val_kubik      = p_info['kubik'] if p_info else 0
        count_nunggak  = nunggak_info['total_lembar'] if nunggak_info else 0
        
        # --- LANGKAH 4: MANAJEMEN PENYIMPANAN FOTO ---
        filename = f"KUNJ_{nomen}_{waktu_wib.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # --- LANGKAH 5: EKSEKUSI PENYIMPANAN SNAPSHOT KE DATABASE ---
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, nomet, nama_snapshot, alamat_snapshot, petugas_name, no_hp, 
             keterangan, catatan, foto_path, mc, ardebt, volume, latitude, longitude, periode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, val_nomet, val_nama, val_alamat, petugas, no_hp, 
              hasil, catatan, filename, val_mc, val_ardebt, val_kubik, 
              lat, lng, waktu_wib.strftime('%m-%Y'), waktu_str))
        conn.commit()

        # Response sukses dengan data yang dikirim ke JavaScript (untuk fitur Share WhatsApp)
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
        if conn: conn.rollback()
        return APIResponse.error(f"Gagal melakukan snapshot: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: FEED DASHBOARD AUDIT]
    Kegunaan: Menampilkan histori laporan berdasarkan snapshot yang sudah dikunci.
    Logika: Mengambil data langsung dari kolom snapshot agar laporan tetap valid 
    meskipun Master Pelanggan diupdate/dihapus untuk periode baru.
    """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        # Query dasar menggunakan data Snapshot V6.8
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

        # Filter: Petugas hanya bisa melihat laporan miliknya sendiri (Personal Performance)
        if role == 'petugas':
            query += " AND petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " ORDER BY created_at DESC").fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Gagal memuat feed aktivitas: {str(e)}", code=500)
    finally:
        conn.close()
