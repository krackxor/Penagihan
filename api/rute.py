from flask import Blueprint, request, jsonify
from core.database import get_db_connection

rute_bp = Blueprint('rute', __name__)

@rute_bp.route('/api/rute/list', methods=['GET'])
def get_rute_list():
    db = get_db_connection()
    try:
        # Mengambil semua PCEZ unik dari data MC yang sudah diupload
        query = """
            SELECT DISTINCT m.pcez, r.petugas 
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

@rute_bp.route('/api/rute/save', methods=['POST'])
def save_rute_manual():
    db = get_db_connection()
    pcez = request.form.get('pcez')
    petugas = request.form.get('petugas', '').strip().upper()
    try:
        db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", (pcez, petugas))
        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()
