from flask import Blueprint, render_template, request
from models import db, MasterPelanggan, MasterPetugas, DataSBRS
from sqlalchemy import func, and_

sbrs_bp = Blueprint('sbrs', __name__)

@sbrs_bp.route('/summary')
def sbrs_summary():
    """Halaman 1: Ringkasan Eksekutif (Summary)"""
    ab = request.args.get('ab', 'AB Sunter')
    
    # Hitung total per kategori untuk Dashboard
    stats = db.session.query(
        DataSBRS.kategori_anomali, 
        func.count(DataSBRS.id)
    ).join(MasterPelanggan).filter(MasterPelanggan.ab == ab).group_by(DataSBRS.kategori_anomali).all()
    
    summary_data = {k: v for k, v in stats}
    
    # Hitung tren per Kelurahan (untuk grafik)
    kelurahan_stats = db.session.query(
        MasterPelanggan.kelurahan, 
        func.count(DataSBRS.id)
    ).join(DataSBRS).filter(MasterPelanggan.ab == ab).group_by(MasterPelanggan.kelurahan).all()

    return render_template('sbrs_summary.html', 
                           summary=summary_data, 
                           kelurahan_data=kelurahan_stats,
                           current_ab=ab)

@sbrs_bp.route('/analisa')
def sbrs_analisa():
    """Halaman 2: Detail Analisa Kasus (Untuk Petugas)"""
    ab = request.args.get('ab', 'AB Sunter')
    kat = request.args.get('kategori') # Filter: ZERO, EKSTREM, atau TURUN

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
         MasterPetugas.peran == 'ANOMALI'
     )).filter(MasterPelanggan.ab == ab)

    if kat:
        query = query.filter(DataSBRS.kategori_anomali == kat)

    results = query.all()
    return render_template('sbrs_analisa.html', data=results, current_ab=ab)
