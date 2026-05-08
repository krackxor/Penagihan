"""
Flask Application - Area Service Integrated System (V13.9 Converter & SBRS Engine)
Updated: 2026-05-09
---------------------------------------------------------------------------
Fixes Log:
1.  ✅ PUBLIC ACCESS: Middleware fix for youtube/materi.
2.  ✅ FIX 413: Max upload size 64MB.
3.  ✅ WA SHARE LINK: Public access allowed.
4.  ✅ ANALISA PARETO: Modul Top 500 Admin.
5.  ✅ PREMIUM CUSTOMER: Modul Monitoring Pelanggan > 75m3 (Stabil).
6.  ✅ PELANGGAN EKSTREM: Modul Investigasi Lonjakan > 100%.
7.  ✅ PELANGGAN DROP: Modul Investigasi Penurunan > 50%.
8.  ✅ GIS MAPPING: Peta Sebaran Anomali & Tagging Lokasi.
9.  ✅ LANDING PAGE: Halaman Publik Cek Tagihan (Secure).
10. ✅ TOOLS: Repair Mainbill Tool untuk akses publik tanpa login.
11. ✅ TOOLS: Merger Ardebt Tool untuk penggabungan banyak file TXT.
12. ✅ TOOLS: Konversi Dokumen (ACTIVE ENGINE) - pdf2docx, Pillow, & LibreOffice.
13. ✅ TOOLS: OCR Gambar ke Teks Multi-Bahasa.
14. ✅ SBRS MEGA-MERGE: Modul Upload & Summary LNP dengan Auto-Detect Cycle & Periode.
15. ✅ API SBRS: Tambahan API Get-Summary (Bulletproof ROWID) & Download Excel LNP.
"""

