"""
Ardebt (Tagihan Berekor) API Endpoints
Logic: 
1. Menampilkan kuota 20 data per petugas per hari berdasarkan urutan rute (PCEZ).
2. Data yang sudah dilaporkan akan "masuk kotak" selama 30 hari.
3. Sinergi: Menarik data Rayon dan NoTagihan untuk kelengkapan Laporan WA.
4. Fitur Search: Mendukung pencarian Nomen/Nama tanpa batasan 30 hari (untuk revisi).

Author: Sunter Team
Updated: 2026-01-09
"""

from flask import Blueprint, request, jsonify
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    petugas_filter = request.args.get('petugas')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Query Sinergi: Menambahkan p.rayon dan p.notagihan
        query = """
            SELECT 
                a.id, a.nomen, p.nama, p.pcez, p.nomet, p.rayon, p.notagihan,
                a.periode_bill, a.jumlah, a.volume,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE 1=1
        """
        params = []

        # LOGIKA SEARCH (REVISI): Jika mencari, abaikan filter 30 hari
        if search_query:
            query += " AND (a.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            # LOGIKA LIST RUTIN: Terapkan filter 30 hari agar daftar bersih
            query += """
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE k.nomen = a.nomen 
                    AND k.created_at >= datetime('now', '-30 days')
                )
            """

        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        # Batasi 20 data per petugas per rute
        query += " ORDER BY p.pcez ASC, a.periode_bill ASC LIMIT 20"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Sinergi: Mengembalikan sebagai list JSON langsung untuk sinkronisasi fetch frontend
        return jsonify([dict(row) for row in rows])
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@ardebt_bp.route('/summary', methods=['GET'])
def get_ardebt_summary():
    """Ringkasan akumulasi piutang berekor untuk dashboard KPI."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(a.id) as total_lembar_tagihan,
                COUNT(DISTINCT a.nomen) as total_nomen,
                SUM(a.jumlah) as total_rupiah
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
        """)
        row = cursor.fetchone()
        data = dict(row) if row else {"total_lembar_tagihan": 0, "total_nomen": 0, "total_rupiah": 0}
        return APIResponse.success(data=data)
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

def register_ardebt_routes(app, get_db):
    """Registrasi blueprint ardebt ke aplikasi utama."""
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
