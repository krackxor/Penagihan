"""
History API Endpoints - Sunter Dashboard Pro (V6.5 Sinergi GPS Edition)
Sinergi & Smart Update:
1. GPS Geolocation: Menangkap koordinat Latitude & Longitude untuk validasi kunjungan.
2. Triple-Check JCOUNT: Verifikasi tunggakan riwayat real-time (MC vs MB vs Collection).
3. Smart Casting: Normalisasi NOMEN ke TEXT (SQLITE) mencegah pemotongan IDPEL panjang.
4. Security Level 3: Filter data berbasis SESSION ROLE & Periode Autopilot.
"""

import os
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
    Logika: Mengambil metadata dari tabel 'upload_history' untuk kontrol kualitas data.
    """
    # Proteksi Keamanan: Hanya role 'admin' yang diizinkan melihat log infrastruktur
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        # Menarik 100 aktivitas terbaru untuk memantau sinkronisasi data antar divisi
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
# 2. ENDPOINT OPERASIONAL (LAPORAN & TRACKING)
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """
    [FUNGSI: ENGINE VALIDASI & PENYIMPANAN LAPORAN LAPANGAN]
    Alur Kerja Sinergi V6.5:
    1. Ekstraksi Payload: Mengambil data Form, File Foto, dan Koordinat GPS.
    2. Snapshot Intelijen: Hitung JCOUNT (Tunggakan) & Snapshot Saldo Rupiah saat ini.
    3. File Management: Simpan bukti foto fisik dengan penamaan berbasis Timestamp.
    4. Database Persistence: Input data lengkap termasuk titik koordinat Latitude/Longitude.
    """
    # Normalisasi Input dari Frontend (Mobile App)
    nomen   = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil') 
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    lat     = request.form.get('latitude')   # Data GPS Baru
    lng     = request.form.get('longitude')  # Data GPS Baru
    foto    = request.files.get('foto')

    # Validasi Integritas: Laporan tanpa IDPEL atau Foto dianggap data sampah (Cacat)
    if not nomen or not foto:
        return APIResponse.error("Data laporan tidak valid (IDPEL/Foto Kosong)", code=400)

    conn = get_db_connection()
    try:
        # 1. SNAPSHOT PELANGGAN: Ambil data teknis terbaru dari Master (MC)
        p_info = conn.execute("""
            SELECT nama, nomet, rayon, volume, nominal, pcez 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # 2. AGREGASI ARDEBT: Hitung total piutang berekor yang belum terselesaikan
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # 3. TRIPLE-CHECK JCOUNT: Verifikasi status tunggakan di 3 tabel berbeda secara sinkron
        # Item dihitung tunggak jika ada di Master tapi tidak ada di Bayar Bank & Setoran Lapangan
        nunggak_info = conn.execute("""
            SELECT COUNT(*) as total_lembar 
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan)
        """, (nomen,)).fetchone()
        
        val_mc         = p_info['nominal'] if p_info else 0
        val_ardebt     = a_info['total'] if a_info and a_info['total'] else 0
        count_nunggak  = nunggak_info['total_lembar'] if nunggak_info else 0
        
        # 4. FILE HANDLING: Simpan bukti fisik foto ke storage server
        filename = f"KUNJ_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 5. DATABASE INPUT: Menyimpan data kunjungan lengkap dengan titik GPS
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, no_hp, keterangan, catatan, foto_path, mc, ardebt, periode, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, no_hp, hasil, catatan, filename, val_mc, val_ardebt, 
              datetime.now().strftime('%m-%Y'), lat, lng))
        conn.commit()

        # Output JSON: Payload untuk trigger WhatsApp Share di Frontend
        return jsonify({
            "status": "success",
            "message": "Validasi Kunjungan Berhasil Disimpan",
            "wa_data": {
                "nomen": nomen,
                "nama": p_info['nama'] if p_info else "Konsumen",
                "no_hp": no_hp,
                "nomet": p_info['nomet'] if p_info else "-",
                "pcez": p_info['pcez'] if p_info else "-",
                "total": val_mc + val_ardebt,
                "status": hasil,
                "catatan": catatan,
                "petugas": petugas,
                "foto_path": filename,
                "jcount": count_nunggak,
                "lat": lat,
                "lng": lng
            }
        })
    except Exception as e:
        return APIResponse.error(f"Gagal Sinkronisasi Database: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: FEED DASHBOARD REAL-TIME]
    Kegunaan: Menampilkan daftar laporan kunjungan untuk Admin (Global) dan Petugas (Personal).
    Logika: Menggunakan LEFT JOIN untuk memastikan nama pelanggan tetap tampil meski data master belum terupdate.
    """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        # Query dasar penggabungan log laporan dan data profil pelanggan
        query = """
            SELECT 
                k.id, k.created_at as waktu, k.petugas_name, k.nomen, 
                COALESCE(p.nama, 'Konsumen') as nama, 
                k.keterangan, k.catatan, k.foto_path,
                k.mc, k.ardebt, k.latitude, k.longitude
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan p ON CAST(k.nomen AS TEXT) = CAST(p.nomen AS TEXT)
            WHERE k.periode = ?
        """
        params = [periode]

        # Filter Keamanan: Petugas lapangan hanya boleh melihat performa kerjanya sendiri
        if role == 'petugas':
            query += " AND k.petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " GROUP BY k.id ORDER BY k.created_at DESC", params).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Gagal filter aktivitas: {str(e)}", code=500)
    finally:
        conn.close()
