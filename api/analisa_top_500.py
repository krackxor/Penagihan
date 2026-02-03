"""
Analisa Top 500 API - Sunter Dashboard Pro (V2.0 Split Rayon & Realtime)
Update: 2026-02-02
---------------------------------------------------------------------------
Pembaruan:
1. ✅ SPLIT RAYON: Top 500 Rayon 34 + Top 500 Rayon 35 (Total 1000).
2. ✅ REAL-TIME EXCLUSION: Otomatis membuang data yang ada di:
   - Collection Harian (Uang Lapangan)
   - Master Bayar (Uang Bank)
   - Ardebt (Tagihan Berekor)
3. ✅ PERFORMANCE: Menggunakan LEFT JOIN IS NULL agar tidak 'muter-muter'.
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime
import pytz

analisa_top500_bp = Blueprint('analisa_top500', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def get_active_period(cursor):
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else get_wib_time().strftime('%m-%Y')

@analisa_top500_bp.route('/top500', methods=['GET'])
def get_top_500():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode = get_active_period(cursor)
        
        # Query Template yang dioptimasi (LEFT JOIN IS NULL)
        # Exclude: Ardebt, Collection Harian, Master Bayar
        base_query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.rayon, p.pcez, 
                p.nominal, p.kubik, 
                COALESCE(a.keterangan, '-') as analisa,
                COALESCE(a.updated_by, '-') as auditor,
                COALESCE(r.petugas, 'UNMAPPED') as petugas_rute
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            LEFT JOIN analisa_tagihan a ON p.nomen = a.nomen AND p.periode = a.periode
            
            -- JOIN UNTUK FILTER EXCLUSION (Lebih cepat dari NOT IN)
            LEFT JOIN ardebt ad ON p.nomen = ad.nomen
            LEFT JOIN collection_harian ch ON p.nomen = ch.nomen AND ch.periode = p.periode
            LEFT JOIN master_bayar mb ON p.nomen = mb.nomen AND mb.periode = p.periode
            
            WHERE p.periode = ? 
            AND p.status_lunas = 0 
            AND p.rayon = ?
            
            -- FILTER HANYA YANG NULL (Belum ada di tabel lain)
            AND ad.nomen IS NULL 
            AND ch.nomen IS NULL 
            AND mb.nomen IS NULL
            
            ORDER BY p.nominal DESC 
            LIMIT 500
        """
        
        # 1. Ambil Top 500 Rayon 34
        cursor.execute(base_query, (periode, '34'))
        data_34 = [dict(row) for row in cursor.fetchall()]
        
        # 2. Ambil Top 500 Rayon 35
        cursor.execute(base_query, (periode, '35'))
        data_35 = [dict(row) for row in cursor.fetchall()]
        
        # 3. Gabungkan Data
        combined_data = data_34 + data_35
        
        return jsonify({
            "status": "success", 
            "periode": periode,
            "total_count": len(combined_data),
            "data": combined_data
        })
    except Exception as e:
        print(f"Error Analisa Top 500: {e}") # Log ke terminal
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@analisa_top500_bp.route('/update', methods=['POST'])
def update_analisa():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
        
    nomen = request.form.get('nomen')
    keterangan = request.form.get('keterangan')
    auditor = session.get('username', 'Admin')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode = get_active_period(cursor)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analisa_tagihan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nomen TEXT,
                periode TEXT,
                keterangan TEXT,
                updated_by TEXT,
                updated_at DATETIME
            )
        """)
        
        check = cursor.execute("SELECT id FROM analisa_tagihan WHERE nomen = ? AND periode = ?", (nomen, periode)).fetchone()
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d %H:%M:%S')
        
        if check:
            cursor.execute("UPDATE analisa_tagihan SET keterangan = ?, updated_by = ?, updated_at = ? WHERE nomen = ? AND periode = ?", (keterangan, auditor, tgl_skrg, nomen, periode))
        else:
            cursor.execute("INSERT INTO analisa_tagihan (nomen, periode, keterangan, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)", (nomen, periode, keterangan, auditor, tgl_skrg))
            
        conn.commit()
        return jsonify({"status": "success", "message": "Analisa tersimpan"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
