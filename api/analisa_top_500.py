"""
Analisa Top 500 API - Sunter Dashboard Pro
File: api/analisa_top_500.py
Modul khusus Admin untuk memonitor Top 500 Penunggak Current (Pareto).
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime
import pytz

# Saya ubah nama variabe blueprint agar sesuai nama file
analisa_top500_bp = Blueprint('analisa_top500', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def get_active_period(cursor):
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else get_wib_time().strftime('%m-%Y')

# --- 1. GET TOP 500 DATA ---
@analisa_top500_bp.route('/top500', methods=['GET'])
def get_top_500():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode = get_active_period(cursor)
        
        # Query Mengambil Top 500 + Join ke Tabel Analisa (jika ada)
        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.rayon, p.pcez, 
                p.nominal, p.kubik, 
                COALESCE(a.keterangan, '-') as analisa,
                COALESCE(a.updated_by, '-') as auditor,
                COALESCE(r.petugas, 'UNMAPPED') as petugas_rute
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            LEFT JOIN analisa_tagihan a ON p.nomen = a.nomen AND p.periode = a.periode
            WHERE p.periode = ? 
            AND p.status_lunas = 0 
            AND p.rayon IN ('34', '35')
            AND p.nomen NOT IN (SELECT nomen FROM ardebt) -- Pastikan Murni Current
            ORDER BY p.nominal DESC 
            LIMIT 500
        """
        
        cursor.execute(query, (periode,))
        results = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            "status": "success", 
            "periode": periode,
            "data": results
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# --- 2. UPDATE KETERANGAN ANALISA ---
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
        
        # Buat tabel jika belum ada (Lazy Migration)
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
        
        # Cek apakah sudah ada analisa sebelumnya
        check = cursor.execute("SELECT id FROM analisa_tagihan WHERE nomen = ? AND periode = ?", (nomen, periode)).fetchone()
        
        tgl_skrg = get_wib_time().strftime('%Y-%m-%d %H:%M:%S')
        
        if check:
            cursor.execute("""
                UPDATE analisa_tagihan 
                SET keterangan = ?, updated_by = ?, updated_at = ? 
                WHERE nomen = ? AND periode = ?
            """, (keterangan, auditor, tgl_skrg, nomen, periode))
        else:
            cursor.execute("""
                INSERT INTO analisa_tagihan (nomen, periode, keterangan, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (nomen, periode, keterangan, auditor, tgl_skrg))
            
        conn.commit()
        return jsonify({"status": "success", "message": "Analisa tersimpan"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
