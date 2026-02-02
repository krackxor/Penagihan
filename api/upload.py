"""
Smart Integration Engine - Sunter Dashboard Pro (V13.16 Auto-Pilot Restored)
Update: 2026-02-02
Fitur Pemulihan:
1. ✅ AUTO-PILOT: Otomatis deteksi Periode dari nama file (misal: "1225" -> "12-2025").
2. ✅ AUTO-TYPE: Otomatis deteksi Tipe dari nama file (misal: "MC..." -> "MC").
3. 🛡️ IRON DOME: Tetap aktif menjaga agar data tidak tertukar.
"""

import pandas as pd
import os
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, log_action

upload_bp = Blueprint('upload', __name__)

class UploadEngine:
    @staticmethod
    def cast_to_float(value):
        try:
            if pd.isna(value) or str(value).strip() == '': return 0.0
            s_val = str(value).replace('\xa0', '').replace(' ', '').replace("'", "").replace("Rp", "")
            if ',' in s_val and '.' in s_val: s_val = s_val.replace('.', '').replace(',', '.')
            elif ',' in s_val: s_val = s_val.replace(',', '.')
            return float(s_val)
        except: return 0.0

    @staticmethod
    def get_column(df, possible_names):
        cols = {c.upper().strip(): c for c in df.columns}
        for name in possible_names:
            u_name = name.upper().strip()
            if u_name in cols: return cols[u_name]
        return None

    @staticmethod
    def clean_bulan_rek(value):
        if not value or pd.isna(value): return ""
        clean_val = ''.join(filter(str.isdigit, str(value)))
        if len(clean_val) == 6: return clean_val
        elif len(clean_val) == 5: return "0" + clean_val
        return clean_val

    def handle_file(self, file_path, data_type, target_period):
        df = pd.read_excel(file_path) if file_path.endswith(('.xls', '.xlsx')) else pd.read_csv(file_path)
        file_cols = [str(c).upper().strip() for c in df.columns]

        # 🛡️ IRON DOME VALIDATOR (Keamanan Data)
        if data_type == 'MC':
            suspicious_mb_cols = ['TGL_BAYAR', 'TANGGAL_BAYAR', 'PAY_DT', 'JML_BAYAR']
            if any(danger in file_cols for danger in suspicious_mb_cols):
                raise ValueError("⛔ DIBLOKIR: Sistem mendeteksi 'TGL_BAYAR'. Ini file MB, jangan upload di MC!")
            if not any(req in file_cols for req in ['NAMA', 'NAMA_PEL', 'ALAMAT', 'ALM1_PEL']):
                raise ValueError("⛔ DIBLOKIR: File MC wajib punya kolom NAMA atau ALAMAT.")

        if data_type == 'MB':
            if not any(req in file_cols for req in ['TGL_BAYAR', 'TANGGAL', 'PAY_DT']):
                raise ValueError("⛔ DIBLOKIR: File MB wajib punya kolom TGL_BAYAR.")

        # MAPPING KOLOM
        map_conf = {
            'MC': {'nomen': ['NOMEN', 'IDPEL'], 'nama': ['NAMA_PEL', 'NAMA'], 'alamat': ['ALM1_PEL', 'ALAMAT'], 'pcez': ['ZONA_NOVAK', 'PCEZ', 'RUTE'], 'rayon': ['RAYON'], 'nominal': ['NOMINAL', 'TAGIHAN'], 'nomet': ['NOMET', 'NO_METER'], 'no_hp': ['NO_HP']},
            'MB': {'nomen': ['NOMEN', 'IDPEL'], 'tgl_bayar': ['TGL_BAYAR', 'TANGGAL'], 'nominal': ['NOMINAL', 'JML_BAYAR', 'BAYAR'], 'kategori': ['LKS_BAYAR', 'KATEGORI'], 'bulan_rek': ['BULAN_REK', 'BLN_REK']},
            'COLLECTION': {'nomen': ['NOMEN'], 'pay_dt': ['PAY_DT'], 'nominal': ['TOTAL'], 'kategori': ['COLLECTOR'], 'bulan_rek': ['BLN_REK']},
            'ARDEBT': {'nomen': ['NOMEN'], 'periode_bill': ['PERIODE_BILL'], 'jumlah': ['JUMLAH'], 'volume': ['VOLUME', 'KUBIK'], 'tipe_bill': ['TIPE_BILL', 'TIPE']},
            'RUTE': {'pcez': ['PCEZ'], 'petugas': ['PETUGAS']}
        }

        found_cols = {}
        for key, candidates in map_conf[data_type].items():
            col_name = self.get_column(df, candidates)
            if col_name: found_cols[key] = col_name
        
        if len(found_cols) < 2: raise ValueError("Format file tidak dikenali.")

        bulk_main = []
        bulk_rute = []
        
        for index, row in df.iterrows():
            nomen = clean_nomen(row.get(found_cols.get('nomen'), ''))
            
            if data_type == 'RUTE':
                pcez = str(row.get(found_cols.get('pcez'), '')).strip()
                petugas = str(row.get(found_cols.get('petugas'), '')).strip().upper()
                if pcez and petugas: bulk_rute.append((pcez, petugas))
                continue

            if not nomen: continue
            nominal = self.cast_to_float(row.get(found_cols.get('nominal') or found_cols.get('jumlah'), 0))

            if data_type == 'MC':
                nama = str(row.get(found_cols.get('nama'), '-')).strip()
                alamat = str(row.get(found_cols.get('alamat'), '-')).strip()
                pcez = str(row.get(found_cols.get('pcez'), '-')).strip()
                rayon = str(row.get(found_cols.get('rayon'), '-')).strip()
                nomet = str(row.get(found_cols.get('nomet'), '-')).strip()
                no_hp = str(row.get(found_cols.get('no_hp'), '-')).strip()
                if nama == '-' and alamat == '-': continue
                bulk_main.append((nomen, nama, alamat, pcez, rayon, nominal, nomet, target_period, no_hp, 'MC', 0))
            
            elif data_type in ['MB', 'COLLECTION']:
                raw_tgl = row.get(found_cols.get('tgl_bayar') or found_cols.get('pay_dt'))
                try: dt_val = pd.to_datetime(raw_tgl).strftime('%Y-%m-%d')
                except: dt_val = datetime.now().strftime('%Y-%m-%d')
                kategori = str(row.get(found_cols.get('kategori'), '-')).strip()
                bulan_rek = str(row.get(found_cols.get('bulan_rek'), '-')).strip()
                bulk_main.append((nomen, dt_val, nominal, target_period, kategori, bulan_rek))
            
            elif data_type == 'ARDEBT':
                if nominal > 0:
                    vol = self.cast_to_float(row.get(found_cols.get('volume'), 0))
                    tipe = str(row.get(found_cols.get('tipe_bill'), 'WATER')).strip()
                    periode_bill = str(row.get(found_cols.get('periode_bill'), '-')).strip()
                    bulk_main.append((nomen, periode_bill, nominal, vol, target_period, tipe))

        db = get_db_connection()
        try:
            db.execute("PRAGMA synchronous = OFF")
            if data_type == 'RUTE' and bulk_rute:
                db.executemany("INSERT OR REPLACE INTO rute_petugas (pcez, petugas, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", bulk_rute)
            elif data_type == 'MC' and bulk_main:
                db.executemany("INSERT OR REPLACE INTO master_pelanggan (nomen, nama, alamat, pcez, rayon, nominal, nomet, periode, no_hp, tipe, status_lunas) VALUES (?,?,?,?,?,?,?,?,?,?,?)", bulk_main)
            elif data_type in ['MB', 'COLLECTION'] and bulk_main:
                tbl = "master_bayar" if data_type == 'MB' else "collection_harian"
                dt_col = "tgl_bayar" if data_type == 'MB' else "pay_dt"
                db.executemany(f"INSERT OR REPLACE INTO {tbl} (nomen, {dt_col}, nominal, periode, kategori, bulan_rek) VALUES (?,?,?,?,?,?)", bulk_main)
            elif data_type == 'ARDEBT' and bulk_main:
                db.executemany("INSERT OR REPLACE INTO ardebt (nomen, periode_bill, jumlah, volume, periode, tipe_bill) VALUES (?,?,?,?,?,?)", bulk_main)

            count = len(bulk_main) if data_type != 'RUTE' else len(bulk_rute)
            db.execute("INSERT INTO upload_history (file_name, file_type, periode, row_count, status) VALUES (?,?,?,?,?)",
                       (os.path.basename(file_path), data_type, target_period, count, 'SUCCESS'))
            db.commit()
            return jsonify({
                "status": "success", 
                "message": f"Integrasi Berhasil! {count} baris data masuk ({data_type} - {target_period}).", 
                "details": [f"File: {os.path.basename(file_path)}"]
            })
        except Exception as e:
            db.rollback()
            return jsonify({"status": "error", "message": f"Database Error: {str(e)}"}), 500
        finally:
            db.close()

