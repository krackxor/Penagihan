"""
Ardebt (Tagihan Berekor) API Endpoints
Logic: Menampilkan data tunggakan berekor yang terhubung dengan Master Pelanggan (MC)

Author: Sunter Team
Updated: 2025-01-03
"""

from flask import Blueprint, request, jsonify
from core.database import get_db_connection
from core.helpers import APIResponse

ardebt_bp = Blueprint('ardebt', __name__)

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    Endpoint untuk mengambil daftar tunggakan berekor (Ardebt).
    - Data Utama: Tabel ardebt
    - Join: master_pelanggan (untuk Nama & PCEZ/Rute)
    - Join: rute_petugas (untuk Nama Petugas)
    - Filter: Hanya nomen yang ada di MC (Inner Join)
    """
    petugas_filter = request.args.get('petugas')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Query sesuai instruksi: INNER JOIN ke MC dan GROUP BY nomen
        query = """
            SELECT 
                a.nomen, 
                MAX(p.nama) as nama,
                MAX(p.pcez) as pcez,
                SUM(a.jumlah) as total_tunggakan, 
                COUNT(a.periode_bill) as jumlah_ekor,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            GROUP BY a.nomen
            HAVING total_tunggakan > 0
        """
        
        params = []
        # Logika filter jika memilih petugas tertentu
        if petugas_filter and petugas_filter != 'all':
            final_query = f"SELECT * FROM ({query}) AS sub WHERE sub.nama_petugas = ?"
            params.append(petugas_filter)
            cursor.execute(final_query, params)
        else:
            # Default sorting: Tunggakan terlama (ekor terbanyak) di atas
            final_query = query + " ORDER BY jumlah_ekor DESC, total_tunggakan DESC"
            cursor.execute(final_query)

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
        cursor.execute("""
            SELECT 
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
