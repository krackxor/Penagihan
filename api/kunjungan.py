"""
API Module - Kunjungan Lapangan (Sinergi V16.6)
Fungsi: Menerima laporan dari tim lapangan beserta foto bukti.
Sinergi: Otomatis masuk ke tabel AnalisaAuditor untuk dipantau Real-Time oleh Admin.
"""

import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models import db, AnalisaAuditor

# Definisi Blueprint
kunjungan_bp = Blueprint('kunjungan', __name__)

@kunjungan_bp.route('/submit', methods=['POST'])
def submit_kunjungan():
    try:
        # 1. Ambil Data Teks dari Form HTML (Inputan Auditor)
        nomen = request.form.get('nomen')
        # Jika periode tidak diisi, otomatis gunakan bulan berjalan (YYYYMM)
        periode = request.form.get('periode', datetime.now().strftime('%Y%m'))
        hasil = request.form.get('hasil_kunjungan')
        keterangan = request.form.get('keterangan', '')
        tgl_janji = request.form.get('tgl_janji_bayar')
        auditor = request.form.get('auditor_name', 'Tim Lapangan')
        
        # Ambil Koordinat saat foto diambil (Jika GPS HP diizinkan)
        lat = request.form.get('lat')
        lng = request.form.get('lng')

        # Validasi Data Wajib
        if not nomen or not hasil:
            return jsonify({"status": "error", "message": "Nomen dan Hasil Kunjungan wajib diisi."}), 400

        # 2. Proses File Foto Kunjungan
        foto_path = ""
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '':
                # Anti-Double Name: Tambahkan Nomen dan Timestamp agar nama file selalu unik
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Contoh hasil: 60313566_20260509_153000_meteran.jpg
                filename = secure_filename(f"{nomen}_{timestamp}_{file.filename}")
                
                # Simpan ke KUNJUNGAN_FOLDER (Sudah dikonfigurasi di config.py)
                save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
                file.save(save_path)
                foto_path = filename # Hanya simpan nama filenya saja di database

        # 3. Simpan ke Database Sinergi (Tabel AnalisaAuditor)
        # Cek apakah Nomen ini sudah pernah dikunjungi di periode yang sama
        laporan = AnalisaAuditor.query.filter_by(nomen=nomen, periode_tagihan=periode).first()
        
        # Jika belum ada, buat record baru
        if not laporan:
            laporan = AnalisaAuditor(nomen=nomen, periode_tagihan=periode)
            db.session.add(laporan)

        # Update isi laporan
        laporan.hasil_kunjungan = hasil
        laporan.keterangan_analisa = keterangan
        laporan.auditor_name = auditor
        
        # Simpan koordinat lokasi aktual saat laporan dikirim
        if lat and lng:
            laporan.lat_audit = lat
            laporan.long_audit = lng
        
        # Format Tanggal Janji Bayar jika ada
        if tgl_janji:
            try:
                laporan.tgl_janji_bayar = datetime.strptime(tgl_janji, '%Y-%m-%d').date()
            except ValueError:
                pass # Abaikan jika format tanggal salah dari HP
            
        # Update path foto jika auditor mengunggah foto baru
        if foto_path:
            laporan.foto_bukti = foto_path

        # Eksekusi ke Database
        db.session.commit()

        return jsonify({
            "status": "success", 
            "message": f"Laporan Nomen {nomen} berhasil diunggah ke server!"
        })

    except Exception as e:
        db.session.rollback() # Batalkan transaksi jika terjadi error agar database tidak rusak
        return jsonify({
            "status": "error", 
            "message": f"Gagal menyimpan laporan: {str(e)}"
        }), 500
