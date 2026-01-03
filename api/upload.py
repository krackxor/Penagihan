import os
from flask import Blueprint, request, jsonify
from processors.auto_detect import detect_file_period

def register_upload_routes(app, get_db):
    @app.route('/api/upload', methods=['POST'])
    def upload_file():
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['file']
        file_type = request.form.get('file_type') # mc, collection, dll
        
        # Simpan file sementara
        temp_path = os.path.join('uploads', 'temp', file.filename)
        file.save(temp_path)
        
        # Membaca file dengan pandas
        df = pd.read_csv(temp_path) if file.filename.endswith('.csv') else pd.read_excel(temp_path)
        
        # 1. AUTO DETECT PERIODE (SOP Poin 2)
        bulan, tahun = detect_file_period(df, file_type)
        
        if not bulan or not tahun:
            return jsonify({"error": "Gagal mendeteksi periode. Pastikan field acuan tersedia."}), 400
            
        # 2. VALIDASI (SOP Poin 6)
        # Contoh: Cek apakah MC sudah ada sebelum upload Collection (SOP Poin 3)
        if file_type != 'mc':
            db = get_db()
            mc_exists = db.execute(
                "SELECT id FROM master_pelanggan WHERE periode_bulan = ? AND periode_tahun = ?",
                (bulan, tahun)
            ).fetchone()
            
            if not mc_exists:
                return jsonify({"error": f"SOP Violation: MC Periode {bulan}-{tahun} belum tersedia sebagai induk."}), 400

        # 3. PROSES SIMPAN (Data Mundur tetap dihitung periode aslinya - SOP Poin 4)
        # Logika pemrosesan masing-masing file_type di sini...
        
        return jsonify({
            "status": "success",
            "detected_period": f"{bulan}/{tahun}",
            "message": "Data berhasil diupload sesuai SOP"
        })
