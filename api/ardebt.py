"""
Ardebt (Tagihan Berekor) API - Smart Autopilot Version
Sinergi & Smart Update:
1. Autopilot Ardebt: Menghitung sejarah tunggakan otomatis dari data MC bulan-bulan lalu.
2. Transitional Logic: Otomatis mendeteksi periode aktif terbaru untuk masa transisi awal bulan.
3. High Value Filter: Tetap menjaga efisiensi dengan filter nominal MC >= 300.000.
4. Smart Casting & Grouping: Normalisasi NOMEN untuk akurasi link data antar periode.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

def get_latest_periode_available(cursor):
    """
    FUNGSI CERDAS: Mencari periode terakhir yang tersedia di database.
    Mencegah dashboard kosong saat ganti bulan (Tanggal 1-10).
    """
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    # Jika database kosong, gunakan bulan berjalan sebagai fallback
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    Endpoint Utama Ardebt Autopilot:
    Menampilkan nasabah dengan tagihan MC besar beserta akumulasi hutang lamanya.
    """
    # 1. IDENTIFIKASI AKSES & SESI
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    
    # 2. PARAMETER REQUEST (Search & Admin Filter)
    petugas_filter = request.args.get('petugas')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 3. DETEKSI PERIODE AKTIF (Masa Transisi)
        # Mencari periode terbaru yang ada di sistem (misal: Jan-2026 jika sudah ada, atau Des-2025 jika belum)
        current_period = get_latest_periode_available(cursor)

        # 4. QUERY AUTOPILOT SINERGI
        # Menghitung nominal bulan berjalan (MC) DAN sejarah tunggakan bulan-bulan sebelumnya
        query = f"""
            SELECT 
                p.nomen, p.nama, p.pcez, p.nomet, p.rayon,
                p.nominal as nominal_mc,                      -- Tagihan periode terbaru
                p.periode as periode_aktif,
                -- SUBQUERY SMART: Hitung total rupiah tunggakan dari periode-periode SEBELUMNYA
                COALESCE((
                    SELECT SUM(m2.nominal) 
                    FROM master_pelanggan m2 
                    WHERE CAST(m2.nomen AS TEXT) = CAST(p.nomen AS TEXT) 
                    AND m2.periode < p.periode
                    AND NOT EXISTS (
                        SELECT 1 FROM master_bayar mb 
                        WHERE CAST(mb.notagihan AS TEXT) = CAST(m2.notagihan AS TEXT)
                    )
                ), 0) as total_ardebt,
                -- SUBQUERY SMART: Hitung berapa lembar (bulan) yang menunggak
                (
                    SELECT COUNT(*) 
                    FROM master_pelanggan m2 
                    WHERE CAST(m2.nomen AS TEXT) = CAST(p.nomen AS TEXT) 
                    AND m2.periode < p.periode
                    AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m2.notagihan)
                ) as lembar_berekor,
                r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.nominal >= 300000                            -- [SMART FILTER] Efisiensi Collection
            AND NOT EXISTS (
                SELECT 1 FROM master_bayar mb 
                WHERE CAST(mb.notagihan AS TEXT) = CAST(p.notagihan AS TEXT)
            )
        """
        params = [current_period]

        # --- LOGIKA FILTER ROLE (KEAMANAN) ---
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif user_role == 'admin' and petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        # --- SMART SEARCH & AUTO-HIDE 30 HARI ---
        if search_query:
            query += " AND (CAST(p.nomen AS TEXT) LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            # Sembunyikan IDPEL yang sudah dikunjungi dalam 30 hari agar petugas menyisir rumah lain
            query += """
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE CAST(k.nomen AS TEXT) = CAST(p.nomen AS TEXT) 
                    AND k.created_at >= datetime('now', '-30 days')
                )
            """
            
        # Urutkan berdasarkan potensi rupiah terbesar (MC + Ardebt)
        query += " ORDER BY (nominal_mc + total_ardebt) DESC LIMIT 25"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return jsonify([dict(row) for row in rows])
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@ardebt_bp.route('/summary', methods=['GET'])
def get_ardebt_summary():
    """
    Dashboard Analysis: 
    Menghitung total potensi piutang berekor yang tersedia di seluruh sejarah database.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Menghitung seluruh data 'Belum Bayar' dari periode lama
        cursor.execute("""
            SELECT 
                COUNT(*) as total_lembar, 
                SUM(nominal) as total_rupiah 
            FROM master_pelanggan m
            WHERE NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m.notagihan)
            AND m.periode < (SELECT MAX(periode) FROM master_pelanggan)
        """)
        row = cursor.fetchone()
        return APIResponse.success(data=dict(row) if row else {"total_rupiah": 0, "total_lembar": 0})
    finally:
        conn.close()