import os
import tempfile
import pandas as pd 
from datetime import timedelta, datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, g, send_from_directory, session, redirect, url_for, request, jsonify, send_file
import sqlite3 # Tambahan untuk query manual

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

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
    
    # --- FIX 413 ERROR: Konfigurasi Batas Unggahan (64 Megabyte) ---
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024 

    # --- 1. STARTUP PROTOCOL ---
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
            'upload_sbrs_page',    # Proteksi Modul SBRS LNP
            'summary_sbrs_page'    # Proteksi Modul SBRS LNP
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
            
            if conv_type == 'pdf_to_word':
                from pdf2docx import Converter
                file = files[0]
                pdf_path = os.path.join(temp_dir, secure_filename(file.filename))
                file.save(pdf_path)
                output_path = os.path.join(temp_dir, "Hasil_Konversi.docx")
                cv = Converter(pdf_path)
                cv.convert(output_path) 
                cv.close()
                return send_file(output_path, as_attachment=True, download_name="Hasil_PDF_ke_Word.docx")
                
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
                    return send_file(output_path, as_attachment=True, download_name="Hasil_Gambar_ke_PDF.pdf")

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
                        return send_file(output_path, as_attachment=True, download_name="Hasil_Word_ke_PDF.pdf")
                except Exception:
                    pass 
                try:
                    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', docx_path, '--outdir', temp_dir], check=True)
                    base_name = os.path.splitext(os.path.basename(docx_path))[0]
                    libre_output_path = os.path.join(temp_dir, f"{base_name}.pdf")
                    if os.path.exists(libre_output_path):
                        return send_file(libre_output_path, as_attachment=True, download_name="Hasil_Word_ke_PDF.pdf")
                    else:
                        return jsonify({"status": "error", "message": "Gagal merender PDF dari file Word tersebut."}), 500
                except FileNotFoundError:
                    return jsonify({
                        "status": "error", 
                        "message": "Server tidak memiliki MS Word atau LibreOffice."
                    }), 500

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
                    return send_file(output_path, as_attachment=True, download_name="Hasil_Teks_OCR.txt")
                except Exception as e:
                    return jsonify({
                        "status": "error", 
                        "message": "Pastikan bahasa yang dipilih sudah terinstal di server."
                    }), 500

            return jsonify({"status": "error", "message": "Tipe konversi tidak didukung."}), 400

        except Exception as e:
            return jsonify({"status": "error", "message": f"Terjadi kesalahan teknis: {str(e)}"}), 500

    # --- RUTE TERPROTEKSI (EXISTING) ---
    @app.route('/performa')
    def performa_page(): 
        return render_template('performa.html')

    @app.route('/monitoring-collection')
    def monitoring_collection_page(): 
        return render_template('monitoring_collection.html')

    @app.route('/belum-bayar')
    def belum_bayar_page(): 
        return render_template('belum_bayar.html')

    @app.route('/tagihan-berekor')
    def ardebt_page(): 
        return render_template('tagihan_berekor.html')

    @app.route('/janji-bayar')
    def janji_bayar_page(): 
        return render_template('janji_bayar.html')

    @app.route('/galeri')
    def galeri_page():
        return render_template('galeri.html')

    @app.route('/history-bayar')
    def history_bayar_page(): 
        return render_template('history_bayar.html')

    @app.route('/history-kunjungan')
    def history_kunjungan_page(): 
        return render_template('history_kunjungan.html')

    @app.route('/admin/dashboard')
    def admin_dashboard(): 
        return render_template('admin_dashboard.html')

    @app.route('/monitoring-lokasi')
    def monitoring_lokasi_page():
        return render_template('monitoring_lokasi.html')

    @app.route('/wa-blast')
    def wa_blast_page():
        return render_template('wa_blast.html')

    @app.route('/history')
    def history_page(): 
        return render_template('history.html')

    @app.route('/analisa-top500')
    def analisa_top500_page():
        return render_template('analisa_top500.html')

    @app.route('/premium-customer')
    def premium_customer_page():
        return render_template('premium_customer.html')

    @app.route('/pelanggan-ekstrem')
    def pelanggan_ekstrem_page():
        return render_template('pelanggan_ekstrem.html')

    @app.route('/pelanggan-drop')
    def pelanggan_drop_page():
        return render_template('pelanggan_drop.html')

    @app.route('/peta-sebaran')
    def peta_sebaran_page():
        return render_template('peta_sebaran.html')

    # --- MODUL BARU: SBRS MEGA-MERGE LNP ---
    @app.route('/upload-sbrs')
    def upload_sbrs_page():
        return render_template('upload_sbrs.html')

    @app.route('/summary-sbrs')
    def summary_sbrs_page():
        return render_template('summary_sbrs.html')

    @app.route('/api/process-sbrs', methods=['POST'])
    def api_process_sbrs():
        try:
            if 'fileCust' not in request.files or 'fileSpot' not in request.files:
                return jsonify({"status": "error", "message": "File Customer dan Spot Bill harus diunggah lengkap."}), 400

            file_cust = request.files['fileCust']
            file_spot = request.files['fileSpot']

            # 1. BACA FILE & BERSIHKAN HEADER
            df_cust = pd.read_csv(file_cust, sep=';', dtype=str, on_bad_lines='skip')
            df_spot = pd.read_csv(file_spot, sep=';', dtype=str, on_bad_lines='skip')

            df_cust.columns = df_cust.columns.str.strip()
            df_spot.columns = df_spot.columns.str.strip()

            # 2. MEGA-MERGE BERDASARKAN ID
            df_final = pd.merge(df_cust, df_spot, left_on='cmr_account', right_on='Nomen', how='inner')

            # ---------------------------------------------------------
            # 🌟 AUTO-DETECT CYCLE & PERIODE DARI FILE
            # ---------------------------------------------------------
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
            # ---------------------------------------------------------

            # 3. KONVERSI TIPE DATA
            kolom_numerik = ['cmr_reading', 'cmr_prev_read', 'Curr_Read_1', 'Prev_Read_1', 'SB_Stand']
            for col in kolom_numerik:
                if col in df_final.columns:
                    df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)

            # 4. TERAPKAN PENAMAAN LNP & PERHITUNGAN
            if 'cmr_reading' in df_final.columns and 'cmr_prev_read' in df_final.columns:
                df_final['Vol_Lap'] = df_final['cmr_reading'] - df_final['cmr_prev_read']
            
            if 'Curr_Read_1' in df_final.columns and 'Prev_Read_1' in df_final.columns:
                df_final['Vol_Bill'] = df_final['Curr_Read_1'] - df_final['Prev_Read_1']
                
            if 'SB_Stand' in df_final.columns and 'Prev_Read_1' in df_final.columns:
                df_final['Vol_SB'] = df_final['SB_Stand'] - df_final['Prev_Read_1']

            if 'Vol_Lap' in df_final.columns:
                df_final['Vol_Riil'] = df_final['Vol_Lap'] 
            df_final['Selisih_HB'] = 31 

            # 5. SIMPAN HASIL KE DATABASE SQLITE (APPEND & ANTI-DOUBLE)
            from sqlalchemy import create_engine, text
            
            os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)
            db_path = os.path.join(app.root_path, 'instance', 'database.db')
            engine = create_engine(f'sqlite:///{db_path}')

            with engine.begin() as conn:
                try:
                    conn.execute(text(f"DELETE FROM history_lnp WHERE cmr_cycle = '{cycle_input}' AND periode_sbrs = '{periode_otomatis}'"))
                except Exception:
                    pass 

            df_final.to_sql('history_lnp', con=engine, if_exists='append', index=False)

            return jsonify({
                "status": "success", 
                "message": f"Data Periode {periode_otomatis} Cycle {cycle_input} berhasil digabung & masuk database!",
                "total_rows": len(df_final)
            })

        except Exception as e:
            return jsonify({"status": "error", "message": f"Gagal memproses file: {str(e)}"}), 500

    # --- API BARU: AMBIL DATA SUMMARY SBRS (VERSI BULLETPROOF) ---
    @app.route('/api/get-summary-sbrs', methods=['GET'])
    def get_summary_sbrs():
        cycle = request.args.get('cycle', 'all')
        
        db_path = os.path.join(app.root_path, 'instance', 'database.db')
        if not os.path.exists(db_path):
            return jsonify({"status": "error", "message": "Database tidak ditemukan."})

        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Pastikan tabel sudah ada
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='history_lnp'")
            if not cursor.fetchone():
                return jsonify({"status": "success", "summary": {"total_objek": 0, "total_vol_riil": 0, "total_hb": 0, "total_kendala": 0}, "skip": [], "trouble": [], "master": []})

            # AUTO-DETECT KOLOM (Mencegah Error Jika Kolom Tidak Ada)
            cursor.execute("PRAGMA table_info(history_lnp)")
            kolom_db = [row[1] for row in cursor.fetchall()]

            col_nomen = 'Nomen' if 'Nomen' in kolom_db else ('nomen' if 'nomen' in kolom_db else ('cmr_account' if 'cmr_account' in kolom_db else kolom_db[0]))
            col_nama = 'cmr_nama' if 'cmr_nama' in kolom_db else ('Nama' if 'Nama' in kolom_db else ('nama_pelanggan' if 'nama_pelanggan' in kolom_db else kolom_db[1]))
            col_skip = 'cmr_skip_code' if 'cmr_skip_code' in kolom_db else None
            col_trbl = 'cmr_trbl1_code' if 'cmr_trbl1_code' in kolom_db else None
            col_vol_riil = 'Vol_Riil' if 'Vol_Riil' in kolom_db else '0'
            col_hb = 'Selisih_HB' if 'Selisih_HB' in kolom_db else '0'

            # Filter Query
            where_clause = ""
            params = []
            if cycle != 'all':
                where_clause = "WHERE cmr_cycle = ?"
                params.append(cycle)

            # 1. Hitung Akumulasi Atas
            cursor.execute(f"SELECT COUNT(*) as tot_obj, SUM({col_vol_riil}) as tot_vol, SUM({col_hb}) as tot_hb FROM history_lnp {where_clause}", params)
            row_sum = cursor.fetchone()
            
            # Hitung Kendala
            tot_kendala = 0
            if col_skip or col_trbl:
                kondisi_kendala = []
                if col_skip: kondisi_kendala.append(f"({col_skip} IS NOT NULL AND {col_skip} != '0' AND {col_skip} != 'nan')")
                if col_trbl: kondisi_kendala.append(f"({col_trbl} IS NOT NULL AND {col_trbl} != '0' AND {col_trbl} != 'nan')")
                
                if kondisi_kendala:
                    query_kendala = f"SELECT COUNT(*) as tot FROM history_lnp {where_clause} {'AND' if where_clause else 'WHERE'} ({' OR '.join(kondisi_kendala)})"
                    cursor.execute(query_kendala, params)
                    tot_kendala = cursor.fetchone()['tot']

            summary = {
                "total_objek": row_sum['tot_obj'] or 0,
                "total_vol_riil": row_sum['tot_vol'] or 0,
                "total_hb": row_sum['tot_hb'] or 0,
                "total_kendala": tot_kendala
            }

            # 2. Rekap Skip
            skip_data = []
            if col_skip:
                cursor.execute(f"SELECT {col_skip} as kode, COUNT(*) as jumlah FROM history_lnp {where_clause} {'AND' if where_clause else 'WHERE'} {col_skip} IS NOT NULL GROUP BY {col_skip}", params)
                for r in cursor.fetchall():
                    val = str(r['kode']).strip()
                    if val not in ['0', 'None', 'nan', '']:
                        skip_data.append({"kode": val, "alasan": "Kendala Lapangan", "jumlah": r['jumlah']})

            # 3. Rekap Trouble
            trouble_data = []
            if col_trbl:
                cursor.execute(f"SELECT {col_trbl} as kode, COUNT(*) as jumlah FROM history_lnp {where_clause} {'AND' if where_clause else 'WHERE'} {col_trbl} IS NOT NULL GROUP BY {col_trbl}", params)
                for r in cursor.fetchall():
                    val = str(r['kode']).strip()
                    if val not in ['0', 'None', 'nan', '']:
                        trouble_data.append({"kode": val, "alasan": "Masalah Teknis", "jumlah": r['jumlah']})

            # 4. Ambil 100 Data Terakhir (PENTING: Pakai ROWID)
            cursor.execute(f"SELECT * FROM history_lnp {where_clause} ORDER BY ROWID DESC LIMIT 100", params)
            
            master_data = []
            for r in cursor.fetchall():
                dict_row = dict(r)
                master_data.append({
                    "nomen": dict_row.get(col_nomen, '-'),
                    "nama": dict_row.get(col_nama, 'Pelanggan'),
                    "vol_lap": dict_row.get('Vol_Lap', 0),
                    "vol_bill": dict_row.get('Vol_Bill', 0),
                    "vol_riil": dict_row.get('Vol_Riil', 0),
                    "vol_sb": dict_row.get('Vol_SB', 0),
                    "hb": dict_row.get('Selisih_HB', 0),
                    "skip": dict_row.get(col_skip, '-') if col_skip else '-',
                    "trouble": dict_row.get(col_trbl, '-') if col_trbl else '-'
                })

            return jsonify({
                "status": "success",
                "summary": summary,
                "skip": skip_data,
                "trouble": trouble_data,
                "master": master_data
            })

        except Exception as e:
            return jsonify({"status": "error", "message": f"Terjadi Kesalahan SQL: {str(e)}"})
        finally:
            conn.close()

    # --- API BARU: DOWNLOAD EXCEL LNP ---
    @app.route('/api/download-sbrs-excel', methods=['GET'])
    def download_sbrs_excel():
        cycle = request.args.get('cycle', 'all')
        db_path = os.path.join(app.root_path, 'instance', 'database.db')
        
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            
            # Ambil data pakai Pandas
            query = "SELECT * FROM history_lnp"
            if cycle != 'all':
                query += f" WHERE cmr_cycle = '{cycle}'"
                
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            if df.empty:
                return "Data tidak ditemukan untuk diekspor", 404

            # Simpan ke folder temporary
            temp_dir = tempfile.mkdtemp()
            output_path = os.path.join(temp_dir, f"Laporan_SBRS_Cycle_{cycle}.xlsx")
            
            df.to_excel(output_path, index=False)
            
            return send_file(output_path, as_attachment=True, download_name=f"Laporan_SBRS_Cycle_{cycle}.xlsx")
            
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
