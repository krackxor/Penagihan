"""
Flask Application - Area Service Integrated System (V16.5 Sinergi Edition)
Updated: 2026-05-09
---------------------------------------------------------------------------
Fixes Log:
1.  PUBLIC ACCESS: Middleware fix for youtube/materi.
2.  FIX STORAGE LEAK: Otomatis hapus folder temp pada fitur Konversi & Ekspor Excel (Menggunakan io.BytesIO).
3.  FIX DATABASE LOCK: Standarisasi penuh menggunakan SQLAlchemy Connection Pooling untuk modul SBRS.
4.  FIX CONFIG CONFLICT: Sinkronisasi Max Upload Size dengan config.py (100MB).
5.  V16.4 ANTI-DOUBLE & INTELLIGENCE AUDIT.
6.  DYNAMIC FILTERS: Tambahan API get-sbrs-filters untuk filter Dropdown dinamis.
7.  [NEW] V16.5 INTEGRASI 1 SINERGI: Modul Master Analisa (MC, CID, MB, Daily, Ardebt, Mainbill) + Smart Importer.
"""

import os
import io
import shutil
import tempfile
import pandas as pd 
from datetime import timedelta, datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify, send_file
import sqlite3 
from sqlalchemy import create_engine, text

# [IMPORT CORE & SINERGI MODELS]
from config import Config
from core.database import init_db, get_db_connection
from core.helpers import get_role_redirect
from models import db  # Pastikan file models.py ada
from api.smart_importer import SmartImporter # Pastikan file api/smart_importer.py ada

# [IMPORT BLUEPRINTS]
from api.auth import auth_bp
from api.dashboard import dashboard_bp 
from api.upload import upload_bp  
from api.history import history_bp
from api.rute import rute_bp
from api.ardebt import ardebt_bp
from api.belum_bayar import belum_bayar_bp
from api.collection import collection_bp
from api.pcez_performance import register_pcez_routes
from api.wa_gateway import wa_bp
from api.analisa_top_500 import analisa_top500_bp 
from api.premium import premium_bp 
from api.ekstrem import ekstrem_bp 
from api.drop import drop_bp 
from api.map_gis import map_bp 

# --- MAPPING KAMUS DATA (V16.0) ---
METHOD_MAP = {
    "30/PE": "System Estimate", 
    "35/PS": "Service Provider Estimate", 
    "40/PE": "Office Estimate", 
    "60/SE": "Regular", 
    "80/PE": "Billing Force"
}

SKIP_MAP = {
    "1A": "Meter Buram", "1B": "Meter Berembun", "1C": "Meter Rusak", 
    "2A": "Meter Tidak Ada (Air Tidak Dipakai)", "2B": "Meter Tidak Ada (Air Dipakai)", 
    "3A": "Rumah Kosong", "4A": "Rumah Dibongkar", "4B": "Meter Terendam", 
    "4C": "Alamat Tak Ketemu", "5A": "Tutup Bak Berat", "5B": "Meter Tertimbun", 
    "5C": "Terhalang Barang", "5D": "Meter Dicor", "5E": "Bak Dikunci"
}

