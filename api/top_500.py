from flask import Blueprint, render_template, request, jsonify
from models import db, TransaksiTagihan, MasterPelanggan, MasterPetugas
from sqlalchemy import desc, func
from datetime import datetime

top_500_bp = Blueprint('top_500', __name__)

def get_current_periode():
    """Fungsi helper untuk mendapatkan periode bulan ini (Format YYYYMM)"""
    return datetime.now().strftime('%Y%m')

@top_500_bp.route('/')
def index():
    """Rute Utama Top 500 Tunggakan menggunakan Explicit Join ke MasterPelanggan"""
    ab_filter = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_bersih = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    # Trik JOIN: Menarik data dari TransaksiTagihan sekaligus menggandeng MasterPelanggan
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
     .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.periode == periode_bersih)
    
    # Filter 'ab' sekarang diarahkan ke MasterPelanggan (Tempat aslinya)
    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)

    # Group By & Order By (Penting untuk PostgreSQL)
    results = query.group_by(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode
    ).order_by(desc(func.sum(TransaksiTagihan.nominal))).limit(500).all()

    return render_template(
        'top_500.html', 
        data=results, 
        current_ab=ab_filter, 
        periode_aktif=periode_bersih
    )
