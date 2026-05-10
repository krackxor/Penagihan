from flask import Blueprint, render_template, request, jsonify
from models import db
from sqlalchemy import text
import os

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/database')
def database_page():
    """Menampilkan Halaman Khusus Manajemen Database."""
    return render_template('admin_db.html')

@admin_bp.route('/api/reset-database', methods=['POST'])
def reset_database():
    """
    Mesin Eksekusi Reset Data Sinergi V18.
    Mendukung dua mode: 'transaksi' (Operasional) dan 'total' (Pabrik).
    """
    mode = request.json.get('mode')
    
    try:
        if mode == 'transaksi':
            # 1. Mode Pembersihan Berkala (CID & Petugas AMAN)
            # Menghapus data operasional lapangan dan billing
            tabel_operasional = [
                'transaksi_tagihan', 
                'data_sbrs', 
                'data_mb', 
                'data_arrdebt', 
                'data_mainbill', 
                'analisa_auditor'
            ]
            
            # Eksekusi Truncate dengan CASCADE agar relasi FK ikut bersih
            for tabel in tabel_operasional:
                db.session.execute(text(f"TRUNCATE {tabel} RESTART IDENTITY CASCADE"))
            
            msg = "Data Transaksi, SBRS, MB, dan Laporan berhasil dikosongkan!"
            
        elif mode == 'total':
            # 2. Mode Reset Total (Setelan Pabrik)
            # Menghapus seluruh skema dan menciptakan ulang tabel kosong
            db.drop_all()
            db.create_all()
            msg = "Database Sinergi V18 telah direset total ke kondisi awal!"
            
        else:
            return jsonify({"status": "error", "message": "Mode reset tidak dikenal"}), 400
            
        db.session.commit()
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Kegagalan Sistem: {str(e)}"}), 500
