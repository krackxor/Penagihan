from flask import Blueprint, render_template, request, jsonify
from models import db, TransaksiTagihan, MasterPelanggan, MasterPetugas
from sqlalchemy import desc, func
from datetime import datetime

# Inisialisasi Blueprint untuk rute Top 500
top_500_bp = Blueprint('top_500', __name__)

def get_current_periode():
    """Fungsi helper untuk mendapatkan periode bulan ini (Format YYYYMM)"""
    return datetime.now().strftime('%Y%m')

@top_500_bp.route('/')
def index():
    """
    Rute Utama Top 500 Tunggakan.
    Menggunakan teknik Explicit Join agar bisa menarik nama wilayah (ab) dari MasterPelanggan,
    dan nilai nominal tagihan dari TransaksiTagihan (File MC).
    """
    # 1. Ambil Parameter Filter dari URL
    ab_filter = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode') 
    
    # 2. Pembersihan Format Periode (Ubah 2026-03 menjadi 202603)
    periode_bersih = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    # 3. Query Data dengan Trik Explicit JOIN (Standar PostgreSQL)
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
    
    # 4. Filter 'ab' diarahkan ke MasterPelanggan (Tempat aslinya)
    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)

    # 5. Group By & Order By
    # Group By wajib mencakup semua kolom yang bukan agregat (sum/count) agar tidak error di PostgreSQL
    results = query.group_by(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode
    ).order_by(desc(func.sum(TransaksiTagihan.nominal))).limit(500).all()

    # 6. Render ke Template
    return render_template(
        'top_500.html', 
        data=results, 
        current_ab=ab_filter, 
        periode_aktif=periode_bersih
    )

@top_500_bp.route('/api/stats')
def api_stats():
    """
    Rute tambahan (API JSON) untuk widget summary Top 500.
    Menghitung total tunggakan dan total pelanggan di bulan tersebut.
    """
    ab_filter = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_bersih = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    # Query untuk Total Nominal Uang Tunggakan
    total_uang_query = db.session.query(func.sum(TransaksiTagihan.nominal))\
                         .select_from(TransaksiTagihan)\
                         .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
                         .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.periode == periode_bersih)

    # Query untuk Total Pelanggan Unik yang Menunggak
    total_pelanggan_query = db.session.query(func.count(func.distinct(TransaksiTagihan.nomen)))\
                              .select_from(TransaksiTagihan)\
                              .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
                              .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.periode == periode_bersih)

    # Terapkan filter wilayah
    if ab_filter != 'all':
        total_uang_query = total_uang_query.filter(MasterPelanggan.ab == ab_filter)
        total_pelanggan_query = total_pelanggan_query.filter(MasterPelanggan.ab == ab_filter)

    total_uang = total_uang_query.scalar() or 0
    total_pelanggan = total_pelanggan_query.scalar() or 0

    return jsonify({
        "status": "success",
        "periode": periode_bersih,
        "wilayah": ab_filter,
        "total_tunggakan_tercatat": int(total_pelanggan),
        "total_nominal_rp": float(total_uang)
    })
