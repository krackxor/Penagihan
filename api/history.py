"""
History API Endpoints - Sunter Dashboard Pro (V4.4 Sinergi Edition)
Sinergi & Smart Update:
1. Smart Casting: Normalisasi NOMEN ke TEXT (SQLITE) untuk mencegah IDPEL ilmiah/terpotong.
2. Autopilot Transition: Deteksi otomatis periode aktif jika parameter tidak dikirim.
3. Unified Reporting: Kalkulasi real-time penggabungan MC + ARDEBT.
4. Security Level 3: Filter data berbasis SESSION ROLE (Admin vs Petugas).
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
    [FUNGSI: MONITORING UNGGAHAN]
    Kegunaan: Menampilkan log riwayat import file Excel ke sistem.
    Logika: Mengambil data dari tabel upload_history untuk diaudit oleh Admin.
    """
    # Proteksi Keamanan: Hanya role 'admin' yang boleh melihat log sistem
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Admin", code=403)
        
    conn = get_db_connection()
    try:
        # Menampilkan 100 aktivitas unggahan file terbaru (MC, MB, atau Ardebt)
        rows = conn.execute("""
            SELECT id, file_name, file_type, periode, row_count, created_at 
            FROM upload_history ORDER BY created_at DESC LIMIT 100
        """).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Gagal memuat log: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/nomen-macet', methods=['GET'])
def get_nomen_macet():
    """
    [FUNGSI: ANALISIS RADAR MACET]
    Kegunaan: Menemukan pelanggan dengan jumlah lembar tunggakan ardebt terbanyak.
    Logika: Melakukan JOIN antara Master Pelanggan dan Tabel Ardebt.
    Teknis: Menggunakan CAST AS TEXT agar NOMEN (IDPEL) yang berupa angka panjang tidak error saat JOIN.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    conn = get_db_connection()
    try:
        # Sinergi Query: Menggabungkan data berjalan dengan data berekor
        query = """
            SELECT 
                p.nomen, p.nama, p.pcez,
                COALESCE(p.nominal, 0) as nominal_terakhir,
                COUNT(a.id) as record_bulan_macet,
                SUM(a.jumlah) as total_tunggakan_akumulasi
            FROM master_pelanggan p
            INNER JOIN ardebt a ON CAST(p.nomen AS TEXT) = CAST(a.nomen AS TEXT)
            WHERE p.periode = (SELECT MAX(periode) FROM master_pelanggan)
            GROUP BY p.nomen
            ORDER BY record_bulan_macet DESC, total_tunggakan_akumulasi DESC
            LIMIT 100
        """
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Error Analisis: {str(e)}", code=500)
    finally:
        conn.close()

# ==========================================
# 2. ENDPOINT OPERASIONAL (LAPORAN & WHATSAPP)
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """
    [FUNGSI: ENGINE SIMPAN LAPORAN LAPANGAN]
    Kegunaan: Memproses kiriman form dari aplikasi petugas (Foto + Hasil Tagih).
    Alur Kerja:
    1. Tangkap data Form & File.
    2. Hitung otomatis (Snapshot) saldo MC dan Ardebt saat detik laporan dibuat.
    3. Simpan fisik foto ke folder 'static/uploads/kunjungan'.
    4. Kembalikan data 'wa_data' ke Frontend untuk memicu buka aplikasi WhatsApp.
    """
    # Normalisasi Input: Mengantisipasi perbedaan nama field dari frontend
    nomen = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp = request.form.get('no_hp')
    hasil = request.form.get('hasil') 
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    foto = request.files.get('foto')

    # Validasi Dasar: IDPEL dan Foto adalah kewajiban integritas data
    if not nomen or not foto:
        return APIResponse.error("Data tidak lengkap (IDPEL/Foto kosong)", code=400)

    conn = get_db_connection()
    try:
        # 1. SNAPSHOT PELANGGAN: Ambil data terbaru dari Master Pelanggan (MC)
        p_info = conn.execute("""
            SELECT nama, nomet, rayon, volume, nominal, pcez 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # 2. SNAPSHOT ARDEBT: Hitung total tunggakan berekor secara real-time
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()
        
        val_mc = p_info['nominal'] if p_info else 0
        val_ardebt = a_info['total'] if a_info and a_info['total'] else 0
        
        # 3. ROUTING ADMIN: Cari nomor WA Supervisor berdasarkan wilayah kerja (PCEZ)
        adm = conn.execute("SELECT no_admin FROM rute_petugas WHERE pcez = ? LIMIT 1", 
                          (p_info['pcez'] if p_info else '',)).fetchone()
        wa_admin = adm['no_admin'] if adm else "628123456789" # Default fallback

        # 4. FILE HANDLING: Beri nama unik pada foto untuk menghindari duplikasi (Timestamp)
        filename = f"KUNJ_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 5. DATABASE PERSISTENCE: Simpan log kunjungan untuk audit keuangan
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, no_hp, keterangan, catatan, foto_path, mc, ardebt, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, no_hp, hasil, catatan, filename, val_mc, val_ardebt, datetime.now().strftime('%m-%Y')))
        conn.commit()

        # Respon JSON: Data ini akan dibaca oleh JavaScript untuk menyusun pesan WhatsApp
        return jsonify({
            "status": "success",
            "message": "Laporan Ardebt Berhasil Disimpan",
            "wa_data": {
                "nomen": nomen,
                "nama": p_info['nama'] if p_info else "Konsumen",
                "nomet": p_info['nomet'] if p_info else "-",
                "rayon": p_info['rayon'] if p_info else "-",
                "vol": p_info['volume'] if p_info else 0,
                "mc": val_mc,
                "ardebt": val_ardebt,
                "total": val_mc + val_ardebt,
                "status": hasil,
                "catatan": catatan,
                "petugas": petugas,
                "foto_path": filename,
                "no_admin": wa_admin
            }
        })
    except Exception as e:
        return APIResponse.error(f"Gagal simpan ke database: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: TRACKING AKTIVITAS]
    Kegunaan: Menampilkan daftar laporan yang sudah masuk (Feed).
    Logika Keamanan:
    - Petugas: Hanya bisa melihat riwayat kerja miliknya sendiri (Strict).
    - Admin: Bisa melihat seluruh laporan dari semua petugas (Global).
    - Periode: Jika user tidak memfilter bulan, otomatis menampilkan bulan saat ini.
    """
    role = str(session.get('role', 'guest')).lower()
    my_id = session.get('petugas_id')
    
    # Autopilot Periode: Menjamin dashboard tidak kosong saat pertama dibuka
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        # Query Dasar: Mengambil info laporan beserta nama pelanggan dari Master (LEFT JOIN)
        query = """
            SELECT 
                k.id, k.created_at as waktu, k.petugas_name, k.nomen, 
                COALESCE(p.nama, 'Konsumen') as nama, 
                k.keterangan, k.catatan, k.foto_path,
                k.mc, k.ardebt
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan p ON CAST(k.nomen AS TEXT) = CAST(p.nomen AS TEXT)
            WHERE k.periode = ?
        """
        params = [periode]

        # FILTER KEAMANAN: Membatasi data jika login sebagai petugas lapangan
        if role == 'petugas':
            query += " AND k.petugas_name = ?"
            params.append(my_id)

        # Eksekusi dengan pengurutan terbaru di atas
        rows = conn.execute(query + " GROUP BY k.id ORDER BY k.created_at DESC", params).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Gagal filter data: {str(e)}", code=500)
    finally:
        conn.close()
