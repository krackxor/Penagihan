from flask import Blueprint, render_template, request, jsonify
from models import db, TransaksiTagihan, MasterPetugas
from sqlalchemy import desc
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
    Mengambil data dari TransaksiTagihan (Upload MC) dan mengurutkannya dari tagihan terbesar.
    """
    # 1. Ambil Parameter Filter dari URL
    ab_filter = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode') # Format dari input type="month" (YYYY-MM)
    
    # 2. Pembersihan Format Periode (Ubah 2026-03 menjadi 202603)
    if periode_raw:
        periode_bersih = periode_raw.replace('-', '')
    else:
        # Jika tidak ada filter, gunakan bulan berjalan
        periode_bersih = get_current_periode()

    # 3. Query Data dari Database
    # Query dasar ke tabel TransaksiTagihan (Tempat data MC bermuara)
    query = TransaksiTagihan.query.filter(TransaksiTagihan.periode == periode_bersih)
    
    # Terapkan filter wilayah jika bukan 'all'
    if ab_filter != 'all':
        query = query.filter(TransaksiTagihan.ab == ab_filter)

    # 4. Pengurutan & Pembatasan Data
    # Urutkan berdasarkan nominal tagihan terbesar (descending) dan batasi 500 data
    top_data = query.order_by(desc(TransaksiTagihan.total_nominal)).limit(500).all()

    # 5. Siapkan Data untuk Frontend (Template HTML)
    results = []
    
    # Ambil data MasterPetugas sekaligus (Mapping PCEZ -> Nama Petugas)
    # Ini jauh lebih cepat daripada query petugas satu per satu di dalam looping
    petugas_records = MasterPetugas.query.filter_by(peran='SBRS').all()
    petugas_map = {p.pcez: p.nama_petugas for p in petugas_records}

    for item in top_data:
        raw = item.raw_data or {}
        
        # Ambil nama petugas dari mapping (jika pcez cocok)
        nama_petugas = petugas_map.get(item.pcez, 'Belum Diplot')

        results.append({
            "nomen": item.nomen,
            "nama": item.nama,
            "kelurahan": item.kelurahan,
            "pcez": item.pcez,
            "total_nominal": item.total_nominal, # Angka asli dari MC (misal: 1660.0)
            "nama_petugas": nama_petugas,
            "raw_data": raw
        })

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
    Rute tambahan (API JSON) jika sewaktu-waktu frontend butuh data summary Top 500 
    tanpa merender ulang halaman (misal untuk Chart atau Widget Dashboard).
    """
    ab_filter = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_bersih = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    query = TransaksiTagihan.query.filter(TransaksiTagihan.periode == periode_bersih)
    if ab_filter != 'all':
        query = query.filter(TransaksiTagihan.ab == ab_filter)

    # Hitung total pelanggan di Top 500 dan total akumulasi uangnya
    total_pelanggan = query.count()
    total_uang_raw = db.session.query(db.func.sum(TransaksiTagihan.total_nominal)).filter(TransaksiTagihan.periode == periode_bersih)
    
    if ab_filter != 'all':
        total_uang_raw = total_uang_raw.filter(TransaksiTagihan.ab == ab_filter)
        
    total_uang = total_uang_raw.scalar() or 0

    return jsonify({
        "status": "success",
        "periode": periode_bersih,
        "wilayah": ab_filter,
        "total_tunggakan_tercatat": int(total_pelanggan),
        "total_nominal_rp": float(total_uang)
    })