# ✅ HELPER: Auto-Deteksi Cerdas
def auto_detect_info(filename, form_type, form_period):
    """Menebak Tipe & Periode dari Nama File jika user tidak input."""
    filename_upper = filename.upper()
    
    # 1. Deteksi Tipe (Jika kosong)
    if not form_type:
        if 'MC' in filename_upper: form_type = 'MC'
        elif 'MB' in filename_upper or 'BAYAR' in filename_upper: form_type = 'MB'
        elif 'ARDEBT' in filename_upper or 'SOREK' in filename_upper: form_type = 'ARDEBT'
        elif 'RUTE' in filename_upper: form_type = 'RUTE'
        elif 'COLLECTION' in filename_upper: form_type = 'COLLECTION'
    
    # 2. Deteksi Periode (Jika kosong)
    # Mencari pola angka "1225" (MMYY) atau "12-25" atau "12 25"
    if not form_period:
        match = re.search(r'(\d{2})[\s-]?(\d{2})', filename)
        if match:
            mm, yy = match.groups()
            # Validasi Bulan (01-12)
            if 1 <= int(mm) <= 12:
                # Asumsi Tahun: Jika < 50 berarti 20xx (Misal 25 -> 2025)
                year = f"20{yy}" if len(yy) == 2 else yy
                form_period = f"{mm}-{year}"
    
    # Fallback: Jika masih kosong, pakai bulan ini
    if not form_period:
        form_period = datetime.now().strftime('%m-%Y')
        
    return form_type, form_period

@upload_bp.route('/upload', methods=['POST'])
def handle_smart_upload():
    if 'file' not in request.files: return jsonify({"status": "error", "message": "No file uploaded"}), 400
    file = request.files['file']
    
    # Baca input user
    data_type = request.form.get('type') or request.form.get('dataType')
    periode = request.form.get('periode') or request.form.get('period')
    
    # ✅ JALANKAN AUTO-DETEKSI (Mengisi yang kosong)
    data_type, periode = auto_detect_info(file.filename, data_type, periode)
    
    # Validasi Terakhir
    if not data_type:
        return jsonify({"status": "error", "message": "Gagal mendeteksi Tipe File. Mohon pilih manual."}), 400

    filename = f"{data_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    save_path = os.path.join(current_app.root_path, 'static', 'uploads', filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)
    
    try: return UploadEngine().handle_file(save_path, data_type, periode)
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500
