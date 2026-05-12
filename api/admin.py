import os
import shutil
from flask import Blueprint, render_template, request, jsonify, current_app
from models import db
from sqlalchemy import text

admin_bp = Blueprint('admin', __name__)

def clear_upload_folder():
    """Fungsi pembantu untuk membersihkan folder foto bukti kunjungan secara permanen."""
    upload_path = current_app.config.get('UPLOAD_FOLDER')
    if upload_path and os.path.exists(upload_path):
        try:
            # Iterasi isi folder untuk dihapus satu per satu
            for filename in os.listdir(upload_path):
                file_path = os.path.join(upload_path, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Gagal menghapus file {file_path}: {e}")
            return True
        except Exception as e:
            print(f"Gagal akses folder upload: {e}")
    return False

@admin_bp.route('/database')
def database_page():
    """Menampilkan Halaman Dashboard Kontrol Database."""
    return render_template('admin_db.html')

@admin_bp.route('/api/reset-database', methods=['POST'])
def reset_database():
    """
    Mesin Eksekusi Reset Data Sinergi V18.
    Dilengkapi Protokol 'Kill-All-Connections' untuk mencegah tabel terkunci (Locking).
    """
    # Deteksi kiriman data dari HTMX (Form) atau Fetch API (JSON)
    data = request.get_json() if request.is_json else request.form
    mode = data.get('mode')
    
    try:
        # --- LANGKAH 1: PROTOKOL PAKSA PUTUS KONEKSI ---
        # PostgreSQL sering menolak TRUNCATE/DROP jika ada sesi aktif (Adminer, HP Petugas, dll)
        db.session.execute(text("""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = current_database()
              AND pid <> pg_backend_pid();
        """))
        db.session.commit()

        if mode == 'transaksi':
            # --- 2. MODE PEMBERSIHAN OPERASIONAL (Bulanan) ---
            # Menghapus data kerja harian tanpa menyentuh Master Data Pelanggan
            tabel_operasional = [
                'transaksi_tagihan', 
                'data_sbrs', 
                'data_mb', 
                'data_arrdebt', 
                'data_mainbill', 
                'analisa_auditor'
            ]
            
            for tabel in tabel_operasional:
                try:
                    # RESTART IDENTITY mengembalikan penomoran ID otomatis ke angka 1
                    db.session.execute(text(f"TRUNCATE {tabel} RESTART IDENTITY CASCADE"))
                except Exception as ex:
                    print(f"Info: Tabel {tabel} dilewati (Mungkin belum dibuat): {ex}")
            
            clear_upload_folder()
            msg = "Data Transaksi & Storage berhasil dikosongkan! (Master CID & Petugas AMAN)"
            
        elif mode == 'total':
            # --- 3. MODE RESET TOTAL (Factory Reset) ---
            # Menghancurkan seluruh struktur tabel dan membangunnya kembali dari nol
            db.drop_all()
            db.create_all()
            
            clear_upload_folder()
            msg = "Sistem Sinergi V18 telah direset ke setelan pabrik! (Semua Data Hilang)"
            
        else:
            return jsonify({"status": "error", "message": "Protokol reset tidak dikenali"}), 400
            
        db.session.commit()
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        db.session.rollback()
        # Mengembalikan pesan error yang jelas jika terjadi kegagalan PostgreSQL
        return jsonify({
            "status": "error", 
            "message": f"Kegagalan Protokol: {str(e)}"
        }), 500
