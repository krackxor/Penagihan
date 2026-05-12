import io
import polars as pl
from flask import Blueprint, render_template, request, jsonify, send_file
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
    Rute Utama Top 500 Tunggakan (Terintegrasi dengan Sinergi V18).
    Menggunakan Explicit Join murni, tanpa menarik raw_data (JSONB) agar loading super cepat.
    """
    # 1. Ambil Parameter Filter dari URL (Default: 'all')
    ab_filter = request.args.get('ab', 'all')
    periode_raw = request.args.get('periode') 
    
    # 2. Pembersihan Format Periode Dinamis
    if not periode_raw or periode_raw.lower() == 'all':
        periode_bersih = 'all'
    else:
        periode_bersih = periode_raw.replace('-', '')

    # 3. Query Data dengan Trik Explicit JOIN & Filter Petugas TAGIHAN
    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode,
        func.sum(TransaksiTagihan.total_tagihan).label('total_nominal')
    ).select_from(TransaksiTagihan)\
     .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, (MasterPelanggan.pcez == MasterPetugas.pcez) & (MasterPetugas.peran == 'TAGIHAN'))\
     .filter(TransaksiTagihan.status_lunas == 0)
    
    # 4. Terapkan Filter Dinamis
    if periode_bersih != 'all':
        query = query.filter(TransaksiTagihan.periode == periode_bersih)
        
    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)

    # 5. Group By & Order By
    results = query.group_by(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode
    ).order_by(desc('total_nominal')).limit(500).all()

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
    Menghitung total uang tunggakan dan jumlah pelanggan yang belum lunas.
    """
    ab_filter = request.args.get('ab', 'all')
    periode_raw = request.args.get('periode')
    
    if not periode_raw or periode_raw.lower() == 'all':
        periode_bersih = 'all'
    else:
        periode_bersih = periode_raw.replace('-', '')

    # Query Base
    total_uang_query = db.session.query(func.sum(TransaksiTagihan.total_tagihan))\
                         .select_from(TransaksiTagihan)\
                         .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
                         .filter(TransaksiTagihan.status_lunas == 0)

    total_pelanggan_query = db.session.query(func.count(func.distinct(TransaksiTagihan.nomen)))\
                              .select_from(TransaksiTagihan)\
                              .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
                              .filter(TransaksiTagihan.status_lunas == 0)

    # Terapkan filter dinamis
    if periode_bersih != 'all':
        total_uang_query = total_uang_query.filter(TransaksiTagihan.periode == periode_bersih)
        total_pelanggan_query = total_pelanggan_query.filter(TransaksiTagihan.periode == periode_bersih)

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

@top_500_bp.route('/export')
def export_top500():
    """
    Export Data Top 500 ke Excel menggunakan Polars Engine!
    (Terlindungi dari jebakan list kosong)
    """
    ab_filter = request.args.get('ab', 'all')
    periode_raw = request.args.get('periode') 
    
    if not periode_raw or periode_raw.lower() == 'all':
        periode_bersih = 'all'
    else:
        periode_bersih = periode_raw.replace('-', '')

    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode,
        func.sum(TransaksiTagihan.total_tagihan).label('total_nominal')
    ).select_from(TransaksiTagihan)\
     .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .outerjoin(MasterPetugas, (MasterPelanggan.pcez == MasterPetugas.pcez) & (MasterPetugas.peran == 'TAGIHAN'))\
     .filter(TransaksiTagihan.status_lunas == 0)
    
    if periode_bersih != 'all':
        query = query.filter(TransaksiTagihan.periode == periode_bersih)

    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)

    results = query.group_by(
        TransaksiTagihan.nomen, MasterPelanggan.nama, MasterPelanggan.kelurahan,
        MasterPelanggan.pcez, MasterPetugas.nama_petugas, TransaksiTagihan.periode
    ).order_by(desc('total_nominal')).limit(500).all()

    # Mapping hasil query ke dalam list dictionary untuk Polars
    data_list = []
    for rank, r in enumerate(results, start=1):
        data_list.append({
            "Peringkat": rank,
            "Nomen Sinergi": r.nomen,
            "Nama Pelanggan": r.nama,
            "Kelurahan": r.kelurahan,
            "Wilayah PCEZ": r.pcez,
            "Petugas Lapangan": r.nama_petugas or "Belum Diatur",
            "Total Tunggakan (Rp)": float(r.total_nominal or 0),
            "Periode": r.periode
        })

    # PROTEKSI V18: Cegah Polars Crash jika data kosong (Tidak ada tunggakan)
    if not data_list:
        data_list = [{"Info": "Tidak ada data tunggakan untuk filter wilayah/periode ini"}]

    # Konversi ke Excel menggunakan mesin Polars
    df = pl.DataFrame(data_list)
    output = io.BytesIO()
    df.write_excel(output, worksheet="Top_500_Pareto")
    output.seek(0)
    
    nama_file = f"Data_Top_500_{ab_filter}_{periode_bersih}.xlsx"
    return send_file(
        output, 
        download_name=nama_file, 
        as_attachment=True, 
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
