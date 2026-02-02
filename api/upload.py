"""
Smart Integration Engine - Sunter Dashboard Pro (V13.12 Header Matcher)
Update: 2026-02-02
Fitur Baru:
1. ✅ HEADER MATCHER: Mapping kolom spesifik sesuai file MC/MB user (NAMA_PEL, ALM1_PEL).
2. ✅ ANTI-SWAP: Mencegah tertukarnya file MC dan MB dengan validasi silang kolom unik.
"""

import pandas as pd
import os
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

    def handle_file(self, file_path, data_type, target_period):
        df = pd.read_excel(file_path) if file_path.endswith(('.xls', '.xlsx')) else pd.read_csv(file_path)
        
        # ✅ MAPPING KHUSUS (Sesuai File User)
        map_conf = {
            'MC': {
                'nomen': ['NOMEN', 'IDPEL'], 
                'nama': ['NAMA_PEL', 'NAMA'],           # Update: NAMA_PEL
                'alamat': ['ALM1_PEL', 'ALAMAT'],       # Update: ALM1_PEL
                'pcez': ['ZONA_NOVAK', 'PCEZ', 'RUTE'], # Update: Fallback ke ZONA jika PCEZ tidak ada
                'rayon': ['RAYON'], 
                'nominal': ['NOMINAL', 'TAGIHAN', 'TOTAL'], 
                'nomet': ['NOMET', 'NO_METER'], 
                'no_hp': ['NO_HP', 'TELP']
            },
            'MB': {
                'nomen': ['NOMEN', 'IDPEL'], 
                'tgl_bayar': ['TGL_BAYAR', 'TANGGAL'], 
                'nominal': ['NOMINAL', 'JML_BAYAR', 'BAYAR'], # Update: NOMINAL
                'kategori': ['LKS_BAYAR', 'KATEGORI', 'LOKET'], 
                'bulan_rek': ['BULAN_REK', 'BLN_REK']
            },
            'COLLECTION': {'nomen': ['NOMEN'], 'pay_dt': ['PAY_DT'], 'nominal': ['TOTAL'], 'kategori': ['COLLECTOR'], 'bulan_rek': ['BLN_REK']},
            'ARDEBT': {'nomen': ['NOMEN'], 'periode_bill': ['PERIODE_BILL'], 'jumlah': ['JUMLAH'], 'volume': ['VOLUME', 'KUBIK'], 'tipe_bill': ['TIPE_BILL']},
            'RUTE': {'pcez': ['PCEZ'], 'petugas': ['PETUGAS']}
        }

        # 1. IDENTIFIKASI KOLOM
        found_cols = {}
        for key, candidates in map_conf[data_type].items():
            col_name = self.get_column(df, candidates)
            if col_name: found_cols[key] = col_name
        
        # 2. 🛡️ SMART VALIDATOR (ANTI-SWAP)
        # Validasi File MC
        if data_type == 'MC':
            # MC Wajib punya Nama Pelanggan atau Alamat
            if 'nama' not in found_cols and 'alamat' not in found_cols:
                raise ValueError("⛔ DITOLAK: File ini tidak terlihat seperti Master Pelanggan (MC). Kolom NAMA_PEL/ALM1_PEL tidak ditemukan.")
            
            # MC HARAM punya Tgl Bayar (Itu ciri MB)
            if self.get_column(df, ['TGL_BAYAR']):
                raise ValueError("⛔ DITOLAK: File ini memiliki kolom TGL_BAYAR. Ini adalah file MB (Bayar), jangan upload di menu MC!")

        # Validasi File MB
        if data_type == 'MB':
            # MB Wajib punya Tgl Bayar
            if 'tgl_bayar' not in found_cols:
                raise ValueError("⛔ DITOLAK: File Master Bayar (MB) wajib memiliki kolom TGL_BAYAR.")
            
            # MB HARAM punya Alamat Lengkap (Itu ciri MC)
            if self.get_column(df, ['ALM1_PEL', 'ALM2_PEL']):
                raise ValueError("⛔ DITOLAK: File ini memiliki kolom ALM1_PEL. Ini adalah file MC (Pelanggan), jangan upload di menu MB!")

        if len(found_cols) < 2: raise ValueError("Format file tidak dikenali. Pastikan header sesuai template.")

        # 3. PROSES DATA
        bulk_main = []
        bulk_rute = []
        
        for index, row in df.iterrows():
            nomen = clean_nomen(row.get(found_cols.get('nomen'), ''))
            if not nomen: continue
            
            if data_type == 'RUTE':
                pcez = str(row.get(found_cols.get('pcez'), '')).strip()
                petugas = str(row.get(found_cols.get('petugas'), '')).strip().upper()
                if pcez and petugas: bulk_rute.append((pcez, petugas))
                continue

            nominal = self.cast_to_float(row.get(found_cols.get('nominal') or found_cols.get('jumlah'), 0))

            if data_type == 'MC':
                nama = str(row.get(found_cols.get('nama'), '-')).strip()
                alamat = str(row.get(found_cols.get('alamat'), '-')).strip()
                pcez = str(row.get(found_cols.get('pcez'), '-')).strip()
                rayon = str(row.get(found_cols.get('rayon'), '-')).strip()
                nomet = str(row.get(found_cols.get('nomet'), '-')).strip()
                no_hp = str(row.get(found_cols.get('no_hp'), '-')).strip()
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

        # 4. EKSEKUSI DATABASE
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
                "message": f"Integrasi Berhasil! {count} baris data masuk.",
                "details": [f"File processed: {os.path.basename(file_path)}"]
            })

        except Exception as e:
            db.rollback()
            return jsonify({"status": "error", "message": f"Database Error: {str(e)}"}), 500
        finally:
            db.close()

@upload_bp.route('/upload', methods=['POST'])
def handle_smart_upload():
    if 'file' not in request.files: return jsonify({"status": "error", "message": "No file"}), 400
    file = request.files['file']
    data_type = request.form.get('type')
    periode = request.form.get('periode')
    if not data_type or not periode: return jsonify({"status": "error", "message": "Tipe & Periode wajib"}), 400

    filename = f"{data_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    save_path = os.path.join(current_app.root_path, 'static', 'uploads', filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)
    
    try: return UploadEngine().handle_file(save_path, data_type, periode)
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500
