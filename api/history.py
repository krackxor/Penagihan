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
    """Mengambil daftar riwayat unggahan file terbaru (Admin Only)."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Admin", code=403)
        
    conn = get_db_connection()
    try:
        query = "SELECT * FROM upload_history ORDER BY created_at DESC LIMIT 50"
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@history_bp.route('/analisis-bayar', methods=['GET'])
def get_analisis_pembayaran():
    """Analisis Tren Pembayaran 3 Bulan Terakhir (Admin Only)."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    conn = get_db_connection()
    try:
        query = """
            SELECT 
                nomen, tipe_pembayaran, periode,
                CASE 
                    WHEN CAST(strftime('%d', tgl_bayar) AS INTEGER) BETWEEN 1 AND 10 THEN 'Termin 1 (1-10)'
                    WHEN CAST(strftime('%d', tgl_bayar) AS INTEGER) BETWEEN 11 AND 20 THEN 'Termin 2 (11-20)'
                    ELSE 'Termin 3 (21-31)'
                END as termin,
                tgl_bayar
            FROM (
                SELECT nomen, 'Undue' as tipe_pembayaran, tgl_bayar, periode FROM master_bayar
                UNION ALL
                SELECT nomen, 'Current' as tipe_pembayaran, pay_dt as tgl_bayar, periode FROM collection_harian
            )
            WHERE tgl_bayar >= date('now', '-3 months')
            ORDER BY tgl_bayar DESC
        """
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

@history_bp.route('/nomen-macet', methods=['GET'])
def get_nomen_macet():
    """Identifikasi Pelanggan Macet (Admin Only)."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    conn = get_db_connection()
    try:
        query = """
            SELECT 
                p.nomen, p.nama, p.pcez,
                p.nominal as nominal_terakhir,
                COUNT(a.id) as record_bulan_macet,
                SUM(a.jumlah) as total_tunggakan_akumulasi
            FROM master_pelanggan p
            INNER JOIN ardebt a ON p.nomen = a.nomen
            WHERE p.tipe = 'MC' 
            AND p.periode = (SELECT MAX(periode) FROM master_pelanggan WHERE tipe='MC')
            GROUP BY p.nomen
            ORDER BY record_bulan_macet DESC, total_tunggakan_akumulasi DESC
            LIMIT 50
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
    """Penyimpan laporan lapangan. MENJAMIN: Simpan foto fisik & log DB."""
    nomen = request.form.get('nomen') or request.form.get('idpel')
    # Prioritaskan nama petugas dari session login agar akurat
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp = request.form.get('no_hp')
    hasil = request.form.get('hasil') or request.form.get('keterangan')
    catatan = request.form.get('catatan') or request.form.get('keterangan_lapangan')
    foto = request.files.get('foto')

    if not nomen:
        return jsonify({"status": "error", "message": "ID Pelanggan (NOMEN) tidak terbaca!"}), 400
    if not foto or not no_hp:
        return jsonify({"status": "error", "message": "Foto dan No HP wajib diisi!"}), 400

    conn = get_db_connection()
    try:
        data = conn.execute("""
            SELECT p.nama, p.nomet, p.rayon, p.volume as vol, p.nominal as mc, p.pcez
            FROM master_pelanggan p
            WHERE p.nomen = ? 
            ORDER BY p.periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        ardebt_info = conn.execute("SELECT SUM(jumlah) as total_ardebt FROM ardebt WHERE nomen = ?", (nomen,)).fetchone()
        val_ardebt = ardebt_info['total_ardebt'] if ardebt_info and ardebt_info['total_ardebt'] else 0

        admin_info = conn.execute("SELECT no_admin FROM rute_petugas WHERE pcez = ? OR petugas = ? LIMIT 1", 
                                 (data['pcez'] if data else '', petugas)).fetchone()
        no_admin = admin_info['no_admin'] if admin_info and admin_info['no_admin'] else "628123456789"

        filename = f"KUNJ_{nomen}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static/uploads/kunjungan', filename)
        foto.save(upload_path)

        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, petugas_name, no_hp, keterangan, catatan, foto_path, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (nomen, petugas, no_hp, hasil, catatan, filename, datetime.now().strftime('%m-%Y')))
        conn.commit()

        return jsonify({
            "status": "success",
            "wa_data": {
                "nomen": nomen, "nama": data['nama'] if data else "Konsumen (Data Ardebt)",
                "nomet": data['nomet'] if data else "-", "rayon": data['rayon'] if data else "-",
                "vol": data['vol'] if data else 0, "mc": data['mc'] if data else 0,
                "ardebt": val_ardebt, "total": (data['mc'] if data else 0) + val_ardebt,
                "hp": no_hp, "status": hasil, "catatan": catatan, "petugas": petugas,
                "foto_path": filename, "no_admin": no_admin
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """Mengambil riwayat kunjungan (Sinergi: Petugas hanya melihat miliknya)."""
    user_role = session.get('role')
    user_petugas_id = session.get('petugas_id')
    periode = request.args.get('periode') or datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        query = """
            SELECT 
                k.id, k.created_at as waktu, k.petugas_name, k.nomen, 
                p.nama, p.nomet, p.rayon, p.volume as vol, k.no_hp, k.keterangan, k.catatan, k.foto_path,
                p.nominal as mc, COALESCE(a.jumlah, 0) as ardebt
            FROM kunjungan_petugas k
            LEFT JOIN master_pelanggan p ON k.nomen = p.nomen
            LEFT JOIN ardebt a ON k.nomen = a.nomen
            WHERE (k.periode = ? OR strftime('%m-%Y', k.created_at) = ?)
        """
        params = [periode, periode]

        # Kunci filter jika yang login adalah Petugas
        if user_role == 'petugas':
            query += " AND k.petugas_name = ?"
            params.append(user_petugas_id)

        rows = conn.execute(query + " GROUP BY k.id ORDER BY k.created_at DESC", params).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()
