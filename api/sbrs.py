from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan, MasterPetugas, DataSBRS
from sqlalchemy import func, and_

sbrs_bp = Blueprint('sbrs', __name__)

@sbrs_bp.route('/summary')
def sbrs_summary():
    """
    Halaman 1: Ringkasan Eksekutif (Dashboard).
    Menampilkan jumlah kasus Zero, Ekstrem, dan Turun per Kelurahan.
    """
    ab = request.args.get('ab', 'AB Sunter')
    
    # 1. Hitung total per kategori anomali
    # Query ini sangat cepat karena kategori_anomali sudah kita beri Index
    stats = db.session.query(
        DataSBRS.kategori_anomali, 
        func.count(DataSBRS.id)
    ).join(MasterPelanggan).filter(MasterPelanggan.ab == ab)\
     .group_by(DataSBRS.kategori_anomali).all()
    
    summary_data = {k: v for k, v in stats if k}
    
    # 2. Hitung sebaran anomali per Kelurahan
    kelurahan_stats = db.session.query(
        MasterPelanggan.kelurahan, 
        func.count(DataSBRS.id)
    ).join(DataSBRS).filter(MasterPelanggan.ab == ab)\
     .group_by(MasterPelanggan.kelurahan)\
     .order_by(func.count(DataSBRS.id).desc()).all()

    return render_template('sbrs_summary.html', 
                           summary=summary_data, 
                           kelurahan_data=kelurahan_stats,
                           current_ab=ab)

@sbrs_bp.route('/analisa')
def sbrs_analisa():
    """
    Halaman 2: Detail Analisa Kasus.
    Digunakan petugas SBRS untuk memverifikasi meteran pelanggan.
    """
    ab = request.args.get('ab', 'AB Sunter')
    kat = request.args.get('kategori') # ZERO, EKSTREM, atau TURUN

    # Query gabungan untuk menampilkan detail anomali + nama petugas SBRS
    query = db.session.query(
        DataSBRS.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        DataSBRS.bulan_ini,
        DataSBRS.rata_rata,
        DataSBRS.kategori_anomali,
        MasterPetugas.nama_petugas.label('nama_petugas_anomali')
    ).join(MasterPelanggan, DataSBRS.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, and_(
         MasterPelanggan.pcez == MasterPetugas.pcez, 
         MasterPetugas.peran == 'ANOMALI' # Filter peran khusus SBRS/Anomali
     )).filter(MasterPelanggan.ab == ab)

    # Filter berdasarkan kategori jika dipilih dari dashboard
    if kat and kat != 'all':
        query = query.filter(DataSBRS.kategori_anomali == kat)

    # Limit 1000 data pertama untuk menjaga performa loading browser
    results = query.limit(1000).all()
    
    return render_template('sbrs_analisa.html', 
                           data=results, 
                           current_ab=ab, 
                           current_kat=kat)
