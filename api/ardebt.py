"""
Ardebt (Tagihan Berekor) API Endpoints
Logic: 
1. Menampilkan kuota 20 data per petugas per hari berdasarkan urutan rute (PCEZ).
2. Data yang belum dikunjungi hari kemarin tetap muncul (tidak dihapus otomatis).
3. Sembunyikan data dari daftar jika sudah dilaporkan hari ini agar daftar tetap bersih.
4. Linked dengan Master Pelanggan melalui INNER JOIN untuk kelengkapan data (Nomet, Nama, PCEZ).

Author: Sunter Team
Updated: 2026-01-08
"""

from flask import Blueprint, request
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    Endpoint Robust Ardebt:
    - Mengambil field lengkap (Nomet, Jumlah, Volume) agar tidak kosong.
    - Filter: Hanya menampilkan yang BELUM dikunjungi hari ini.
    - Kuota: Dibatasi 20 data per petugas sesuai urutan rute.
    """
    petugas_filter = request.args.get('petugas')
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Menggunakan parameterized query untuk keamanan dan JOIN langsung pada PCEZ
        query = """
            SELECT 
                a.id, 
                a.nomen, 
                p.nama, 
                p.pcez, 
                p.nomet,
                a.periode_bill, 
                a.jumlah, 
                a.volume,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE 1=1
            
            -- DATA HILANG DARI DAFTAR JIKA SUDAH DILAPORKAN HARI INI
            AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = a.nomen 
                AND date(k.created_at, '+7 hours') = ?
            )
        """
        
        params = [today_str]
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        # Urutan berdasarkan Rute (PCEZ) dan Periode Bill terlama
        # Batasi kuota 20 data sesuai permintaan operasional
        query += " ORDER BY p.pcez ASC, a.periode_bill ASC LIMIT 20"
        
        cursor.execute(query, params)
        data = [dict(row) for row in cursor.fetchall()]
        return APIResponse.success(data=data)

    except Exception as e:
        print(f"❌ Error API Ardebt: {str(e)}")
        return APIResponse.error(f"Gagal mengambil data Ardebt: {str(e)}", code=500)
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
    """Registrasi blueprint ardebt."""
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
