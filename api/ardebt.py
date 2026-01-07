"""
Ardebt (Tagihan Berekor) API Endpoints
Logic: Menampilkan data tunggakan berekor APA ADANYA (Tanpa SUM/COUNT)
Linked dengan Master Pelanggan (MC) melalui INNER JOIN.

Author: Sunter Team
Updated: 2026-01-07
"""

from flask import Blueprint, request, jsonify
from core.database import get_db_connection
from core.helpers import APIResponse

ardebt_bp = Blueprint('ardebt', __name__)

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    Endpoint untuk mengambil daftar tunggakan berekor (Ardebt).
    - Data Utama: Tabel ardebt (Raw Data per baris)
    - Join: master_pelanggan (untuk Nama & PCEZ/Rute)
    - Filter: Hanya nomen yang ada di MC (Inner Join)
    - Agregasi: DINONAKTIFKAN (No SUM, No COUNT, No GROUP BY)
    """
    petugas_filter = request.args.get('petugas')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Query DIPERBARUI: Menampilkan rincian asli per periode_bill, jumlah, dan volume
        query = """
            SELECT 
                a.id,
                a.nomen, 
                p.nama,
                p.pcez,
                a.periode_bill, 
                a.jumlah,       
                a.volume,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
        """
        
        params = []
        if petugas_filter and petugas_filter != 'all':
            query += " WHERE r.petugas = ?"
            params.append(petugas_filter)
            
        # Sorting berdasarkan Nomen agar tagihan per pelanggan tetap berkumpul, 
        # lalu diurutkan berdasarkan periode penagihan.
        query += " ORDER BY a.nomen ASC, a.periode_bill DESC"
        
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
    """Ringkasan total tagihan berekor untuk dashboard kpi"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Summary tetap menghitung total keseluruhan untuk statistik dashboard
        cursor.execute("""
            SELECT 
                COUNT(a.id) as total_lembar_tagihan,
                COUNT(DISTINCT a.nomen) as total_nomen,
                SUM(a.jumlah) as total_rupiah
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
        """)
        return APIResponse.success(data=dict(cursor.fetchone()))
    except Exception as e:
        return APIResponse.error(str(e), code=500)
    finally:
        conn.close()

def register_ardebt_routes(app, get_db):
    """Fungsi registrasi blueprint ke app utama"""
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
