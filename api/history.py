"""
History API Endpoints - Sunter Dashboard Pro
Sinergi & Smart Update:
1. Smart Casting: Normalisasi NOMEN ke TEXT saat audit dan pelaporan agar sinkron dengan data Excel.
2. Autopilot Transition: Otomatis mendeteksi periode terbaru jika input periode kosong.
3. Unified Reporting: Penggabungan data tagihan berjalan (MC) dan berekor (Ardebt) dalam satu respon.
4. Security Level 3: Proteksi data berdasarkan role (Admin Global vs Petugas Personal).
"""

import os
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

history_bp = Blueprint('history', __name__)

# ==========================================
# 1. ANALISIS & AUDIT (LEVEL ADMIN)
# ==========================================

@history_bp.route('/list', methods=['GET'])
def get_history():
    """
    AUDIT DASHBOARD:
    Menampilkan daftar riwayat unggahan file Excel (MC, MB, Ardebt).
    Khusus Admin untuk memantau kapan terakhir data diperbarui.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Admin", code=403)
        
    conn = get_db_connection()
    try:
        # Menampilkan 100 riwayat unggahan terakhir
        rows = conn.execute("""
            SELECT id, file_name, file_type, periode, row_count, created_at 
            FROM upload_history ORDER BY created_at DESC LIMIT 100
        """).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@history_bp.route('/nomen-macet', methods=['GET'])
def get_nomen_macet():
    """
    RADAR MACET (SMART AUDIT):
    Mengidentifikasi pelanggan dengan jumlah lembar tunggakan tertinggi.
    Menggunakan Smart Casting agar data Ardebt tetap terbaca meskipun format ID terpotong.
    """
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    conn = get_db_connection()
    try:
        # Query Sinergi: Gabungkan Master (MC) dan Ardebt menggunakan normalisasi TEXT
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
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

# ==========================================
# 2. ENDPOINT SINERGI (LAPORAN & WA SHARE)
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """
    SINERGI LAPORAN CERDAS:
    1. Menyimpan foto fisik ke server.
    2. Menarik snapshot tagihan (MC + ARDEBT) otomatis.
    3. Mengambil nomor WA Supervisor berdasarkan wilayah rute (PCEZ).
    4. Mengembalikan data lengkap untuk format kirim pesan WhatsApp.
    """
    nomen = request.form.get('nomen') or request.form.get('idpel')
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp = request.form.get('no_hp')
    hasil = request.form.get('hasil') or request.form.get('keterangan')
    catatan = request.form.get('catatan', '-')
    foto = request.files.get('foto')

    if not nomen or not foto:
        return APIResponse.error("Data laporan (IDPEL/Foto) tidak lengkap", code=400)

    conn = get_db_connection()
    try:
        # 1. Ambil snapshot data pelanggan menggunakan Smart Casting
        p_info = conn.execute("""
            SELECT nama, nomet, rayon, volume, nominal, pcez 
            FROM master_pelanggan WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # 2. Hitung total Ardebt otomatis (Logic Autopilot)
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT)
        """, (nomen,)).fetchone()
        
        val_mc = p_info['nominal'] if p_info else 0
        val_ardebt = a_info['total'] if a_info and a_info['total'] else 0
        
        # 3. Cari nomor WA Admin untuk wilayah tersebut (Sinergi Rute)
        adm = conn.execute("SELECT no_admin FROM rute_petugas WHERE pcez = ? LIMIT 1", 
                          (p_info['pcez'] if p_info else '',)).fetchone()
        wa_admin = adm['no_admin'] if adm else "628123456789"

        # 4. Proses Simpan Foto dengan Nama File Unik
        filename = f"KUNJ_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 5. Insert Log ke Database
        # Mengunci angka MC dan ARDEBT saat laporan dibuat untuk integritas audit
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, no_hp, keterangan, catatan, foto_path, mc, ardebt, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, no_hp, hasil, catatan, filename, val_mc, val_ardebt, datetime.now().strftime('%m-%Y')))
        conn.commit()

        # Respon sukses dikembalikan ke frontend untuk memicu Share WhatsApp
        return jsonify({
            "status": "success",
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
        return APIResponse.error(f"Gagal simpan: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """
    LOG AKTIVITAS (SMART FILTER):
    1. Petugas: Hanya bisa melihat riwayat miliknya sendiri.
    2. Admin: Akses global ke seluruh aktivitas tim.
    3. Autopilot Periode: Menampilkan bulan berjalan jika periode tidak dipilih.
    """
    role = str(session.get('role', 'guest')).lower()
    my_id = session.get('petugas_id')
    
    # Autopilot Periode: Jika request kosong, gunakan bulan berjalan
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

        # Filter keamanan berdasarkan level akses
        if role == 'petugas':
            query += " AND k.petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " GROUP BY k.id ORDER BY k.created_at DESC", params).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()
