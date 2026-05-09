from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan, MasterPetugas, TransaksiTagihan, AnalisaAuditor
from sqlalchemy import func

# Inisialisasi Blueprint
monitoring_bp = Blueprint('monitoring', __name__)

@monitoring_bp.route('/')
def list_tagihan():
    """
    Halaman Utama Monitoring.
    Mendukung filter: AB, Rayon, Kelurahan, PCEZ.
    Default: AB Sunter.
    """
    # Ambil filter dari URL (Query String)
    ab_filter = request.args.get('ab', 'AB Sunter')
    rayon_filter = request.args.get('rayon')
    kel_filter = request.args.get('kelurahan')
    pcez_filter = request.args.get('pcez')
    
    # Query Dasar: Gabungkan Tagihan + Pelanggan + Nama Petugas
    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.pcez,
        MasterPelanggan.rayon,
        MasterPelanggan.kelurahan,
        MasterPelanggan.alamat,
        MasterPetugas.nama_petugas,
        func.sum(TransaksiTagihan.nominal).label('total_nominal'),
        func.count(TransaksiTagihan.id).label('jumlah_bulan')
    ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, MasterPelanggan.pcez == MasterPetugas.pcez)\
     .filter(TransaksiTagihan.status_lunas == 0)

    # Terapkan Filter Dinamis
    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)
    if rayon_filter:
        query = query.filter(MasterPelanggan.rayon == rayon_filter)
    if kel_filter:
        query = query.filter(MasterPelanggan.kelurahan == kel_filter)
    if pcez_filter:
        query = query.filter(MasterPelanggan.pcez == pcez_filter)

    # Grouping berdasarkan Nomen (Agar tagihan berekor jadi satu baris)
    results = query.group_by(TransaksiTagihan.nomen).order_by(func.sum(TransaksiTagihan.nominal).desc()).all()

    return render_template('monitoring.html', 
                           data=results, 
                           current_ab=ab_filter,
                           current_rayon=rayon_filter,
                           current_kel=kel_filter)

@monitoring_bp.route('/top-500')
def top_500():
    """Khusus untuk menarik 500 besar tunggakan di AB Sunter."""
    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPetugas.nama_petugas,
        func.sum(TransaksiTagihan.nominal).label('total_nominal')
    ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, MasterPelanggan.pcez == MasterPetugas.pcez)\
     .filter(TransaksiTagihan.status_lunas == 0, MasterPelanggan.ab == 'AB Sunter')\
     .group_by(TransaksiTagihan.nomen)\
     .order_by(func.sum(TransaksiTagihan.nominal).desc())\
     .limit(500)
    
    results = query.all()
    return render_template('top_500.html', data=results)

@monitoring_bp.route('/get-filters')
def get_filters():
    """
    API pendukung untuk mengisi dropdown filter di halaman web.
    Mengambil daftar Kelurahan dan Rayon yang tersedia di database.
    """
    ab = request.args.get('ab', 'AB Sunter')
    
    kelurahans = db.session.query(MasterPelanggan.kelurahan).filter(MasterPelanggan.ab == ab).distinct().all()
    rayons = db.session.query(MasterPelanggan.rayon).filter(MasterPelanggan.ab == ab).distinct().all()
    
    return jsonify({
        "kelurahan": [k[0] for k in kelurahans if k[0]],
        "rayon": [r[0] for r in rayons if r[0]]
    })

@monitoring_bp.route('/summary')
def summary_stats():
    """Menghitung ringkasan cepat untuk Dashboard."""
    ab = request.args.get('ab', 'AB Sunter')
    
    total_duit = db.session.query(func.sum(TransaksiTagihan.nominal))\
                   .join(MasterPelanggan)\
                   .filter(MasterPelanggan.ab == ab, TransaksiTagihan.status_lunas == 0).scalar() or 0
                   
    total_plg = db.session.query(func.count(func.distinct(TransaksiTagihan.nomen)))\
                  .join(MasterPelanggan)\
                  .filter(MasterPelanggan.ab == ab, TransaksiTagihan.status_lunas == 0).scalar() or 0
    
    return jsonify({
        "total_nominal": total_duit,
        "total_pelanggan": total_plg
    })
