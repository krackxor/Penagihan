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
    Dilengkapi Protokol Kill-Connections untuk mencegah error 'Database in use'.
    """
    # Gunakan request.form jika data dikirim dari htmx (default) atau request.json
    data = request.get_json() if request.is_json else request.form
    mode = data.get('mode')
    
    try:
        # --- LANGKAH 1: PROTOKOL PUTUS KONEKSI PAKSA ---
        # Ini akan menendang semua user/koneksi lain agar DB tidak terkunci (Lock)
        db.session.execute(text("""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = current_database()
              AND pid <> pg_backend_pid();
        """))
        db.session.commit()

        if mode == 'transaksi':
            # --- 2. MODE PEMBERSIHAN BERKALA ---
            tabel_operasional = [
                'transaksi_tagihan', 
                'data_sbrs', 
                'data_mb', 
                'data_arrdebt', 
                'data_mainbill', 
                'analisa_auditor'
            ]
            
            # Eksekusi Truncate per tabel (Hanya tabel operasional)
            for tabel in tabel_operasional:
                try:
                    db.session.execute(text(f"TRUNCATE {tabel} RESTART IDENTITY CASCADE"))
                except Exception:
                    continue # Lewati jika tabel belum ada/dibuat
            
            clear_upload_folder()
            msg = "Data Transaksi & Foto Laporan berhasil dikosongkan! (CID & Petugas AMAN)"
            
        elif mode == 'total':
            # --- 3. MODE RESET TOTAL (SETELAN PABRIK) ---
            # Drop dan Create All adalah cara tercepat membersihkan schema
            db.drop_all()
            db.create_all()
            
            clear_upload_folder()
            msg = "Database & Storage Sinergi V18 telah direset total ke kondisi awal!"
            
        else:
            return jsonify({"status": "error", "message": "Mode reset tidak dikenal"}), 400
            
        db.session.commit()
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        db.session.rollback()
        # Jika error karena tabel tidak ditemukan saat truncate, kirim pesan ramah
        return jsonify({"status": "error", "message": f"Kegagalan Sistem: {str(e)}"}), 500
