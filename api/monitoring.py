from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan, MasterPetugas, TransaksiTagihan
from sqlalchemy import func
from datetime import datetime

monitoring_bp = Blueprint('monitoring', __name__)

def get_current_periode():
    """Fungsi pembantu untuk mendapatkan periode bulan berjalan (YYYYMM)."""
    return datetime.now().strftime('%Y%m')

@monitoring_bp.route('/')
def list_tagihan():
    """Halaman Utama Monitoring dengan Fix Explicit Join."""
    ab_filter = request.args.get('ab', 'AB Sunter')
    rayon_filter = request.args.get('rayon')
    kel_filter = request.args.get('kelurahan')
    pcez_filter = request.args.get('pcez')
    
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    # PERBAIKAN: Menambahkan .select_from(TransaksiTagihan) agar PostgreSQL tidak bingung
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
    ).select_from(TransaksiTagihan)\
     .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, (MasterPelanggan.pcez == MasterPetugas.pcez) & (MasterPetugas.peran == 'TAGIHAN'))\
     .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.periode == periode_filter)

    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)
    if rayon_filter:
        query = query.filter(MasterPelanggan.rayon == rayon_filter)
    if kel_filter:
        query = query.filter(MasterPelanggan.kelurahan == kel_filter)
    if pcez_filter:
        query = query.filter(MasterPelanggan.pcez == pcez_filter)

    # Pastikan group_by mencakup semua kolom non-agregat untuk standar PostgreSQL
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

    # KEMBALI KE NAMA ASLI BOS (monitoring.html)
    return render_template('monitoring.html', 
                           data=results, 
                           current_ab=ab_filter,
                           current_rayon=rayon_filter,
                           current_kel=kel_filter,
                           periode_aktif=periode_filter)

@monitoring_bp.route('/top-500')
def top_500():
    """Top 500 Tunggakan dengan Fix Explicit Join."""
    ab_filter = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode,
        func.sum(TransaksiTagihan.nominal).label('total_nominal')
    ).select_from(TransaksiTagihan)\
     .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, (MasterPelanggan.pcez == MasterPetugas.pcez) & (MasterPetugas.peran == 'TAGIHAN'))\
     .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.periode == periode_filter)
    
    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)

    results = query.group_by(
         TransaksiTagihan.nomen,
         MasterPelanggan.nama,
         MasterPelanggan.kelurahan,
         MasterPelanggan.pcez,
         MasterPetugas.nama_petugas,
         TransaksiTagihan.periode
     ).order_by(func.sum(TransaksiTagihan.nominal).desc()).limit(500).all()
    
    # KEMBALI KE NAMA ASLI BOS (top_500.html)
    return render_template('top_500.html', 
                           data=results, 
                           current_ab=ab_filter, 
                           periode_aktif=periode_filter)

@monitoring_bp.route('/summary')
def summary_stats():
    """API Summary dengan Fix Explicit Join."""
    ab = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    stats = db.session.query(
        func.sum(TransaksiTagihan.nominal),
        func.count(TransaksiTagihan.id)
    ).select_from(TransaksiTagihan)\
     .join(MasterPelanggan)\
     .filter(MasterPelanggan.ab == ab if ab != 'all' else True, 
             TransaksiTagihan.periode == periode_filter, 
             TransaksiTagihan.status_lunas == 0).first()

    total_plg = db.session.query(func.count(func.distinct(TransaksiTagihan.nomen)))\
                  .select_from(TransaksiTagihan)\
                  .join(MasterPelanggan)\
                  .filter(MasterPelanggan.ab == ab if ab != 'all' else True, 
                          TransaksiTagihan.periode == periode_filter, 
                          TransaksiTagihan.status_lunas == 0).scalar() or 0
                   
    return jsonify({
        "total_nominal": float(stats[0] or 0),
        "total_lembar": stats[1] or 0,
        "total_pelanggan": total_plg,
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
