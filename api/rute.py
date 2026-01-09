"""
Rute API - Sunter Dashboard Pro
Sinergi:
1. Mapping PCEZ ke Petugas secara manual atau massal.
2. Integrasi No Admin WA untuk tembusan laporan otomatis.
3. Sinkronisasi otomatis dari master data pelanggan (MC).
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection

rute_bp = Blueprint('rute', __name__)

@rute_bp.route('/list', methods=['GET'])
def get_rute_list():
    """Mengambil semua daftar rute (PCEZ) dan mapping petugasnya."""
    db = get_db_connection()
    try:
        # Menampilkan PCEZ dari Master Pelanggan dan status petugasnya saat ini
        query = """
            SELECT DISTINCT m.pcez, r.petugas, r.no_admin,
            (SELECT COUNT(*) FROM master_pelanggan WHERE pcez = m.pcez AND tipe = 'MC') as jml_pelanggan
            FROM master_pelanggan m
            LEFT JOIN rute_petugas r ON m.pcez = r.pcez
            WHERE m.tipe = 'MC'
            ORDER BY m.pcez ASC
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@rute_bp.route('/save', methods=['POST'])
def save_rute_manual():
    """Simpan mapping petugas dan nomor admin per PCEZ (Individual)."""
    # Proteksi: Hanya admin yang boleh mengubah mapping
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    db = get_db_connection()
    pcez = request.form.get('pcez')
    petugas = request.form.get('petugas', '').strip().upper()
    no_admin = request.form.get('no_admin', '628123456789').strip() # Default No Admin
    
    try:
        db.execute("""
            INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (pcez, petugas, no_admin))
        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@rute_bp.route('/mass-update', methods=['POST'])
def mass_update_petugas():
    """Update banyak PCEZ sekaligus ke satu petugas (Fitur Cepat Admin)."""
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.get_json()
    pcez_list = data.get('pcez_list', []) # Array of pcez
    petugas = data.get('petugas', '').strip().upper()
    no_admin = data.get('no_admin', '628123456789').strip()

    if not pcez_list or not petugas:
        return jsonify({"status": "error", "message": "PCEZ atau Petugas kosong"}), 400

    db = get_db_connection()
    try:
        for pcez in pcez_list:
            db.execute("""
                INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (pcez, petugas, no_admin))
        db.commit()
        return jsonify({"status": "success", "message": f"{len(pcez_list)} rute berhasil diupdate."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()
