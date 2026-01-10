"""
History API Endpoints - Sunter Dashboard Pro (V6.7 Ultimate Snapshot)
Sinergi & Smart Update:
1. Real-time Snapshot: Mengunci Nama, Nomet, Alamat, dan Hasil Koordinasi saat kejadian.
2. WIB Timezone Guard: Memastikan record waktu menggunakan standar Asia/Jakarta.
3. GPS Geolocation: Menangkap koordinat Latitude & Longitude untuk audit lokasi.
4. Triple-Check JCOUNT: Verifikasi tunggakan riwayat real-time (MC vs MB vs Collection).
"""

import os
import pytz # Library untuk standarisasi zona waktu WIB
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
    Kegunaan: Menampilkan jejak audit proses import data Excel (MC/MB/Ardebt).
    """
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
# 2. ENDPOINT OPERASIONAL (LAPORAN & SNAPSHOT)
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """
    [FUNGSI: ENGINE ULTIMATE SNAPSHOT & GPS]
    Alur Kerja Sinergi V6.7:
    1. Timezone Locking: Set waktu ke Asia/Jakarta (WIB).
    2. Inteligence Snapshot: Mengambil data Nomet, Nama, Alamat, dan Rupiah saat ini.
    3. Triple-Check JCOUNT: Hitung lembar tunggakan dari 3 sumber data.
    4. Database Persistence: Simpan semua data fisik pelanggan ke tabel kunjungan.
    """
    # Pengaturan Zona Waktu WIB
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_sekarang = datetime.now(tz_jkt)
    waktu_str = waktu_sekarang.strftime('%Y-%m-%d %H:%M:%S')

    # Normalisasi Input dari Frontend
    nomen   = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil') # Hasil Koordinasi (Janji Bayar, dll)
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    lat     = request.form.get('latitude')   
    lng     = request.form.get('longitude')  
    foto    = request.files.get('foto')

    if not nomen or not foto:
        return APIResponse.error("Data laporan (IDPEL/Foto) wajib dilampirkan", code=400)

    conn = get_db_connection()
    try:
        # 1. SNAPSHOT MASTER: Ambil data identitas fisik pelanggan (Snapshot Alamat & Nomet)
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, rayon, volume, nominal, pcez 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # 2. AGREGASI ARDEBT: Hitung total piutang lama
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # 3. TRIPLE-CHECK JCOUNT: Verifikasi lembar nunggak
        nunggak_info = conn.execute("""
            SELECT COUNT(*) as total_lembar 
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan)
        """, (nomen,)).fetchone()
        
        # Mapping Variabel Snapshot
        val_nama       = p_info['nama'] if p_info else "Konsumen"
        val_nomet      = p_info['nomet'] if p_info else "-"
        val_alamat     = p_info['alamat'] if p_info else "-"
        val_mc         = p_info['nominal'] if p_info else 0
        val_ardebt     = a_info['total'] if a_info and a_info['total'] else 0
        count_nunggak  = nunggak_info['total_lembar'] if nunggak_info else 0
        
        # 4. FILE HANDLING: Penamaan file unik berbasis IDPEL & Waktu
        filename = f"KUNJ_{nomen}_{waktu_sekarang.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 5. DATABASE INPUT: Mengunci data ke tabel kunjungan_petugas
        # Kolom 'created_at' diisi manual dengan waktu_str (WIB)
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, nomet, nama_snapshot, alamat_snapshot, petugas_name, no_hp, 
             keterangan, catatan, foto_path, mc, ardebt, periode, latitude, longitude, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, val_nomet, val_nama, val_alamat, petugas, no_hp, 
              hasil, catatan, filename, val_mc, val_ardebt, 
              waktu_sekarang.strftime('%m-%Y'), lat, lng, waktu_str))
        conn.commit()

        # Output JSON: Data lengkap untuk dikirim ke WhatsApp
        return jsonify({
            "status": "success",
            "message": "Validasi Kunjungan Berhasil Disimpan (WIB)",
            "wa_data": {
                "nomen": nomen,
                "nama": val_nama,
                "nomet": val_nomet,
                "alamat": val_alamat,
                "no_hp": no_hp,
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
        return APIResponse.error(f"Gagal Sinkronisasi Snapshot: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: FEED DASHBOARD REAL-TIME]
    Kegunaan: Menampilkan histori laporan kunjungan lengkap dengan snapshot data.
    """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
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
        return APIResponse.error(f"Gagal memuat histori: {str(e)}", code=500)
    finally:
        conn.close()
