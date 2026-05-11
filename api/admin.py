import os
import shutil
from flask import Blueprint, render_template, request, jsonify, current_app
from models import db
from sqlalchemy import text

admin_bp = Blueprint('admin', __name__)

def clear_upload_folder():
    """Fungsi pembantu untuk membersihkan folder foto bukti kunjungan."""
    upload_path = current_app.config.get('UPLOAD_FOLDER')
    if upload_path and os.path.exists(upload_path):
        try:
            # Hapus isi folder tanpa menghapus folder utamanya
            for filename in os.listdir(upload_path):
                file_path = os.path.join(upload_path, filename)
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            return True
        except Exception as e:
            print(f"Gagal membersihkan folder upload: {e}")
    return False

@admin_bp.route('/database')
def database_page():
    """Menampilkan Halaman Khusus Manajemen Database."""
    return render_template('admin_db.html')

@admin_bp.route('/api/reset-database', methods=['POST'])
def reset_database():
    """
    Mesin Eksekusi Reset Data Sinergi V18.
    Mendukung dua mode: 'transaksi' (Operasional) dan 'total' (Pabrik).
    Kini otomatis membersihkan storage dari file foto sampah.
    """
    mode = request.json.get('mode')
    
    try:
        if mode == 'transaksi':
            # 1. Mode Pembersihan Berkala (Master CID & Petugas tetap Aman)
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
                # RESTART IDENTITY mengembalikan ID (Auto Increment) ke angka 1
                db.session.execute(text(f"TRUNCATE {tabel} RESTART IDENTITY CASCADE"))
            
            # Bersihkan foto bukti dari server
            clear_upload_folder()
            
            msg = "Data Transaksi & Foto Laporan berhasil dikosongkan! (CID & Petugas AMAN)"
            
        elif mode == 'total':
            # 2. Mode Reset Total (Setelan Pabrik)
            # Menghapus seluruh skema dan menciptakan ulang tabel kosong
            db.drop_all()
            db.create_all()
            
            # Bersihkan foto bukti dari server
            clear_upload_folder()
            
            msg = "Database & Storage Sinergi V18 telah direset total ke kondisi awal!"
            
        else:
            return jsonify({"status": "error", "message": "Mode reset tidak dikenal"}), 400
            
        db.session.commit()
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Kegagalan Sistem: {str(e)}"}), 500