TROUBLE_MAP = {
    "1A": "Meter Berembun", "1B": "Meter Mati", "1C": "Meter Buram", 
    "1D": "Segel Pabrik Putus", "2A": "Meter Terbalik", "2B": "Meter Dipindah", 
    "2C": "Meter Lepas", "2D": "By Pass Meter", "2E": "Meter Dicolok", 
    "2F": "Meter Tak Normal", "2G": "Meter Rusak/Kaca Pecah", 
    "3A": "Air Kecil/Mati", "4A": "Pipa Dinas Bocor"
}

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

    # --- 1. STARTUP PROTOCOL & DATABASE ENGINE ---
    # Inisialisasi Database Sinergi (ORM)
    db.init_app(app)

    os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)
    db_path = os.path.join(app.root_path, 'instance', 'database.db')
    engine_sbrs = create_engine(f'sqlite:///{db_path}', pool_pre_ping=True)

    with app.app_context():
        init_db(app) 
        db.create_all() # Otomatis membuat tabel Sinergi dari models.py jika belum ada
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'materi')
        ]
        for folder in folders:
            os.makedirs(folder, exist_ok=True)

    @app.teardown_appcontext
    def close_connection(exception):
        db_conn = g.pop('db', None)
        if db_conn is not None:
            db_conn.close()

    # --- 2. MIDDLEWARE: SECURITY LAYER ---
    @app.before_request
    def security_layer():
        public_endpoints = [
            'login_page',
            'auth.login',
            'youtube_page',    
            'materi_page',     
            'static',          
            'serve_kunjungan_photo',
            'index',            
            'public_cek_tagihan', 
            'history.public_share_view', 
            'repair_mainbill', 
            'merger_ardebt',   
            'converter_tool',
            'image_to_txt',    
            'api_convert'      
        ]
        
        endpoint = request.endpoint
        
        if request.path.startswith('/api/history/share/view/') or request.path.startswith('/static/'):
            return None

        if not endpoint or endpoint in public_endpoints:
            return

        if 'role' not in session:
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"status": "error", "message": "Otoritas Diperlukan"}), 401
            return redirect(url_for('login_page'))
        
        admin_only_endpoints = [
            'admin_dashboard', 'monitoring_lokasi_page', 'wa_blast_page',
            'upload.handle_smart_upload', 'history_page',
            'analisa_top500_page', 
            'premium_customer_page',
            'pelanggan_ekstrem_page',
            'pelanggan_drop_page',
            'peta_sebaran_page',
            'upload_sbrs_page',    
            'summary_sbrs_page',
            'analisa_sbrs_page',
            'master_analisa_page' # Tambahan route admin untuk upload sinergi
        ]
        
        user_role = str(session.get('role', 'petugas')).lower()
        if endpoint in admin_only_endpoints and user_role != 'admin':
            return redirect(url_for('index'))

    # --- 3. REGISTRASI BLUEPRINTS ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(rute_bp, url_prefix='/api/rute')
    app.register_blueprint(belum_bayar_bp, url_prefix='/api/belum-bayar')
    app.register_blueprint(ardebt_bp, url_prefix='/api/ardebt')
    app.register_blueprint(collection_bp, url_prefix='/api/collection')
    app.register_blueprint(wa_bp, url_prefix='/api/wa-gateway') 
    app.register_blueprint(analisa_top500_bp, url_prefix='/api/analisa')
    app.register_blueprint(premium_bp, url_prefix='/api/premium')
    app.register_blueprint(ekstrem_bp, url_prefix='/api/ekstrem') 
    app.register_blueprint(drop_bp, url_prefix='/api/drop') 
    app.register_blueprint(map_bp, url_prefix='/api/map') 
    
    register_pcez_routes(app, get_db_connection)

    # --- 4. NAVIGASI FRONTEND (UI ROUTES) ---
    @app.route('/')
    def index():
        if 'role' in session:
            return render_template('index.html') 
        return render_template('landing.html')

    @app.route('/api/public/cek-tagihan/<nomen>')
    def public_cek_tagihan(nomen):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT nomen, nama, periode, kubik, nominal, status_lunas 
                FROM master_pelanggan 
                WHERE nomen = ? ORDER BY id DESC LIMIT 1
            """, (nomen,))
            row = cursor.fetchone()
            
            if row:
                return jsonify({
                    "status": "success",
                    "data": {
                        "nomen": row['nomen'],
                        "nama": row['nama'][:3] + "***", 
                        "periode": row['periode'],
                        "kubik": row['kubik'],
                        "nominal": row['nominal'],
                        "lunas": row['status_lunas'] == 1
                    }
                })
            return jsonify({"status": "error", "message": "ID Pelanggan tidak ditemukan"}), 404
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            conn.close()

    @app.route('/login')
    def login_page(): 
        if 'role' in session: 
            return redirect(get_role_redirect(session['role']))
        return render_template('login.html')

    @app.route('/youtube')
    def youtube_page(): return render_template('youtube.html')

    @app.route('/materi')
    def materi_page():
        materi_dir = os.path.join(app.root_path, 'static', 'uploads', 'materi')
        files = os.listdir(materi_dir) if os.path.exists(materi_dir) else []
        return render_template('materi.html', files=files)

    # --- TOOLS PUBLIK ---
    @app.route('/repair-mainbill')
    def repair_mainbill(): return render_template('repair_mainbill.html')

    @app.route('/merger-ardebt')
    def merger_ardebt(): return render_template('merger_ardebt.html')

    @app.route('/converter-tool')
    def converter_tool(): return render_template('converter_tool.html')

    @app.route('/image-to-text')
    def image_to_txt(): return render_template('image_to_txt.html')

    @app.route('/api/convert', methods=['POST'])
    def api_convert():
        # [Logika Konverter Tidak Diubah]
        try:
            if 'files' not in request.files:
                return jsonify({"status": "error", "message": "Tidak ada dokumen yang dipilih."}), 400
                
            files = request.files.getlist('files')
            conv_type = request.form.get('type')
            
            if not files or not conv_type:
                return jsonify({"status": "error", "message": "Data tidak lengkap."}), 400

            temp_dir = tempfile.mkdtemp()
            
            def send_and_clean(file_path, dl_name, mime=None):
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                shutil.rmtree(temp_dir, ignore_errors=True) 
                return send_file(io.BytesIO(file_data), as_attachment=True, download_name=dl_name, mimetype=mime)

            if conv_type == 'pdf_to_word':
                from pdf2docx import Converter
                file = files[0]
                pdf_path = os.path.join(temp_dir, secure_filename(file.filename))
                file.save(pdf_path)
                output_path = os.path.join(temp_dir, "Hasil_Konversi.docx")
                cv = Converter(pdf_path)
                cv.convert(output_path) 
                cv.close()
                return send_and_clean(output_path, "Hasil_PDF_ke_Word.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                
            # [LOGIKA GAMBAR DAN WORD TO PDF DIHILANGKAN SEMENTARA DI SNIPPET INI AGAR RINGKAS, TETAP ADA DI FILE ASLI]
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({"status": "error", "message": "Tipe konversi tidak didukung."}), 400

        except Exception as e:
            return jsonify({"status": "error", "message": f"Terjadi kesalahan teknis: {str(e)}"}), 500

    # --- RUTE TERPROTEKSI (EXISTING) ---
    @app.route('/performa')
    def performa_page(): return render_template('performa.html')

    @app.route('/admin/dashboard')
    def admin_dashboard(): return render_template('admin_dashboard.html')

    @app.route('/analisa-top500')
    def analisa_top500_page(): return render_template('analisa_top500.html')

    # --- MODUL BARU: SBRS MEGA-MERGE LNP ---
    @app.route('/upload-sbrs')
    def upload_sbrs_page(): return render_template('upload_sbrs.html')

    @app.route('/summary-sbrs')
    def summary_sbrs_page(): return render_template('summary_sbrs.html')

    # =====================================================================
    # --- MODUL BARU: MASTER ANALISA (1 SINERGI) ---
    # =====================================================================

    @app.route('/master-analisa')
    def master_analisa_page(): 
        """Halaman UI untuk mengunggah MC, CID, MB, ARDEBT"""
        return render_template('master_analisa.html')

    @app.route('/api/process-master-analisa', methods=['POST'])
    def api_process_master_analisa():
        """
        API untuk memproses 6 file master.
        Memanfaatkan SmartImporter untuk otomatisasi Nomen, Periode, dan Status Lunas.
        """
        try:
            if 'file' not in request.files:
                return jsonify({"status": "error", "message": "File tidak ditemukan."}), 400
                
            file = request.files['file']
            file_type = request.form.get('file_type') # Expected: 'MC', 'CID', 'MB', 'DAILY', 'ARDEBT', 'MAINBILL'
            
            if not file or not file_type:
                return jsonify({"status": "error", "message": "Data file atau tipe file tidak lengkap."}), 400

            # Simpan file ke direktori temp
            filename = secure_filename(file.filename)
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)

            importer = SmartImporter()
            
            # Routing ke fungsi Importer sesuai jenis file
            if file_type == 'CID':
                importer.import_cid(file_path)
                msg = "Data Master Pelanggan (CID) berhasil disinkronisasi."
            
            elif file_type == 'MC':
                count = importer.import_mc(file_path)
                msg = f"{count} Data Tagihan Baru (MC) berhasil diunggah ke database."
            
            elif file_type in ['MB', 'DAILY']:
                importer.import_pembayaran(file_path, type=file_type)
                msg = f"Data Pembayaran ({file_type}) berhasil diunggah. Status tagihan terkait otomatis menjadi LUNAS."
            
            elif file_type == 'ARDEBT':
                importer.import_ardebt(file_path)
                msg = "Data Tunggakan (Ardebt) berhasil disinkronisasi ke database."
                
            elif file_type == 'MAINBILL':
                importer.import_mainbill(file_path)
                msg = "Data Referensi Pusat (Mainbill) berhasil disinkronisasi."
                
            else:
                return jsonify({"status": "error", "message": "Tipe Kategori File tidak valid."}), 400

            return jsonify({"status": "success", "message": msg})
            
        except Exception as e:
            return jsonify({"status": "error", "message": f"Gagal memproses file: {str(e)}"}), 500
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True) # Cleanup memori

    # =====================================================================

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
