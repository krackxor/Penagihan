"""
Analisa Top 500 API - Sunter Dashboard Pro (V2.2 Period Filter)
Update: 2026-02-03
---------------------------------------------------------------------------
Pembaruan:
1. ✅ PERIOD FILTER: Bisa memilih periode spesifik dari parameter request.
2. ✅ STRICT SPLIT: Tetap memisahkan data Rayon 34 & 35.
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime
import pytz

analisa_top500_bp = Blueprint('analisa_top500', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def get_active_period(cursor):
    """Ambil periode terakhir dari database jika user tidak memilih."""
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
        
        # 1. LOGIKA PILIH PERIODE
        req_periode = request.args.get('periode') # Format dari HTML: YYYY-MM (misal 2026-02)
        
        if req_periode:
            try:
                # Konversi YYYY-MM (HTML) -> MM-YYYY (Database)
                parts = req_periode.split('-')
                periode = f"{parts[1]}-{parts[0]}"
            except:
                periode = get_active_period(cursor)
        else:
            periode = get_active_period(cursor)
        
        # Query Template (Optimized)
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
            
            -- EXCLUSION JOINS
            LEFT JOIN ardebt ad ON p.nomen = ad.nomen
            LEFT JOIN collection_harian ch ON p.nomen = ch.nomen AND ch.periode = p.periode
            LEFT JOIN master_bayar mb ON p.nomen = mb.nomen AND mb.periode = p.periode
            
            WHERE p.periode = ? 
            AND p.status_lunas = 0 
            AND p.rayon = ?
            
            -- SYARAT: TIDAK ADA DI TABEL EXCLUSION
            AND ad.nomen IS NULL 
            AND ch.nomen IS NULL 
            AND mb.nomen IS NULL
            
            ORDER BY p.nominal DESC 
            LIMIT 500
        """
        
        # Ambil Top 500 Rayon 34
        cursor.execute(base_query, (periode, '34'))
        data_34 = [dict(row) for row in cursor.fetchall()]
        
        # Ambil Top 500 Rayon 35
        cursor.execute(base_query, (periode, '35'))
        data_35 = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            "status": "success", 
            "periode": periode, # Kembalikan periode yang dipakai agar UI tahu
            "data_34": data_34,
            "data_35": data_35
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# ... (Fungsi update_analisa TETAP SAMA seperti sebelumnya, jangan dihapus) ...
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
        # Disini kita ambil periode dari request juga atau pakai active period
        # Idealnya analisa disimpan sesuai periode nomen tsb.
        # Untuk simplifikasi, kita ambil periode aktif saat ini untuk penyimpanan.
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
