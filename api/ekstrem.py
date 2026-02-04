"""
Ekstrem Customer API - Sunter Dashboard Pro
File: api/ekstrem.py
Fungsi: Menangani Pelanggan dengan Lonjakan Tidak Wajar (>100%) untuk investigasi.
"""

from flask import Blueprint, jsonify, request, session
from core.database import get_db_connection
from datetime import datetime
import pytz

ekstrem_bp = Blueprint('ekstrem', __name__)

def get_wib_time():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def get_active_period(cursor):
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else get_wib_time().strftime('%m-%Y')

@ekstrem_bp.route('/list', methods=['GET'])
def get_ekstrem_customers():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Buat Tabel Analisa Ekstrem jika belum ada
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analisa_ekstrem (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nomen TEXT,
                periode TEXT,
                penyebab TEXT,
                tindakan TEXT,
                auditor TEXT,
                updated_at DATETIME
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

        # QUERY: Cari yang melonjak > 100% (2x Rata-rata) ATAU > 500m3
        query = """
            SELECT 
                p.nomen, p.nama, p.alamat, p.rayon, p.pcez, 
                p.nominal, p.kubik, 
                (SELECT ROUND(AVG(mp.kubik), 1) FROM master_pelanggan mp WHERE mp.nomen = p.nomen) as avg_hist,
                COALESCE(ae.penyebab, '-') as penyebab,
                COALESCE(ae.tindakan, '-') as tindakan,
                COALESCE(ae.auditor, '-') as auditor
            FROM master_pelanggan p
            LEFT JOIN analisa_ekstrem ae ON p.nomen = ae.nomen AND p.periode = ae.periode
            WHERE p.periode = ? 
            AND (
                p.kubik > 500 
                OR 
                (p.kubik > 20 AND p.kubik > (SELECT AVG(mp2.kubik)*2 FROM master_pelanggan mp2 WHERE mp2.nomen = p.nomen))
            )
            ORDER BY p.kubik DESC
        """
        
        cursor.execute(query, (periode,))
        rows = [dict(row) for row in cursor.fetchall()]
        
        # Hitung Persentase Kenaikan di Python
        processed = []
        for r in rows:
            avg = r['avg_hist'] if r['avg_hist'] else 1
            curr = r['kubik']
            r['persen_naik'] = int(((curr - avg) / avg) * 100) if avg > 0 else 0
            processed.append(r)

        return jsonify({
            "status": "success",
            "periode": periode,
            "data": processed
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@ekstrem_bp.route('/update', methods=['POST'])
def update_analisa_ekstrem():
    if session.get('role') != 'admin':
        return jsonify({"status": "error"}), 403
        
    nomen = request.form.get('nomen')
    penyebab = request.form.get('penyebab') # Dropdown
    tindakan = request.form.get('tindakan') # Textarea
    auditor = session.get('username', 'Admin')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        periode = get_active_period(cursor)
        tgl = get_wib_time().strftime('%Y-%m-%d %H:%M:%S')
        
        # Cek existing
        exist = cursor.execute("SELECT id FROM analisa_ekstrem WHERE nomen=? AND periode=?", (nomen, periode)).fetchone()
        
        if exist:
            cursor.execute("""
                UPDATE analisa_ekstrem 
                SET penyebab=?, tindakan=?, auditor=?, updated_at=? 
                WHERE nomen=? AND periode=?
            """, (penyebab, tindakan, auditor, tgl, nomen, periode))
        else:
            cursor.execute("""
                INSERT INTO analisa_ekstrem (nomen, periode, penyebab, tindakan, auditor, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nomen, periode, penyebab, tindakan, auditor, tgl))
            
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# ✅ NEW FUNCTION: GET HISTORY FOR POPUP
@ekstrem_bp.route('/history/<nomen>', methods=['GET'])
def get_ekstrem_history(nomen):
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Ambil 12 data terakhir (Periode, Kubik, Nominal, Status Lunas)
        query = """
            SELECT periode, kubik, nominal, status_lunas 
            FROM master_pelanggan 
            WHERE nomen = ? 
            ORDER BY id DESC 
            LIMIT 12
        """
        cursor.execute(query, (nomen,))
        rows = cursor.fetchall()
        
        history = []
        # Balik urutan agar di Grafik/Timeline urut dari Lama -> Baru
        for row in reversed(rows): 
            history.append({
                "periode": row['periode'], 
                "kubik": row['kubik'],
                "nominal": row['nominal'],
                "lunas": row['status_lunas']
            })
            
        return jsonify({"status": "success", "data": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()
