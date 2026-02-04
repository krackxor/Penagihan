"""
Drop Usage Customer API - Sunter Dashboard Pro
File: api/drop.py
Fungsi: Menangani Pelanggan dengan Penurunan Pemakaian Drastis (>50%) atau 0 m3.
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime
import pytz

drop_bp = Blueprint('drop', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def get_active_period(cursor):
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else get_wib_time().strftime('%m-%Y')

@drop_bp.route('/list', methods=['GET'])
def get_drop_customers():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Buat Tabel Analisa Drop jika belum ada
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analisa_drop (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nomen TEXT, periode TEXT, penyebab TEXT, tindakan TEXT, auditor TEXT, updated_at DATETIME
            )
        """)
        conn.commit()

        req_periode = request.args.get('periode')
        if req_periode:
            try:
                parts = req_periode.split('-')
                periode = f"{parts[1]}-{parts[0]}"
            except:
                periode = get_active_period(cursor)
        else:
            periode = get_active_period(cursor)

        # QUERY: Cari yang Anjlok > 50% ATAU Jadi 0 m3 (Padahal biasanya aktif > 10m3)
        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.rayon, p.pcez, 
                p.nominal, p.kubik, 
                (SELECT ROUND(AVG(mp.kubik), 1) FROM master_pelanggan mp WHERE mp.nomen = p.nomen) as avg_hist,
                COALESCE(ad.penyebab, '-') as penyebab,
                COALESCE(ad.tindakan, '-') as tindakan
            FROM master_pelanggan p
            LEFT JOIN analisa_drop ad ON p.nomen = ad.nomen AND p.periode = ad.periode
            WHERE p.periode = ? 
            AND (
                -- Syarat 1: Kubik jadi 0, padahal rata-rata > 5 (Indikasi Meter Macet/Rumah Kosong)
                (p.kubik = 0 AND (SELECT AVG(mp2.kubik) FROM master_pelanggan mp2 WHERE mp2.nomen = p.nomen) > 5)
                OR 
                -- Syarat 2: Kubik turun dibawah 50% rata-rata (Drop Drastis)
                (p.kubik < ((SELECT AVG(mp3.kubik) FROM master_pelanggan mp3 WHERE mp3.nomen = p.nomen) * 0.5))
            )
            ORDER BY p.kubik ASC -- Urutkan dari yang terkecil (0)
        """
        
        cursor.execute(query, (periode,))
        rows = [dict(row) for row in cursor.fetchall()]
        
        # Hitung Persentase Penurunan
        processed = []
        for r in rows:
            avg = r['avg_hist'] if r['avg_hist'] else 0.1 # Hindari division by zero
            curr = r['kubik']
            
            # Hitung % Turun
            if avg > 0:
                persen = int(((avg - curr) / avg) * 100)
            else:
                persen = 0
                
            r['persen_turun'] = persen
            processed.append(r)

        return jsonify({"status": "success", "periode": periode, "data": processed})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@drop_bp.route('/update', methods=['POST'])
def update_analisa_drop():
    if session.get('role') != 'admin':
        return jsonify({"status": "error"}), 403
    
    nomen = request.form.get('nomen')
    penyebab = request.form.get('penyebab')
    tindakan = request.form.get('tindakan')
    auditor = session.get('username', 'Admin')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode = get_active_period(cursor)
        tgl = get_wib_time().strftime('%Y-%m-%d %H:%M:%S')
        
        exist = cursor.execute("SELECT id FROM analisa_drop WHERE nomen=? AND periode=?", (nomen, periode)).fetchone()
        if exist:
            cursor.execute("UPDATE analisa_drop SET penyebab=?, tindakan=?, auditor=?, updated_at=? WHERE nomen=? AND periode=?", (penyebab, tindakan, auditor, tgl, nomen, periode))
        else:
            cursor.execute("INSERT INTO analisa_drop (nomen, periode, penyebab, tindakan, auditor, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (nomen, periode, penyebab, tindakan, auditor, tgl))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# HISTORY ENDPOINT (Sama seperti Ekstrem/Premium)
@drop_bp.route('/history/<nomen>', methods=['GET'])
def get_drop_history(nomen):
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 403
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT periode, kubik, nominal, status_lunas 
            FROM master_pelanggan WHERE nomen = ? 
            ORDER BY id DESC LIMIT 12
        """
        cursor.execute(query, (nomen,))
        rows = cursor.fetchall()
        history = []
        for row in reversed(rows): 
            history.append({
                "periode": row['periode'], "kubik": row['kubik'], 
                "nominal": row['nominal'], "lunas": row['status_lunas']
            })
        return jsonify({"status": "success", "data": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
