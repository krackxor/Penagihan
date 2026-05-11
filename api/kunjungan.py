import os
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models import db, MasterPelanggan, MasterPetugas, AnalisaAuditor
from sqlalchemy import and_
from PIL import Image, ImageOps # Tambahan untuk Optimasi Foto Lapangan

# Inisialisasi Blueprint
kunjungan_bp = Blueprint('kunjungan', __name__)

# ==========================================
# MESIN PEMBERSIH NOMEN V18 (WAJIB ADA)
# ==========================================
def clean_nomen(val):
    """Pembersih Nomen Sakti: Memastikan Nomen Lapangan sinkron dengan CID/MC/MB."""
    if not val: return None
    s = str(val).strip().upper()
    s = s.replace('K', '') # Hapus huruf K pengganggu
    s = re.sub(r'[^0-9]', '', s) # Buang karakter non-angka
    if not s: return None
    return s[-8:].zfill(8) # Ambil tepat 8 digit angka

def allowed_file(filename):
    """Validasi format foto agar server tetap bersih."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@kunjungan_bp.route('/cek-pcez/<nomen_raw>', methods=['GET'])
def cek_pcez_petugas(nomen_raw):
    """
    Fitur Otomatis: Cek data pelanggan dan mapping petugas secara real-time.
    Sudah menggunakan clean_nomen agar tidak miss dengan data lapangan.
    """
    nomen = clean_nomen(nomen_raw)
    
    # Cari pelanggan (V18 Style: Mengambil info penting saja untuk speed)
    pelanggan = db.session.query(
        MasterPelanggan.nomen, 
        MasterPelanggan.nama, 
        MasterPelanggan.pcez, 
        MasterPelanggan.kelurahan
    ).filter(MasterPelanggan.nomen == nomen).first()

    if not pelanggan:
        return jsonify({"status": "error", "message": "Nomen tidak ditemukan di database CID"}), 404

    # Cari petugas Tagihan di PCEZ tersebut
    petugas = db.session.query(MasterPetugas.nama_petugas).filter(
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
    Mesin Penerima Laporan Lapangan V18.
    Dilengkapi dengan Auto-Rotation dan Smart Compression untuk menghemat SSD.
    """
    try:
        nomen_raw = request.form.get('nomen')
        nomen = clean_nomen(nomen_raw) 
        
        hasil = request.form.get('hasil_kunjungan')
        tgl_janji = request.form.get('tgl_janji_bayar')
        lat = request.form.get('lat')
        lng = request.form.get('lng')

        if not nomen or not hasil:
            return jsonify({"status": "error", "message": "Nomen dan Hasil Kunjungan wajib diisi"}), 400

        # Ambil snapshot pelanggan
        pelanggan = MasterPelanggan.query.filter_by(nomen=nomen).first()
        if not pelanggan:
             return jsonify({"status": "error", "message": "Nomen tidak valid atau belum terdaftar di CID"}), 400

        # Identifikasi Petugas Otomatis berdasarkan PCEZ
        petugas = MasterPetugas.query.filter_by(pcez=pelanggan.pcez, peran='TAGIHAN').first()
        nama_petugas = petugas.nama_petugas if petugas else "Petugas Luar"

        # Proses Upload & Optimasi Foto
        foto_filename = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and allowed_file(file.filename):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Paksa ekstensi menjadi jpg untuk standardisasi
                filename = secure_filename(f"{nomen}_{timestamp}.jpg")
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                
                try:
                    # Buka gambar di memori
                    img = Image.open(file.stream)
                    
                    # Cegah foto lapangan miring/terbalik
                    img = ImageOps.exif_transpose(img)
                    
                    # Pastikan format kompatibel untuk JPEG
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                        
                    # SMART COMPRESSION: Batasi resolusi maksimal (misal 1280px)
                    # File 5MB akan turun drastis menjadi < 200KB tanpa buram
                    img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                    
                    # Simpan ke SSD Server
                    img.save(save_path, "JPEG", quality=75, optimize=True)
                    foto_filename = filename
                    
                except Exception as e:
                    # Fallback Darurat jika proses Pillow gagal, simpan file mentah
                    file.seek(0)
                    file.save(save_path)
                    foto_filename = secure_filename(file.filename)

        # Konversi Tanggal Janji Bayar
        janji_date = None
        if tgl_janji:
            try:
                janji_date = datetime.strptime(tgl_janji, '%Y-%m-%d').date()
            except ValueError:
                pass 

        # Simpan Laporan ke PostgreSQL (Atomik)
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

@kunjungan_bp.route('/riwayat/<nomen_raw>', methods=['GET'])
def riwayat_kunjungan(nomen_raw):
    """Menarik sejarah kunjungan pelanggan dengan Nomen yang sudah dibersihkan."""
    nomen = clean_nomen(nomen_raw)
    
    riwayat = db.session.query(AnalisaAuditor)\
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
