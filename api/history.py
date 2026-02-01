"""
History API Endpoints - Sunter Dashboard Pro (V12.46 Fallback Logic)
Update: 2026-02-01
---------------------------------------------------------------------------
Pembaruan Strategis:
1. ✅ BACKUP DATA JOIN: Mengambil Nama/Alamat dari Master jika snapshot kosong (Fix Foto Hilang).
2. Smart Periode Parser: Auto-konversi YYYY-MM (HTML5) ke MM-YYYY (DB Standard).
3. Snapshot Integrity: Mengunci data Nama, Alamat, dan NOMET saat kunjungan dilakukan.
"""

import os
import pytz
import sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse, clean_nomen, clean_coordinate
from datetime import datetime

history_bp = Blueprint('history', __name__)

# ==========================================
# 1. MODUL LOG AUDIT OPERASIONAL
# ==========================================

@history_bp.route('/list', methods=['GET'])
def get_history():
    """ Menampilkan log sinkronisasi file master Excel oleh Admin. """
    if session.get('role') != 'admin':
        return APIResponse.error("Otoritas terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        query = """
            SELECT 
                id, 
                COALESCE(file_name, 'Unknown_Source') as file_name, 
                COALESCE(file_type, 'N/A') as file_type, 
                COALESCE(periode, '-') as periode, 
                COALESCE(row_count, 0) as row_count, 
                COALESCE(status, 'Unknown') as status, 
                created_at 
            FROM upload_history 
            ORDER BY created_at DESC LIMIT 100
        """
        rows = conn.execute(query).fetchall()
        return APIResponse.success(data=[dict(row) for row in rows])
        
    except Exception as e:
        return APIResponse.error(f"Gagal memproses log audit: {str(e)}", code=500)
    finally:
        conn.close()

# ==========================================
# 2. MODUL SNAPSHOT KUNJUNGAN & GPS
# ==========================================

@history_bp.route('/simpan-kunjungan', methods=['POST'])
def simpan_kunjungan():
    """ [ENGINE SNAPSHOT & TELEMETRI GPS] """
    tz_jkt = pytz.timezone('Asia/Jakarta')
    waktu_wib = datetime.now(tz_jkt)
    waktu_str = waktu_wib.strftime('%Y-%m-%d %H:%M:%S')

    # Pembersihan Nomen agar sinkron dengan Master Data
    raw_nomen = request.form.get('idpel') or request.form.get('nomen')
    nomen = clean_nomen(raw_nomen)
    
    petugas = session.get('petugas_id') or request.form.get('petugas_name')
    no_hp   = request.form.get('no_hp')
    hasil   = request.form.get('hasil') # Contoh: JANJI BAYAR, RKS, BAYAR
    catatan = request.form.get('keterangan') or request.form.get('catatan', '-')
    
    # Penangkapan Koordinat Geospasial
    lat = clean_coordinate(request.form.get('latitude'))
    lng = clean_coordinate(request.form.get('longitude'))
    foto = request.files.get('foto')

    if not nomen or not foto:
        return APIResponse.error("ID Pelanggan dan Dokumentasi Foto wajib disertakan", code=400)

    conn = get_db_connection()
    try:
        # --- LANGKAH 1: SNAPSHOT DATA MASTER ---
        p_info = conn.execute("""
            SELECT nama, nomet, alamat, nominal, pcez
            FROM master_pelanggan WHERE nomen = ? 
            ORDER BY periode DESC LIMIT 1
        """, (nomen,)).fetchone()

        # --- LANGKAH 2: AGREGASI PIUTANG ARDEBT (TOTAL RECOVERY) ---
        a_info = conn.execute("""
            SELECT SUM(jumlah) as total FROM ardebt 
            WHERE nomen = ?
        """, (nomen,)).fetchone()

        # Mapping Data Snapshot
        val_nama    = p_info['nama'] if p_info else "Entitas Konsumen"
        val_nomet   = p_info['nomet'] if p_info else "-"
        val_alamat  = p_info['alamat'] if p_info else "-"
        val_mc      = p_info['nominal'] if p_info else 0
        val_ardebt  = a_info['total'] if a_info and a_info['total'] else 0
        val_pcez    = p_info['pcez'] if p_info else "-"
        
        # --- LANGKAH 3: PENYIMPANAN VISUAL ---
        filename = f"SUNTER_{nomen}_{waktu_wib.strftime('%Y%m%d_%H%M%S')}.jpg"
        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'kunjungan', filename)
        foto.save(upload_path)

        # --- LANGKAH 4: TRANSAKSI DATABASE ---
        conn.execute("""
            INSERT INTO kunjungan_petugas 
            (nomen, nomet, nama_snapshot, alamat_snapshot, petugas_name, no_hp, 
             keterangan, catatan, foto_path, mc, ardebt, latitude, longitude, periode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nomen, val_nomet, val_nama, val_alamat, petugas, no_hp, 
              hasil, catatan, filename, val_mc, val_ardebt, 
              lat, lng, waktu_wib.strftime('%m-%Y'), waktu_str))
        conn.commit()

        return jsonify({
            "status": "success",
            "message": "Audit Lapangan Terverifikasi",
            "data": {
                "nomen": nomen, "nama": val_nama, 
                "total_audit": val_mc + val_ardebt, 
                "status": hasil, "waktu": waktu_str
            }
        })
    except Exception as e:
        if conn: conn.rollback()
        return APIResponse.error(f"Gagal melakukan snapshot: {str(e)}", code=500)
    finally:
        conn.close()

