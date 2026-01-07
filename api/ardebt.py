"""
Ardebt (Tagihan Berekor) API Endpoints
Logic: 
1. Menampilkan data tunggakan berekor (Max 10 data per hari).
2. Sembunyikan data jika sudah dilaporkan oleh petugas pada hari yang sama.
3. Linked dengan Master Pelanggan (MC) melalui INNER JOIN.

Author: Sunter Team
Updated: 2026-01-07
"""

from flask import Blueprint, request, jsonify
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    Endpoint untuk mengambil daftar tunggakan berekor (Ardebt).
    - Limit: 10 Data per hari.
    - Filter: Sembunyikan jika sudah dikunjungi hari ini.
    - Sorting: Prioritas data terlama (Periode Bill ASC) agar tetap muncul jika belum dikunjungi.
    """
    petugas_filter = request.args.get('petugas')
    
    # Ambil tanggal hari ini untuk filter pengecekan laporan
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Query dengan penambahan filter NOT EXISTS pada tabel kunjungan_petugas
        query = f"""
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
            WHERE 1=1
            
            -- REVISI: Sembunyikan pelanggan yang sudah dilaporkan HARI INI
            AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = a.nomen 
                AND date(k.created_at, '+7 hours') = '{today_str}'
            )
        """
        
        params = []
        if petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)
            
        # REVISI: Urutkan berdasarkan periode bill terlama dan batasi 10 baris saja
        query += " ORDER BY a.periode_bill ASC, a.nomen ASC LIMIT 10"
        
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
