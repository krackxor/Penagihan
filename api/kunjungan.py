import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models import db, MasterPelanggan, MasterPetugas, AnalisaAuditor

# Inisialisasi Blueprint
kunjungan_bp = Blueprint('kunjungan', __name__)

def allowed_file(filename):
    """Validasi format foto agar server tidak menyimpan file sampah."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@kunjungan_bp.route('/cek-pcez/<nomen>', methods=['GET'])
def cek_pcez_petugas(nomen):
    """
    Fitur Otomatis: Cek data pelanggan dan nama petugas penagihan.
    Membantu petugas (Wahyu dkk) agar tidak perlu input nama manual.
    """
    pelanggan = MasterPelanggan.query.filter_by(nomen=nomen).first()
    if not pelanggan:
        return jsonify({"status": "error", "message": "Nomen tidak ditemukan di database CID"}), 404

    # Cari petugas dengan peran spesifik 'TAGIHAN' sesuai PCEZ pelanggan
    petugas = MasterPetugas.query.filter_by(pcez=pelanggan.pcez, peran='TAGIHAN').first()
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
    Menangani data teks, koordinat GPS, dan upload foto bukti kunjungan.
    """
    try:
        nomen = request.form.get('nomen')
        hasil = request.form.get('hasil_kunjungan')
        tgl_janji = request.form.get('tgl_janji_bayar')
        lat = request.form.get('lat')
        lng = request.form.get('lng')

        # 1. Validasi Input
        if not nomen or not hasil:
            return jsonify({"status": "error", "message": "Nomen dan Hasil Kunjungan wajib diisi"}), 400

        # 2. Ambil Info Pelanggan Terkini
        pelanggan = MasterPelanggan.query.filter_by(nomen=nomen).first()
        if not pelanggan:
             return jsonify({"status": "error", "message": "Nomen tidak valid"}), 400

        # Ambil petugas penagihan untuk dicatat di riwayat
        petugas = MasterPetugas.query.filter_by(pcez=pelanggan.pcez, peran='TAGIHAN').first()
        nama_petugas = petugas.nama_petugas if petugas else "Tanpa Nama"

        # 3. Proses Foto Bukti (Disimpan ke Disk agar DB Ringan)
        foto_filename = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and allowed_file(file.filename):
                # Nama file: NOMEN_TANGGAL_JAM.jpg
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"{nomen}_{timestamp}.{ext}")
                
                # Gunakan UPLOAD_FOLDER yang sudah kita setel di app.py
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                foto_filename = filename

        # 4. Simpan ke PostgreSQL
        janji_date = None
        if tgl_janji:
            try:
                janji_date = datetime.strptime(tgl_janji, '%Y-%m-%d').date()
            except:
                pass # Abaikan jika format tanggal salah

        laporan = AnalisaAuditor(
            nomen=nomen,
            hasil_kunjungan=hasil,
            foto_bukti=foto_filename,
            tgl_janji_bayar=janji_date,
            lat_audit=float(lat) if lat else None,
            long_audit=float(lng) if lng else None,
            auditor_name=nama_petugas,
            pcez_saat_ini=pelanggan.pcez # Sesuaikan dengan models.py
        )

        db.session.add(laporan)
        db.session.commit()

        return jsonify({
            "status": "success", 
            "message": f"Laporan Berhasil. Terima Kasih, {nama_petugas}!"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Gagal simpan: {str(e)}"}), 500

@kunjungan_bp.route('/riwayat/<nomen>', methods=['GET'])
def riwayat_kunjungan(nomen):
    """
    Menampilkan sejarah kunjungan pelanggan.
    Sangat kencang karena kolom 'nomen' di AnalisaAuditor sudah kita beri Index.
    """
    riwayat = AnalisaAuditor.query.filter_by(nomen=nomen).order_by(AnalisaAuditor.timestamp.desc()).all()
    
    output = []
    for r in riwayat:
        output.append({
            "tanggal": r.timestamp.strftime("%d/%m/%Y %H:%M"),
            "petugas": r.auditor_name,
            "hasil": r.hasil_kunjungan,
            "foto": r.foto_bukti if r.foto_bukti else None
        })
    
    return jsonify({"status": "success", "riwayat": output})
