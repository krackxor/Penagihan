"""
Flask Application - Area Service Integrated System (V16.1 Full Anti-Double, Audit Engine & Stability Patch)
Updated: 2026-05-09
---------------------------------------------------------------------------
Fixes Log:
1.  ✅ PUBLIC ACCESS: Middleware fix for youtube/materi.
2.  ✅ FIX STORAGE LEAK: Otomatis hapus folder temp pada fitur Konversi & Ekspor Excel (Menggunakan io.BytesIO).
3.  ✅ FIX DATABASE LOCK: Standarisasi penuh menggunakan SQLAlchemy Connection Pooling untuk modul SBRS.
4.  ✅ FIX CONFIG CONFLICT: Sinkronisasi Max Upload Size dengan config.py (100MB).
5.  ✅ V16.1 ANTI-DOUBLE & INTELLIGENCE AUDIT (Zero Baru/Lama, Ekstrim Hybrid, Split Analisa).
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

# [IMPORT CORE]
from config import Config
from core.database import init_db, get_db_connection
from core.helpers import get_role_redirect

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
    # Inisialisasi engine SBRS sekali di awal agar Connection Pooling SQLAlchemy bekerja sempurna (Mencegah Database Locked)
    os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)
    db_path = os.path.join(app.root_path, 'instance', 'database.db')
    engine_sbrs = create_engine(f'sqlite:///{db_path}', pool_pre_ping=True)

    with app.app_context():
        init_db(app) 
        folders = [
            os.path.join(app.root_path, 'static', 'uploads', 'kunjungan'),
            os.path.join(app.root_path, 'static', 'uploads', 'materi')
        ]
        for folder in folders:
            os.makedirs(folder, exist_ok=True)

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

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
            'analisa_sbrs_page'    
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
    def youtube_page():
        return render_template('youtube.html')

    @app.route('/materi')
    def materi_page():
        materi_dir = os.path.join(app.root_path, 'static', 'uploads', 'materi')
        files = os.listdir(materi_dir) if os.path.exists(materi_dir) else []
        return render_template('materi.html', files=files)

    # --- TOOLS PUBLIK ---
    @app.route('/repair-mainbill')
    def repair_mainbill():
        return render_template('repair_mainbill.html')

    @app.route('/merger-ardebt')
    def merger_ardebt():
        return render_template('merger_ardebt.html')

    @app.route('/converter-tool')
    def converter_tool():
        return render_template('converter_tool.html')

    @app.route('/image-to-text')
    def image_to_txt():
        return render_template('image_to_txt.html')

    @app.route('/api/convert', methods=['POST'])
    def api_convert():
        try:
            if 'files' not in request.files:
                return jsonify({"status": "error", "message": "Tidak ada dokumen yang dipilih."}), 400
                
            files = request.files.getlist('files')
            conv_type = request.form.get('type')
            
            if not files or not conv_type:
                return jsonify({"status": "error", "message": "Data tidak lengkap."}), 400

            temp_dir = tempfile.mkdtemp()
            
            # --- FIX STORAGE LEAK: Fungsi Helper Pengiriman File ---
            def send_and_clean(file_path, dl_name, mime=None):
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                shutil.rmtree(temp_dir, ignore_errors=True) # Menghapus sampah konversi seketika
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
                
            elif conv_type == 'img_to_pdf':
                from PIL import Image
                image_list = []
                for file in files:
                    img_path = os.path.join(temp_dir, secure_filename(file.filename))
                    file.save(img_path)
                    img = Image.open(img_path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    image_list.append(img)
                if image_list:
                    output_path = os.path.join(temp_dir, "Hasil_Gabungan.pdf")
                    image_list[0].save(output_path, save_all=True, append_images=image_list[1:])
                    return send_and_clean(output_path, "Hasil_Gambar_ke_PDF.pdf", "application/pdf")

            elif conv_type == 'word_to_pdf':
                import subprocess
                file = files[0]
                docx_path = os.path.join(temp_dir, secure_filename(file.filename))
                file.save(docx_path)
                output_path = os.path.join(temp_dir, "Hasil_Konversi.pdf")
                try:
                    from docx2pdf import convert
                    convert(docx_path, output_path)
                    if os.path.exists(output_path):
                        return send_and_clean(output_path, "Hasil_Word_ke_PDF.pdf", "application/pdf")
                except Exception:
                    pass 
                try:
                    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', docx_path, '--outdir', temp_dir], check=True)
                    base_name = os.path.splitext(os.path.basename(docx_path))[0]
                    libre_output_path = os.path.join(temp_dir, f"{base_name}.pdf")
                    if os.path.exists(libre_output_path):
                        return send_and_clean(libre_output_path, "Hasil_Word_ke_PDF.pdf", "application/pdf")
                    else:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return jsonify({"status": "error", "message": "Gagal merender PDF dari file Word tersebut."}), 500
                except FileNotFoundError:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return jsonify({"status": "error", "message": "Server tidak memiliki MS Word atau LibreOffice."}), 500

            elif conv_type == 'img_to_txt':
                try:
                    import pytesseract
                    from PIL import Image
                    file = files[0]
                    img_path = os.path.join(temp_dir, secure_filename(file.filename))
                    file.save(img_path)
                    ocr_lang = request.form.get('lang', 'ind+eng')
                    extracted_text = pytesseract.image_to_string(Image.open(img_path), lang=ocr_lang)
                    output_path = os.path.join(temp_dir, "Hasil_Ekstraksi.txt")
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(extracted_text)
                    return send_and_clean(output_path, "Hasil_Teks_OCR.txt", "text/plain")
                except Exception as e:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return jsonify({"status": "error", "message": "Pastikan bahasa yang dipilih sudah terinstal di server."}), 500

            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({"status": "error", "message": "Tipe konversi tidak didukung."}), 400

        except Exception as e:
            return jsonify({"status": "error", "message": f"Terjadi kesalahan teknis: {str(e)}"}), 500

    # --- RUTE TERPROTEKSI (EXISTING) ---
    @app.route('/performa')
    def performa_page(): return render_template('performa.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): return render_template('monitoring_collection.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): return render_template('belum_bayar.html')

    @app.route('/tagihan-berekor')
    def ardebt_page(): return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): return render_template('janji_bayar.html')

    @app.route('/galeri')
    def galeri_page(): return render_template('galeri.html')

    @app.route('/history-bayar')
    def history_bayar_page(): return render_template('history_bayar.html')

    @app.route('/history-kunjungan')
    def history_kunjungan_page(): return render_template('history_kunjungan.html')

    @app.route('/admin/dashboard')
    def admin_dashboard(): return render_template('admin_dashboard.html')

    @app.route('/monitoring-lokasi')
    def monitoring_lokasi_page(): return render_template('monitoring_lokasi.html')

    @app.route('/wa-blast')
    def wa_blast_page(): return render_template('wa_blast.html')

    @app.route('/history')
    def history_page(): return render_template('history.html')

    @app.route('/analisa-top500')
    def analisa_top500_page(): return render_template('analisa_top500.html')

    @app.route('/premium-customer')
    def premium_customer_page(): return render_template('premium_customer.html')

    @app.route('/pelanggan-ekstrem')
    def pelanggan_ekstrem_page(): return render_template('pelanggan_ekstrem.html')

    @app.route('/pelanggan-drop')
    def pelanggan_drop_page(): return render_template('pelanggan_drop.html')

    @app.route('/peta-sebaran')
    def peta_sebaran_page(): return render_template('peta_sebaran.html')

    # --- MODUL BARU: SBRS MEGA-MERGE LNP (V16.1 SQLALCHEMY STANDARDIZED) ---
    @app.route('/upload-sbrs')
    def upload_sbrs_page(): return render_template('upload_sbrs.html')

    @app.route('/summary-sbrs')
    def summary_sbrs_page(): return render_template('summary_sbrs.html')

    @app.route('/analisa-sbrs')
    def analisa_sbrs_page(): return render_template('analisa_sbrs.html')

    @app.route('/api/process-sbrs', methods=['POST'])
    def api_process_sbrs():
        try:
            if 'fileCust' not in request.files or 'fileSpot' not in request.files:
                return jsonify({"status": "error", "message": "File Customer dan Spot Bill harus diunggah lengkap."}), 400

            file_cust = request.files['fileCust']
            file_spot = request.files['fileSpot']

            df_cust = pd.read_csv(file_cust, sep=';', dtype=str, on_bad_lines='skip')
            df_spot = pd.read_csv(file_spot, sep=';', dtype=str, on_bad_lines='skip')

            df_cust.columns = df_cust.columns.str.strip()
            df_spot.columns = df_spot.columns.str.strip()

            # 1. MEGA-MERGE BERDASARKAN ID
            df_final = pd.merge(df_cust, df_spot, left_on='cmr_account', right_on='Nomen', how='inner')

            # 2. ANTI-DOUBLE (CLEANING DUPLIKAT DI FILE CSV)
            if 'cmr_account' in df_final.columns:
                df_final.drop_duplicates(subset=['cmr_account'], keep='last', inplace=True)

            # 3. AUTO-DETECT CYCLE & PERIODE DARI FILE
            if 'cmr_cycle' in df_final.columns:
                cycle_terdeteksi = str(df_final['cmr_cycle'].mode()[0]).strip()
                cycle_input = cycle_terdeteksi.zfill(2)
            else:
                cycle_input = "Unknown"

            if 'cmr_rd_date' in df_final.columns:
                tanggal_terdeteksi = str(df_final['cmr_rd_date'].mode()[0]).strip()
                if len(tanggal_terdeteksi) == 8:
                    bulan = tanggal_terdeteksi[2:4] 
                    tahun = tanggal_terdeteksi[4:8] 
                    periode_otomatis = f"{tahun}-{bulan}" 
                else:
                    periode_otomatis = datetime.now().strftime('%Y-%m')
            else:
                periode_otomatis = datetime.now().strftime('%Y-%m')
            
            df_final['cmr_cycle'] = cycle_input
            df_final['periode_sbrs'] = periode_otomatis

            # 4. KONVERSI TIPE DATA
            kolom_numerik = ['cmr_reading', 'cmr_prev_read', 'Curr_Read_1', 'Prev_Read_1', 'SB_Stand']
            for col in kolom_numerik:
                if col in df_final.columns:
                    df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)

            # 5. TERAPKAN PENAMAAN LNP & PERHITUNGAN
            if 'cmr_reading' in df_final.columns and 'cmr_prev_read' in df_final.columns:
                df_final['Vol_Lap'] = df_final['cmr_reading'] - df_final['cmr_prev_read']
            
            if 'Curr_Read_1' in df_final.columns and 'Prev_Read_1' in df_final.columns:
                df_final['Vol_Bill'] = df_final['Curr_Read_1'] - df_final['Prev_Read_1']
                
            if 'SB_Stand' in df_final.columns and 'Prev_Read_1' in df_final.columns:
                df_final['Vol_SB'] = df_final['SB_Stand'] - df_final['Prev_Read_1']

            if 'Vol_Lap' in df_final.columns:
                df_final['Vol_Riil'] = df_final['Vol_Lap'] 
            df_final['Selisih_HB'] = 31 

            # 6. SIMPAN HASIL KE DATABASE SQLITE MENGGUNAKAN GLOBAL ENGINE
            with engine_sbrs.begin() as conn:
                try:
                    conn.execute(text(f"DELETE FROM history_lnp WHERE cmr_cycle = '{cycle_input}' AND periode_sbrs = '{periode_otomatis}'"))
                except Exception:
                    pass 

            df_final.to_sql('history_lnp', con=engine_sbrs, if_exists='append', index=False)

            return jsonify({
                "status": "success", 
                "message": f"Data Periode {periode_otomatis} Cycle {cycle_input} berhasil digabung & bersih dari duplikat!",
                "total_rows": len(df_final)
            })

        except Exception as e:
            return jsonify({"status": "error", "message": f"Gagal memproses file: {str(e)}"}), 500

    # --- API SBRS: GET SUMMARY (INTELLIGENCE AUDIT) ---
    @app.route('/api/get-summary-sbrs', methods=['GET'])
    def get_summary_sbrs():
        cycle = request.args.get('cycle', 'all')
        sort_by = request.args.get('sort_by', 'ROWID')
        order = request.args.get('order', 'DESC')
        status_filter = request.args.get('filter', 'all')

        try:
            with engine_sbrs.connect() as conn:
                # Pastikan tabel sudah ada
                check = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='history_lnp'")).fetchone()
                if not check:
                    return jsonify({
                        "status": "success", "summary": {"total_objek": 0, "total_vol_sb": 0}, 
                        "stats": {"zero_baru":0,"zero_lama":0,"ekstrim":0,"turun":0,"anomali":0},
                        "skip": [], "trouble": [], "methods": [], "master": []
                    })

                query = "SELECT ROWID as rowid, * FROM history_lnp"
                params = {}
                if cycle != 'all':
                    query += " WHERE cmr_cycle = :cycle"
                    params['cycle'] = cycle
                query += f" ORDER BY {sort_by} {order}"
                
                rows = conn.execute(text(query), params).mappings().all()

            master_data = []
            stats = {"zero_baru": 0, "zero_lama": 0, "ekstrim": 0, "anomali": 0, "turun": 0}
            skip_count, trbl_count, meth_count = {}, {}, {}
            total_vol_sb = 0

            for d in rows:
                # Tangkap kolom fleksibel
                col_nomen = d.get('Nomen', d.get('cmr_account', '-'))
                col_nama = d.get('cmr_nama', d.get('Nama', 'Pelanggan'))

                # Ambil Kode Analisa
                s_raw = str(d.get('cmr_skip_code', '0')).strip().upper()
                t_raw = str(d.get('cmr_trbl1_code', '0')).strip().upper()
                
                # Baca metode & pesan dari header
                m_raw = str(d.get('Read_Method', d.get('cmr_read_method', '-'))).strip()
                spcl_msg = str(d.get('cmr_chg_spcl_msg', '-')).strip()

                if s_raw not in ['0', 'NAN', '', 'NONE']: skip_count[s_raw] = skip_count.get(s_raw, 0) + 1
                if t_raw not in ['0', 'NAN', '', 'NONE']: trbl_count[t_raw] = trbl_count.get(t_raw, 0) + 1
                if m_raw != '-': meth_count[m_raw] = meth_count.get(m_raw, 0) + 1

                # Audit Volume Logics
                v_lap, v_bill, v_sb = float(d.get('Vol_Lap', 0)), float(d.get('Vol_Bill', 0)), float(d.get('Vol_SB', 0))
                v_gap, sb_gap = (v_bill - v_lap), (v_sb - v_lap)
                selisih_naik = v_lap - v_bill
                pct_naik = (selisih_naik / v_bill * 100) if v_bill > 0 else 0
                
                tags = []
                
                # Zero Split Logic
                if v_lap == 0:
                    if v_bill > 0: 
                        tags.append("Zero Baru")
                        stats["zero_baru"] += 1
                    else: 
                        tags.append("Zero Lama")
                        stats["zero_lama"] += 1
                
                # Ekstrim Hybrid Logic (Naik >100% ATAU Naik >50m3 mutlak)
                if (v_lap > 10 and pct_naik >= 100) or (selisih_naik >= 50):
                    tags.append("Ekstrim")
                    stats["ekstrim"] += 1
                
                if 0 < v_lap < (v_bill * 0.4): 
                    tags.append("Turun")
                    stats["turun"] += 1
                    
                if v_gap != 0 or sb_gap != 0: 
                    tags.append("Anomali")
                    stats["anomali"] += 1
                
                # Filter Matching
                match = True
                if status_filter == 'ekstrem' and "Ekstrim" not in tags and "Anomali" not in tags: match = False
                elif status_filter == 'turun' and "Turun" not in tags: match = False
                elif status_filter == 'zero_baru' and "Zero Baru" not in tags: match = False
                elif status_filter == 'zero_lama' and "Zero Lama" not in tags: match = False
                elif status_filter == 'anomali' and "Anomali" not in tags: match = False
                elif status_filter == 'skip' and s_raw in ['0', 'NAN', '', 'NONE']: match = False
                elif status_filter == 'trouble' and t_raw in ['0', 'NAN', '', 'NONE']: match = False

                if match:
                    total_vol_sb += v_sb
                    master_data.append({
                        "rowid": d['rowid'], "nomen": col_nomen, "nama": col_nama,
                        "vol_lap": v_lap, "vol_bill": v_bill, "vol_sb": v_sb, "v_gap": v_gap, "sb_gap": sb_gap,
                        "status": " / ".join(tags) if tags else "Normal",
                        "method": m_raw, "method_full": METHOD_MAP.get(m_raw, m_raw),
                        "spcl_msg": spcl_msg, "hb": d.get('Selisih_HB', 31), "vol_riil": d.get('Vol_Riil', v_lap)
                    })

            return jsonify({
                "status": "success",
                "summary": {"total_objek": len(rows), "total_vol_sb": total_vol_sb},
                "stats": stats,
                "skip": [{"kode": k, "ket": SKIP_MAP.get(k, "Lain-lain"), "jml": v} for k, v in skip_count.items()],
                "trouble": [{"kode": k, "ket": TROUBLE_MAP.get(k, "Lain-lain"), "jml": v} for k, v in trbl_count.items()],
                "methods": [{"kode": k, "ket": METHOD_MAP.get(k, k), "jml": v} for k, v in meth_count.items()],
                "master": master_data[:1000] 
            })

        except Exception as e:
            return jsonify({"status": "error", "message": f"Terjadi Kesalahan SQL: {str(e)}"})

    # --- API SBRS: EDIT & DOWNLOAD (STABILITY PATCHED) ---
    @app.route('/api/edit-sbrs', methods=['POST'])
    def edit_sbrs():
        try:
            d = request.json
            with engine_sbrs.begin() as conn:
                conn.execute(text("UPDATE history_lnp SET Vol_Lap=:lap, Vol_Bill=:bill, Vol_SB=:sb, Vol_Riil=:riil, Selisih_HB=:hb WHERE ROWID=:rowid"),
                             {"lap": d['vol_lap'], "bill": d['vol_bill'], "sb": d['vol_sb'], "riil": d['vol_riil'], "hb": d.get('hb', 31), "rowid": d['rowid']})
            return jsonify({"status": "success"})
        except Exception as e: 
            return jsonify({"status": "error", "message": str(e)})

    @app.route('/api/download-sbrs-excel', methods=['GET'])
    def download_sbrs_excel():
        cycle = request.args.get('cycle', 'all')
        try:
            with engine_sbrs.connect() as conn:
                query = "SELECT * FROM history_lnp"
                if cycle != 'all':
                    query += f" WHERE cmr_cycle = '{cycle}'"
                    
                df = pd.read_sql_query(query, conn)
                
            if df.empty:
                return "Data tidak ditemukan untuk diekspor", 404

            # --- FIX STORAGE LEAK: Gunakan Memori BytesIO & Langsung Hapus Temp ---
            temp_dir = tempfile.mkdtemp()
            output_path = os.path.join(temp_dir, f"Laporan_SBRS_Cycle_{cycle}.xlsx")
            df.to_excel(output_path, index=False)
            
            with open(output_path, 'rb') as f:
                file_data = f.read()
            shutil.rmtree(temp_dir, ignore_errors=True) # Hapus sampah seketika
            
            return send_file(io.BytesIO(file_data), as_attachment=True, download_name=f"Laporan_SBRS_Cycle_{cycle}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
        except Exception as e:
            return f"Terjadi kesalahan saat membuat Excel: {str(e)}", 500

    @app.route('/static/uploads/kunjungan/<filename>')
    def serve_kunjungan_photo(filename):
        folder = os.path.join(app.root_path, 'static', 'uploads', 'kunjungan')
        return send_from_directory(folder, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
