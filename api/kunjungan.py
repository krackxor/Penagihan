import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models import db, MasterPelanggan, MasterPetugas, AnalisaAuditor
from sqlalchemy import and_

# Inisialisasi Blueprint
kunjungan_bp = Blueprint('kunjungan', __name__)

def allowed_file(filename):
    """Validasi format foto agar server tetap bersih dari file sampah."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@kunjungan_bp.route('/cek-pcez/<nomen>', methods=['GET'])
def cek_pcez_petugas(nomen):
    """
    Fitur Otomatis: Cek data pelanggan dan mapping petugas secara real-time.
    Menggunakan Explicit Join agar sinkron dengan standar Sinergi.
    """
    # Cari pelanggan dan info wilayahnya
    pelanggan = db.session.query(MasterPelanggan).filter_by(nomen=nomen).first()
    if not pelanggan:
        return jsonify({"status": "error", "message": "Nomen tidak ditemukan di database CID"}), 404

    # Cari petugas dengan peran 'TAGIHAN' yang bertugas di PCEZ tersebut
    petugas = db.session.query(MasterPetugas).filter(
        and_(MasterPetugas.pcez == pelanggan.pcez, MasterPetugas.peran == 'TAGIHAN')
    ).first()
    
    nama_petugas = petugas.nama_petugas if petugas else "Belum Ada Petugas Tagihan"

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
    Menangani data teks, koordinat GPS, dan upload bukti foto secara atomik.
    """
    try:
        nomen = request.form.get('nomen')
        hasil = request.form.get('hasil_kunjungan')
        tgl_janji = request.form.get('tgl_janji_bayar')
        lat = request.form.get('lat')
        lng = request.form.get('lng')

        if not nomen or not hasil:
            return jsonify({"status": "error", "message": "Nomen dan Hasil Kunjungan wajib diisi"}), 400

        # Ambil data pelanggan untuk snapshot PCEZ saat kunjungan
        pelanggan = MasterPelanggan.query.filter_by(nomen=nomen).first()
        if not pelanggan:
             return jsonify({"status": "error", "message": "Nomen tidak valid"}), 400

        # Identifikasi Petugas Otomatis
        petugas = MasterPetugas.query.filter_by(pcez=pelanggan.pcez, peran='TAGIHAN').first()
        nama_petugas = petugas.nama_petugas if petugas else "Petugas Luar"

        # Proses Upload Foto (Sinergi dengan UPLOAD_FOLDER di app.py)
        foto_filename = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and allowed_file(file.filename):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"{nomen}_{timestamp}.{ext}")
                
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                foto_filename = filename

        # Konversi Tanggal Janji Bayar
        janji_date = None
        if tgl_janji:
            try:
                janji_date = datetime.strptime(tgl_janji, '%Y-%m-%d').date()
            except ValueError:
                pass 

        # Simpan Laporan ke PostgreSQL
        laporan = AnalisaAuditor(
            nomen=nomen,
            hasil_kunjungan=hasil,
            foto_bukti=foto_filename,
            tgl_janji_bayar=janji_date,
            lat_audit=float(lat) if lat else None,
            long_audit=float(lng) if lng else None,
            auditor_name=nama_petugas
        )

        db.session.add(laporan)
        db.session.commit()

        return jsonify({
            "status": "success", 
            "message": f"Laporan terkirim. Terima Kasih, {nama_petugas}!"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Kesalahan Sistem: {str(e)}"}), 500

@kunjungan_bp.route('/riwayat/<nomen>', methods=['GET'])
def riwayat_kunjungan(nomen):
    """
    Menarik sejarah kunjungan pelanggan.
    Kencang karena menggunakan Index pada kolom nomen di AnalisaAuditor.
    """
    riwayat = db.session.query(AnalisaAuditor).select_from(AnalisaAuditor)\
                .filter_by(nomen=nomen)\
                .order_by(AnalisaAuditor.timestamp.desc()).all()
    
    output = []
    for r in riwayat:
        output.append({
            "tanggal": r.timestamp.strftime("%d/%m/%Y %H:%M"),
            "petugas": r.auditor_name,
            "hasil": r.hasil_kunjungan,
            "foto": r.foto_bukti if r.foto_bukti else None,
            "gps": f"{r.lat_audit}, {r.long_audit}" if r.lat_audit else "Tanpa Koordinat"
        })
    
    return jsonify({"status": "success", "riwayat": output})