@history_bp.route('/kunjungan', methods=['GET'])
def list_kunjungan():
    """ [FEED AUDIT LAPANGAN DENGAN FALLBACK DATA] """
    role    = str(session.get('role', 'guest')).lower()
    my_id   = session.get('petugas_id')
    periode_raw = request.args.get('periode')

    # --- SINKRONISASI PERIODE (YYYY-MM HTML5 TO MM-YYYY DB) ---
    if periode_raw and "-" in periode_raw:
        parts = periode_raw.split('-')
        periode = f"{parts[1]}-{parts[0]}" if len(parts[0]) == 4 else periode_raw
    else:
        periode = datetime.now().strftime('%m-%Y')

    conn = get_db_connection()
    try:
        # ✅ PERBAIKAN UTAMA: LEFT JOIN & COALESCE
        # Jika k.nama_snapshot kosong (data lama), ambil dari m.nama (Master Pelanggan)
        query = """
            SELECT 
                k.id, k.created_at as waktu, k.petugas_name, k.nomen, k.nomet,
                COALESCE(k.nama_snapshot, m.nama, 'Tanpa Nama') as nama, 
                COALESCE(k.alamat_snapshot, m.alamat, '-') as alamat,
                k.keterangan, k.catatan, k.foto_path,
                k.mc, k.ardebt, k.latitude, k.longitude
            FROM kunjungan_petugas k
            LEFT JOIN (
                SELECT nomen, nama, alamat FROM master_pelanggan GROUP BY nomen
            ) m ON k.nomen = m.nomen
            WHERE k.periode = ?
        """
        params = [periode]

        if role == 'petugas':
            query += " AND k.petugas_name = ?"
            params.append(my_id)

        rows = conn.execute(query + " ORDER BY k.created_at DESC", params).fetchall()
        
        # Konversi ke List Dict & Bersihkan Koordinat
        data_list = []
        for row in rows:
            d = dict(row)
            d['latitude'] = clean_coordinate(d['latitude'])
            d['longitude'] = clean_coordinate(d['longitude'])
            data_list.append(d)

        return APIResponse.success(data=data_list)
    except Exception as e:
        return APIResponse.error(f"Gagal sinkronisasi data audit: {str(e)}", code=500)
    finally:
        conn.close()
