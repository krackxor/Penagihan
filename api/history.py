"""
History API Endpoints - Sunter Dashboard Pro (V5.1 Sinergi Edition)
Sinergi & Smart Update:
1. Triple-Check JCOUNT: Hitung otomatis tunggakan riwayat (MC vs MB vs Collection).
2. Smart Casting: Normalisasi NOMEN ke TEXT (SQLITE) untuk mencegah IDPEL ilmiah/terpotong.
3. Unified Reporting: Kalkulasi real-time penggabungan MC + ARDEBT + No HP Pelanggan.
4. Security Level 3: Filter data berbasis SESSION ROLE (Admin vs Petugas).
"""

import os
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

# Inisialisasi Blueprint untuk modul History agar dapat diregistrasikan di app.py
history_bp = Blueprint('history', __name__)

# ==========================================
# 1. ANALISIS & AUDIT (KHUSUS LEVEL ADMIN)
# ==========================================

@history_bp.route('/list', methods=['GET'])
def get_history():
    """
    [FUNGSI: MONITORING UNGGAHAN]
    Kegunaan: Menampilkan log riwayat aktivitas import file Excel ke sistem.
    Logika: Mengambil metadata dari tabel 'upload_history' untuk keperluan audit Admin.
    """
    # Proteksi Keamanan: Hanya role 'admin' yang diberikan hak akses melihat log sistem
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Admin", code=403)
        
    conn = get_db_connection()
    try:
        # Mengambil 100 aktivitas unggahan terbaru untuk memantau integritas data periode berjalan
        rows = conn.execute("""
            SELECT id, file_name, file_type, periode, row_count, created_at 
            FROM upload_history ORDER BY created_at DESC LIMIT 100
        """).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Gagal memuat log unggahan: {str(e)}", code=500)
    finally:
        conn.close()

# ==========================================
# 2. ENDPOINT OPERASIONAL (LAPORAN & WHATSAPP)
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """
    [FUNGSI: ENGINE SIMPAN LAPORAN LAPANGAN + JCOUNT]
    Kegunaan: Titik akhir pemrosesan laporan petugas (Foto Bukti + Hasil Koordinasi).
    Alur Kerja Sinergi:
    1. Ekstraksi data form dan validasi file foto.
    2. Snapshot saldo & JCOUNT: Verifikasi tunggakan riwayat dari 3 tabel (MC, MB, CH).
    3. File Handling: Menyimpan foto ke server dengan naming convention unik.
    4. Payload WA: Mengembalikan data detail (Termasuk No HP Pelanggan) untuk Share WA.
    """
    # Normalisasi Input: Mendukung berbagai varian penamaan field dari frontend
    nomen = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp_pelanggan = request.form.get('no_hp')
    hasil = request.form.get('hasil') 
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    foto = request.files.get('foto')

    # Validasi Integritas: Laporan tanpa IDPEL atau Foto dianggap tidak valid/cacat
    if not nomen or not foto:
        return APIResponse.error("Data laporan (IDPEL/Foto) wajib dilampirkan", code=400)

    conn = get_db_connection()
    try:
        # 1. AMBIL SNAPSHOT MASTER: Mengambil data teknis dan wilayah terbaru
        p_info = conn.execute("""
            SELECT nama, nomet, rayon, volume, nominal, pcez 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # 2. HITUNG SALDO ARDEBT: Agregasi seluruh piutang lama dari tabel ARDEBT
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()

        # 3. HITUNG JCOUNT (TRIPLE CHECK): Menghitung lembar menunggak di Master Pelanggan
        # Baris dihitung nunggak jika NOTAGIHAN tidak ada di MB dan tidak ada di Collection
        nunggak_info = conn.execute("""
            SELECT COUNT(*) as total_lembar 
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT)
            AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan)
            AND NOT EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan)
        """, (nomen,)).fetchone()
        
        val_mc = p_info['nominal'] if p_info else 0
        val_ardebt = a_info['total'] if a_info and a_info['total'] else 0
        count_nunggak = nunggak_info['total_lembar'] if nunggak_info else 0
        
        # 4. ROUTING SUPERVISOR: Mencari nomor kontak admin pengawas wilayah
        adm = conn.execute("SELECT no_admin FROM rute_petugas WHERE pcez = ? LIMIT 1", 
                          (p_info['pcez'] if p_info else '',)).fetchone()
        wa_admin = adm['no_admin'] if adm else "628123456789"

        # 5. PENYIMPANAN FOTO
        filename = f"KUNJ_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 6. LOGGING DATABASE: Menyimpan status final laporan
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, no_hp, keterangan, catatan, foto_path, mc, ardebt, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, no_hp_pelanggan, hasil, catatan, filename, val_mc, val_ardebt, datetime.now().strftime('%m-%Y')))
        conn.commit()

        # Output JSON: Dikirim ke JavaScript executeShareWA()
        return jsonify({
            "status": "success",
            "message": "Laporan Berhasil Disimpan",
            "wa_data": {
                "nomen": nomen,
                "nama": p_info['nama'] if p_info else "Konsumen",
                "no_hp": no_hp_pelanggan, # DATA NO HP PELANGGAN
                "nomet": p_info['nomet'] if p_info else "-",
                "pcez": p_info['pcez'] if p_info else "-", # DATA WILAYAH PCEZ
                "mc": val_mc,
                "ardebt": val_ardebt,
                "total": val_mc + val_ardebt,
                "status": hasil,
                "catatan": catatan,
                "petugas": petugas,
                "foto_path": filename,
                "jcount": count_nunggak # DATA JUMLAH BULAN NUNGGAK
            }
        })
    except Exception as e:
        return APIResponse.error(f"Gagal memproses laporan: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    [FUNGSI: FEED AKTIVITAS]
    Kegunaan: Menyediakan daftar laporan kunjungan untuk ditampilkan di dashboard.
    """
    role = str(session.get('role', 'guest')).lower()
    my_id = session.get('petugas_id')
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
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

        if role == 'petugas':
            query += " AND k.petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " GROUP BY k.id ORDER BY k.created_at DESC", params).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(f"Gagal mengambil feed: {str(e)}", code=500)
    finally:
        conn.close()
