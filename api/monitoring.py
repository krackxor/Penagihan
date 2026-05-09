from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan, MasterPetugas, TransaksiTagihan
from sqlalchemy import func
from datetime import datetime

# Inisialisasi Blueprint
monitoring_bp = Blueprint('monitoring', __name__)

def get_current_periode():
    """Fungsi pembantu untuk mendapatkan periode bulan berjalan (YYYYMM)."""
    return datetime.now().strftime('%Y%m')

@monitoring_bp.route('/')
def list_tagihan():
    """
    Halaman Utama Monitoring dengan Filter Wilayah dan Periode Dinamis.
    """
    ab_filter = request.args.get('ab', 'AB Sunter')
    rayon_filter = request.args.get('rayon')
    kel_filter = request.args.get('kelurahan')
    pcez_filter = request.args.get('pcez')
    
    # Ambil Periode dari Kalender (Default: Bulan Sekarang)
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    # Query Dasar: Join Pelanggan + Tagihan + Petugas
    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.pcez,
        MasterPelanggan.rayon,
        MasterPelanggan.kelurahan,
        MasterPelanggan.alamat,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode,
        func.sum(TransaksiTagihan.nominal).label('total_nominal'),
        func.count(TransaksiTagihan.id).label('jumlah_lembar')
    ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, (MasterPelanggan.pcez == MasterPetugas.pcez) & (MasterPetugas.peran == 'TAGIHAN'))\
     .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.periode == periode_filter)

    # Filter Wilayah Dinamis
    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)
    if rayon_filter:
        query = query.filter(MasterPelanggan.rayon == rayon_filter)
    if kel_filter:
        query = query.filter(MasterPelanggan.kelurahan == kel_filter)
    if pcez_filter:
        query = query.filter(MasterPelanggan.pcez == pcez_filter)

    # PostgreSQL mewajibkan semua kolom non-agregat masuk ke group_by
    results = query.group_by(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.pcez,
        MasterPelanggan.rayon,
        MasterPelanggan.kelurahan,
        MasterPelanggan.alamat,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode
    ).order_by(func.sum(TransaksiTagihan.nominal).desc()).all()

    return render_template('monitoring.html', 
                           data=results, 
                           current_ab=ab_filter,
                           current_rayon=rayon_filter,
                           current_kel=kel_filter,
                           periode_aktif=periode_filter)

@monitoring_bp.route('/top-500')
def top_500():
    """Menarik 500 besar tunggakan berdasarkan periode yang dipilih."""
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode,
        func.sum(TransaksiTagihan.nominal).label('total_nominal')
    ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, (MasterPelanggan.pcez == MasterPetugas.pcez) & (MasterPetugas.peran == 'TAGIHAN'))\
     .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.periode == periode_filter)\
     .group_by(
         TransaksiTagihan.nomen,
         MasterPelanggan.nama,
         MasterPelanggan.kelurahan,
         MasterPetugas.nama_petugas,
         TransaksiTagihan.periode
     )\
     .order_by(func.sum(TransaksiTagihan.nominal).desc())\
     .limit(500)
    
    results = query.all()
    return render_template('monitoring_top500.html', data=results, periode_aktif=periode_filter)

@monitoring_bp.route('/summary')
def summary_stats():
    """API Ringkasan untuk Kartu Statistik (Total Rupiah & Lembar Tagihan)."""
    ab = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    stats = db.session.query(
        func.sum(TransaksiTagihan.nominal),
        func.count(TransaksiTagihan.id)
    ).join(MasterPelanggan)\
     .filter(MasterPelanggan.ab == ab, 
             TransaksiTagihan.periode == periode_filter, 
             TransaksiTagihan.status_lunas == 0).first()
                   
    return jsonify({
        "total_nominal": float(stats[0] or 0),
        "total_lembar": stats[1] or 0,
        "periode_text": periode_filter
    })

@monitoring_bp.route('/get-filters')
def get_filters():
    """API pendukung filter dropdown wilayah."""
    ab = request.args.get('ab', 'AB Sunter')
    kelurahans = db.session.query(MasterPelanggan.kelurahan).filter(MasterPelanggan.ab == ab).distinct().all()
    rayons = db.session.query(MasterPelanggan.rayon).filter(MasterPelanggan.ab == ab).distinct().all()
    
    return jsonify({
        "kelurahan": [k[0] for k in kelurahans if k[0]],
        "rayon": [r[0] for r in rayons if r[0]]
    })
