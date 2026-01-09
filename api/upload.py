"""
Upload API - Sunter Dashboard Pro
Sinergi:
1. Auto-Detection: Mengenali tipe file (MC, MB, Rute, Ardebt) secara otomatis.
2. Auto-Rayon: Mapping otomatis Rayon 34/35 berdasarkan prefix kode PCEZ.
3. WhatsApp Integration: Sinkronisasi No Admin WA saat update mapping rute.
"""

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import clean_nomen, validate_periode
from processors.auto_detect import identify_file_type, detect_file_period

upload_bp = Blueprint('upload', __name__)

def clean_pcez(val):
    """
    Standarisasi Kode Rute (PCEZ).
    Mengubah format acak (misal: 34011 atau 34/11) menjadi format standar 34/11.
    Juga mendeteksi Rayon secara otomatis.
    """
    if pd.isna(val) or str(val).strip().upper() in ('NAN', 'NULL', ''):
        return None, None
    
    # Ambil angka saja
    val_str = str(val).strip()
    digits = ''.join(filter(str.isdigit, val_str))
    
    if len(digits) < 4:
        return val_str, None

    # Logika Rayon: 2 angka pertama
    rayon = digits[:2] if digits[:2] in ('34', '35') else '35'
    
    # Format XXX/XX (Sinergi Standard)
    if len(digits) == 4: # misal 3401 -> 034/01
        formatted = f"0{digits[:2]}/{digits[2:]}"
    elif len(digits) == 5: # misal 34011 -> 340/11
        formatted = f"{digits[:3]}/{digits[3:]}"
    else:
        formatted = val_str # Fallback jika format sangat asing
            
    return formatted, rayon

@upload_bp.route('/upload', methods=['POST'])
def handle_upload():
    """Endpoint unggahan tunggal dengan Auto-Processor (Admin Only)."""
    if session.get('role') != 'admin':
        return jsonify({"error": "Akses Ditolak: Khusus Administrator"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "Pilih file Excel terlebih dahulu"}), 400
    
    file = request.files['file']
    db = get_db_connection()
    row_count = 0
    
    try:
        # Load data dengan dtype str untuk mencegah hilangnya angka nol di depan (IDPEL)
        df = pd.read_excel(file, dtype=str).fillna('')
        file_type = identify_file_type(df)
        
        if not file_type:
            return jsonify({"error": "Sistem tidak mengenali struktur kolom file ini."}), 400

        # Deteksi Periode (Manual atau Auto-Detect dari Header)
        bulan, tahun = detect_file_period(df, file_type)
        periode_str = f"{str(bulan).zfill(2)}-{tahun}" if bulan else datetime.now().strftime('%m-%Y')
        
        df.columns = [str(c).upper().strip() for c in df.columns]
        row_count = len(df)

        # 1. PROSES MAPPING RUTE
        if file_type == 'rute':
            for _, row in df.iterrows():
                pcez, _ = clean_pcez(row.get('PCEZ'))
                petugas = str(row.get('PETUGAS', '')).strip().upper()
                # Sinergi WA: Simpan nomor admin jika tersedia
                no_admin = str(row.get('NO_ADMIN', '628123456789')).replace("'", "").strip()
                
                if pcez and petugas:
                    db.execute("""
                        INSERT OR REPLACE INTO rute_petugas (pcez, petugas, no_admin, updated_at) 
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, (pcez, petugas, no_admin))

        # 2. PROSES MASTER TAGIHAN (MC)
        elif file_type == 'mc':
            # Bersihkan data lama pada periode yang sama untuk akurasi re-upload
            db.execute("DELETE FROM master_pelanggan WHERE periode = ? AND tipe = 'MC'", (periode_str,))
            
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                if not nomen: continue
                
                pcez_fixed, rayon = clean_pcez(row.get('ZONA_NOVAK'))
                nominal = float(str(row.get('NOMINAL', 0)).replace(',', ''))
                volume = float(str(row.get('KUBIK', 0)).replace(',', ''))
                
                db.execute("""
                    INSERT INTO master_pelanggan 
                    (nomen, notagihan, nomet, nama, pcez, rayon, nominal, volume, tipe, periode) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MC', ?)
                """, (nomen, clean_nomen(row.get('NOTAGIHAN')), clean_nomen(row.get('NOMET')), 
                      row.get('NAMA_PEL'), pcez_fixed, rayon, nominal, volume, periode_str))

        # 3. PROSES DATA ARDEBT (TUNGGAKAN BEREKOR)
        elif file_type == 'ardebt':
            # Ardebt bersifat refresh total setiap upload
            db.execute("DELETE FROM ardebt")
            for _, row in df.iterrows():
                nomen = clean_nomen(row.get('NOMEN'))
                if not nomen: continue
                
                jumlah = float(str(row.get('JUMLAH', 0)).replace(',', ''))
                db.execute("""
                    INSERT INTO ardebt (nomen, jumlah, volume, periode_bill) 
                    VALUES (?, ?, ?, ?)
                """, (nomen, jumlah, row.get('VOLUME', 0), str(row.get('PERIODE_BILL', '')).strip()))

        # 4. LOG HISTORY & COMMIT
        db.execute("""
            INSERT INTO upload_history (file_name, file_type, periode, row_count, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (file.filename, file_type.upper(), periode_str, row_count, 'SUCCESS'))
        
        db.commit()
        return jsonify({
            "status": "success", 
            "message": f"Sync {file_type.upper()} Berhasil", 
            "rows": row_count, 
            "periode": periode_str
        })

    except Exception as e:
        if db: db.rollback()
        return jsonify({"error": f"Gagal memproses data: {str(e)}"}), 500
    finally:
        if db: db.close()

@upload_bp.route('/data-status', methods=['GET'])
def get_data_status():
    """Audit Kesiapan Data: Digunakan oleh Admin untuk memantau integritas database."""
    db = get_db_connection()
    try:
        tables = {
            'MC': 'master_pelanggan WHERE tipe="MC"', 
            'MB': 'master_bayar', 
            'Collection': 'collection_harian', 
            'Ardebt': 'ardebt', 
            'Rute': 'rute_petugas'
        }
        status = {}
        for label, table in tables.items():
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            status[label] = {"exists": count > 0, "count": count}
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
