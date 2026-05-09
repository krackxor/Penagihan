import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models import db, MasterPelanggan, MasterPetugas, AnalisaAuditor

# Inisialisasi Blueprint untuk modul Kunjungan Lapangan
kunjungan_bp = Blueprint('kunjungan', __name__)

def allowed_file(filename):
    """Cek apakah format file foto diizinkan."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@kunjungan_bp.route('/cek-pcez/<nomen>', methods=['GET'])
def cek_pcez_petugas(nomen):
    """
    Fitur Otomatis: Cek data pelanggan dan nama petugas berdasarkan Nomen.
    Digunakan saat petugas input Nomen di HP, biar nama mereka langsung muncul.
    """
    # 1. Cari data pelanggan (CID)
    pelanggan = MasterPelanggan.query.filter_by(nomen=nomen).first()
    if not pelanggan:
        return jsonify({"status": "error", "message": "Nomen tidak terdaftar di database CID"}), 404

    # 2. Cari nama petugas berdasarkan kode PCEZ pelanggan
    petugas = MasterPetugas.query.filter_by(pcez=pelanggan.pcez).first()
    nama_petugas = petugas.nama_petugas if petugas else "Belum Ada Petugas"

    return jsonify({
        "status": "success",
        "nomen": pelanggan.nomen,
        "nama_pelanggan": pelanggan.nama,
        "pcez": pelanggan.pcez,
        "kelurahan": pelanggan.kelurahan,
        "petugas": nama_petugas
    })

@kunjungan_bp.route('/submit', methods=['POST'])
def submit_laporan():
    """
    Mesin Penerima Laporan Lapangan.
    Menyimpan: Hasil kunjungan, Foto Bukti, Tanggal Janji Bayar, dan Koordinat GPS.
    """
    try:
        nomen = request.form.get('nomen')
        hasil = request.form.get('hasil_kunjungan')
        tgl_janji = request.form.get('tgl_janji_bayar')
        lat = request.form.get('lat')
        lng = request.form.get('lng')

        # 1. Validasi Dasar
        if not nomen or not hasil:
            return jsonify({"status": "error", "message": "Nomen dan Hasil Kunjungan wajib diisi"}), 400

        # 2. Cari Info Petugas & PCEZ Terkini (Biar data sinkron)
        pelanggan = MasterPelanggan.query.filter_by(nomen=nomen).first()
        petugas = MasterPetugas.query.filter_by(pcez=pelanggan.pcez).first() if pelanggan else None
        nama_petugas = petugas.nama_petugas if petugas else "Tanpa Nama"

        # 3. Proses Upload Foto Bukti
        foto_path = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and allowed_file(file.filename):
                # Buat nama file unik: NOMEN_TIMESTAMP.jpg
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"{nomen}_{timestamp}.{ext}")
                
                # Simpan ke folder yang sudah diatur di config.py
                save_path = os.path.join(current_app.config['UPLOAD_KUNJUNGAN'], filename)
                file.save(save_path)
                foto_path = filename # Simpan nama filenya saja ke database

        # 4. Simpan ke Tabel AnalisaAuditor
        # Format tanggal janji bayar jika ada
        janji_date = datetime.strptime(tgl_janji, '%Y-%m-%d').date() if tgl_janji else None

        laporanbaru = AnalisaAuditor(
            nomen=nomen,
            hasil_kunjungan=hasil,
            foto_bukti=foto_path,
            tgl_janji_bayar=janji_date,
            lat_audit=float(lat) if lat else None,
            long_audit=float(lng) if lng else None,
            auditor_name=nama_petugas,
            pcez_audit=pelanggan.pcez if pelanggan else None
        )

        db.session.add(laporanbaru)
        db.session.commit()

        return jsonify({
            "status": "success", 
            "message": f"Laporan berhasil dikirim. Terima kasih {nama_petugas}!"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@kunjungan_bp.route('/riwayat/<nomen>', methods=['GET'])
def riwayat_kunjungan(nomen):
    """Melihat catatan sejarah kunjungan untuk satu Nomen tertentu."""
    riwayat = AnalisaAuditor.query.filter_by(nomen=nomen).order_by(AnalisaAuditor.timestamp.desc()).all()
    
    data = []
    for r in riwayat:
        data.append({
            "tanggal": r.timestamp.strftime("%d-%m-%Y %H:%M"),
            "petugas": r.auditor_name,
            "hasil": r.hasil_kunjungan,
            "foto": r.foto_bukti
        })
    
    return jsonify({"status": "success", "riwayat": data})
