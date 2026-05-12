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
    """
    # 1. Ambil Parameter Filter
    ab_filter = request.args.get('ab', 'all')
    periode_raw = request.args.get('periode') 
    
    # 2. Penentuan Periode (Dinamis, tidak dipaksa jika user ingin melihat semua)
    if not periode_raw or periode_raw.lower() == 'all':
        periode_bersih = 'all'
    else:
        periode_bersih = periode_raw.replace('-', '')

    # 3. Query Dasar
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
    
    # 4. Terapkan Filter Periode & Wilayah Secara Ketat
    if periode_bersih != 'all':
        query = query.filter(TransaksiTagihan.periode == periode_bersih)
        
    if ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)

    # 5. Eksekusi Query
    results = query.group_by(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.kelurahan,
        MasterPelanggan.pcez,
        MasterPetugas.nama_petugas,
        TransaksiTagihan.periode
    ).order_by(desc('total_nominal')).limit(500).all()

    # 6. LOGIKA "DATA READY": Cek apakah ada data yang ditemukan?
    # Jika hasil query kosong, maka data_ready = False
    data_ready = True if results else False

    # 7. Render ke Template dengan Flag data_ready
    return render_template(
        'top_500.html', 
        data=results, 
        current_ab=ab_filter, 
        periode_aktif=periode_bersih,
        data_ready=data_ready
    )

@top_500_bp.route('/api/stats')
def api_stats():
    """Rute API untuk widget summary."""
    ab_filter = request.args.get('ab', 'all')
    periode_raw = request.args.get('periode')
    
    if not periode_raw or periode_raw.lower() == 'all':
        periode_bersih = 'all'
    else:
        periode_bersih = periode_raw.replace('-', '')

    total_uang_query = db.session.query(func.sum(TransaksiTagihan.total_tagihan))\
                         .select_from(TransaksiTagihan)\
                         .join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
                         .filter(TransaksiTagihan.status_lunas == 0)

    if periode_bersih != 'all':
        total_uang_query = total_uang_query.filter(TransaksiTagihan.periode == periode_bersih)

    if ab_filter != 'all':
        total_uang_query = total_uang_query.filter(MasterPelanggan.ab == ab_filter)

    total_uang = total_uang_query.scalar() or 0

    return jsonify({
        "status": "success",
        "periode": periode_bersih,
        "total_nominal_rp": float(total_uang),
        "data_exists": True if total_uang > 0 else False
    })

@top_500_bp.route('/export')
def export_top500():
    """Export ke Excel dengan proteksi data kosong."""
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

    data_list = []
    if not results:
        data_list = [{"Pesan": "Data Belum Tersedia untuk periode/wilayah ini"}]
    else:
        for rank, r in enumerate(results, start=1):
            data_list.append({
                "Peringkat": rank,
                "Nomen": r.nomen,
                "Nama": r.nama,
                "Kelurahan": r.kelurahan,
                "PCEZ": r.pcez,
                "Petugas": r.nama_petugas or "-",
                "Nominal": float(r.total_nominal or 0),
                "Periode": r.periode
            })

    df = pl.DataFrame(data_list)
    output = io.BytesIO()
    df.write_excel(output)
    output.seek(0)
    
    return send_file(
        output, 
        download_name=f"Top_500_{periode_bersih}.xlsx",
        as_attachment=True, 
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
