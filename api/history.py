"""
History API Endpoints - Sunter Dashboard Pro
Sinergi: 
1. Level Akses: Petugas dikunci ke log miliknya, Admin akses global (3 Level).
2. Penyatuan Logika Current (MC) dan Ardebt dalam satu respon laporan.
3. Database Audit: Menjamin foto dan log tersimpan sebelum Share WA.
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
    """Mengambil riwayat unggahan database untuk Admin Control Center."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Admin", code=403)
        
    conn = get_db_connection()
    try:
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
    """Radar Macet: Identifikasi pelanggan dengan akumulasi tunggakan tinggi."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    conn = get_db_connection()
    try:
        # Query Sinergi: Gabungkan Master (MC) dan Ardebt terbaru
        query = """
            SELECT 
                p.nomen, p.nama, p.pcez,
                COALESCE(p.nominal, 0) as nominal_terakhir,
                COUNT(a.id) as record_bulan_macet,
                SUM(a.jumlah) as total_tunggakan_akumulasi
            FROM master_pelanggan p
            INNER JOIN ardebt a ON p.nomen = a.nomen
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
    Sinergi Lapangan: Simpan foto fisik & log DB.
    Mengambil data tagihan saat ini (Snapshot) untuk dikirim via WA.
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
        # 1. Ambil data snapshot tagihan untuk laporan WA
        p_info = conn.execute("""
            SELECT nama, nomet, rayon, volume, nominal, pcez 
            FROM master_pelanggan WHERE nomen = ? ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        a_info = conn.execute("SELECT SUM(jumlah) as total FROM ardebt WHERE nomen = ?", (nomen,)).fetchone()
        
        val_mc = p_info['nominal'] if p_info else 0
        val_ardebt = a_info['total'] if a_info and a_info['total'] else 0
        
        # 2. Ambil WA Admin/Supervisor wilayah terkait
        adm = conn.execute("SELECT no_admin FROM rute_petugas WHERE pcez = ? LIMIT 1", 
                          (p_info['pcez'] if p_info else '',)).fetchone()
        wa_admin = adm['no_admin'] if adm else "628123456789"

        # 3. Proses Simpan Foto
        filename = f"KUNJ_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        # 4. Insert ke Riwayat
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, no_hp, keterangan, catatan, foto_path, mc, ardebt, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, no_hp, hasil, catatan, filename, val_mc, val_ardebt, datetime.now().strftime('%m-%Y')))
        conn.commit()

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
    """Log Aktivitas: Petugas hanya melihat miliknya, Admin Global."""
    role = session.get('role')
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
            LEFT JOIN master_pelanggan p ON k.nomen = p.nomen
            WHERE k.periode = ?
        """
        params = [periode]

        if role == 'petugas':
            query += " AND k.petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " GROUP BY k.id ORDER BY k.created_at DESC", params).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()
