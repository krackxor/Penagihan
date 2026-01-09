"""
Ardebt (Tagihan Berekor) API Endpoints
Sinergi & Logic: 
1. Level Akses: Petugas dikunci ke rutenya (petugas_id), Admin akses global.
2. Akumulasi Cerdas: Menggabungkan semua periode berekor per NOMEN agar list tidak panjang.
3. Kuota Lapangan: Menampilkan 20 titik rute (PCEZ) prioritas.
4. Auto-Hide: Data hilang dari list selama 30 hari setelah dilaporkan.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    # 1. Identifikasi Sinergi Login
    user_role = session.get('role')
    user_petugas_id = session.get('petugas_id') # Nama Petugas (Contoh: PIAN)
    
    # 2. Ambil Parameter Request
    petugas_filter = request.args.get('petugas') # Digunakan Admin
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 3. Query Utama dengan Akumulasi (GROUP BY nomen)
        # Menghitung total lembar berekor dan total rupiah per pelanggan
        query = """
            SELECT 
                a.id, a.nomen, p.nama, p.pcez, p.nomet, p.rayon, p.notagihan,
                GROUP_CONCAT(a.periode_bill, ', ') as rincian_periode,
                COUNT(a.id) as lembar_berekor,
                SUM(a.jumlah) as jumlah, 
                SUM(a.volume) as volume,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE 1=1
        """
        params = []

        # --- LOGIKA PROTEKSI AKSES 3 LEVEL ---
        if user_role == 'petugas':
            # Paksa filter rute milik petugas yang login
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif user_role == 'admin' and petugas_filter and petugas_filter != 'all':
            # Admin memilih petugas tertentu dari dropdown
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        # --- LOGIKA PENCARIAN & FILTER 30 HARI ---
        if search_query:
            query += " AND (a.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        else:
            # Filter Kotak (Hanya tampilkan yang belum dikunjungi dalam 30 hari terakhir)
            query += """
                AND NOT EXISTS (
                    SELECT 1 FROM kunjungan_petugas k 
                    WHERE k.nomen = a.nomen 
                    AND k.created_at >= datetime('now', '-30 days')
                )
            """
            
        # Finalisasi Query: Kelompokkan per Nomen dan urutkan rute terkecil
        query += """ 
            GROUP BY a.nomen 
            ORDER BY p.pcez ASC, lembar_berekor DESC 
            LIMIT 20 
        """
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Sinergi Fetch: Mengembalikan list JSON murni untuk performa frontend mobile
        return jsonify([dict(row) for row in rows])
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@ardebt_bp.route('/summary', methods=['GET'])
def get_ardebt_summary():
    """Analisis Dashboard: Menghitung beban piutang berekor global."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Query optimasi untuk ringkasan cepat
        cursor.execute("""
            SELECT 
                COUNT(id) as total_lembar,
                COUNT(DISTINCT nomen) as total_pelanggan,
                SUM(jumlah) as total_rupiah,
                SUM(volume) as total_m3
            FROM ardebt
        """)
        row = cursor.fetchone()
        return APIResponse.success(data=dict(row) if row else {})
    except Exception as e:
        return APIResponse.error(str(e))
    finally:
        conn.close()
