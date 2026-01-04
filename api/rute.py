from flask import Blueprint, request, jsonify
from core.database import get_db_connection

rute_bp = Blueprint('rute', __name__)

@rute_bp.route('/api/rute/list', methods=['GET'])
def get_rute_list():
    """Mengambil semua PCEZ unik dari MC dan status petugasnya"""
    db = get_db_connection()
    try:
        # Query ini mengambil semua PCEZ yang ada di data MC (master_pelanggan)
        # Dan menggabungkannya dengan tabel rute_petugas (mapping manual)
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
    """Menyimpan atau mengupdate nama petugas untuk PCEZ tertentu"""
    db = get_db_connection()
    pcez = request.form.get('pcez')
    petugas = request.form.get('petugas').upper() # Simpan dengan huruf besar
    
    try:
        db.execute("INSERT OR REPLACE INTO rute_petugas (pcez, petugas) VALUES (?, ?)", 
                   (pcez, petugas))
        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@rute_bp.route('/api/rute/delete', methods=['DELETE'])
def delete_rute_manual():
    """Menghapus mapping petugas pada PCEZ tertentu"""
    db = get_db_connection()
    pcez = request.args.get('pcez')
    try:
        db.execute("DELETE FROM rute_petugas WHERE pcez = ?", (pcez,))
        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()
