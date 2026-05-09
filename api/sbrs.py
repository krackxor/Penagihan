from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan, MasterPetugas, DataSBRS
from sqlalchemy import func, and_, case
from datetime import datetime

sbrs_bp = Blueprint('sbrs', __name__)

def get_current_periode():
    """Mendapatkan periode berjalan dalam format YYYYMM."""
    return datetime.now().strftime('%Y%m')

# --- KAMUS DATA SBRS (BERDASARKAN SOP PAM JAYA) ---
SKIP_LABELS = {
    '1A': 'Meter Buram', '1B': 'Meter Berembun', '1C': 'Meter Rusak',
    '2A': 'Meter Tidak Ada (Air Tidak Dipakai)', '2B': 'Meter Tidak Ada (Air Dipakai)',
    '3A': 'Rumah Kosong', '4A': 'Rumah Dibongkar', '4B': 'Meter Terendam',
    '4C': 'Alamat Tidak Ketemu', '5A': 'Tutup Bak Meter Berat', '5B': 'Meter Tertimbun',
    '5C': 'Meter Terhalang Barang Berat', '5D': 'Meter Dicor', '5E': 'Bak Meter Dikunci',
    '5F': 'Pagar Dikunci', '5G': 'Tidak Diizinkan Baca Meter'
}

TRBL_LABELS = {
    '1A': 'Meter Berembun', '1B': 'Meter Mati', '1C': 'Meter Buram', '1D': 'Segel Pabrik Putus/Tidak Ada',
    '2A': 'Meter Terbalik', '2B': 'Meter Dipindah', '2C': 'Meter Lepas', '2D': 'By Pass Meter',
    '2E': 'Meter Dicolok', '2F': 'Meter Tidak Normal/Meter Dicolok', '2G': 'Meter Rusak/Kaca Meter Pecah',
    '3A': 'Air Kecil/Mati', '4A': 'Pipa Dinas Sebelum Meter Bocor', '4B': 'Pipa Lama Keluar Air',
    '4C': 'Perlu Rehab Pipa Dinas (Pipa Gip)', '4D': 'Aksesoris Meter Rusak', '4E': 'Segel Dinas Diputus/Tidak Ada',
    '5A': 'Stand Tempel', '5B': 'No Seri Beda'
}

READ_LABELS = {
    '30/PE': 'System Estimate', '35/PS': 'Service Provider Estimate',
    '40/PE': 'Office Estimate', '60/SE': 'Regular', '80/PE': 'Billing Force'
}

@sbrs_bp.route('/summary')
def sbrs_summary():
    """
    Dashboard Ringkasan SBRS.
    Menampilkan statistik anomali dan Rincian Teknis Lapangan (Skip, Trouble, Read Method).
    """
    ab = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    # 1. Hitung total per kategori anomali (Zero, Ekstrem, Turun)
    stats_query = db.session.query(
        DataSBRS.kategori_anomali, 
        func.count(DataSBRS.id)
    ).select_from(DataSBRS).filter(DataSBRS.periode == periode_filter)
    
    if ab != 'all':
        stats_query = stats_query.filter(DataSBRS.ab == ab)
        
    stats = stats_query.group_by(DataSBRS.kategori_anomali).all()
    summary_data = {k: v for k, v in stats if k}
    
    # --- MULAI TARIK DATA JSONB ---
    
    # 2. Hitung SKIP CODE dari JSONB
    skip_stats = db.session.query(
        DataSBRS.raw_data['CMR_SKIP_CODE'].astext.label('code'),
        func.count(DataSBRS.id)
    ).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': skip_stats = skip_stats.filter(DataSBRS.ab == ab)
    skip_raw = skip_stats.group_by('code').all()

    # 3. Hitung TRUBLEM CODE dari JSONB
    trbl_stats = db.session.query(
        DataSBRS.raw_data['CMR_TRBL1_CODE'].astext.label('code'),
        func.count(DataSBRS.id)
    ).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': trbl_stats = trbl_stats.filter(DataSBRS.ab == ab)
    trbl_raw = trbl_stats.group_by('code').all()

    # 4. Hitung READ METHOD dari JSONB
    read_stats = db.session.query(
        DataSBRS.raw_data['READ_METHOD'].astext.label('method'),
        func.count(DataSBRS.id)
    ).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': read_stats = read_stats.filter(DataSBRS.ab == ab)
    read_raw = read_stats.group_by('method').all()

    # --- PROSES MAPPING KE BAHASA MANUSIA ---
    skip_final = [{"code": c, "desc": SKIP_LABELS.get(c, 'Lainnya'), "count": count} for c, count in skip_raw if c and c != 'None']
    trbl_final = [{"code": c, "desc": TRBL_LABELS.get(c, 'Lainnya'), "count": count} for c, count in trbl_raw if c and c != 'None']
    read_final = [{"code": c, "desc": READ_LABELS.get(c, 'Manual/Other'), "count": count} for c, count in read_raw if c and c != 'None']

    return render_template('sbrs_summary.html', 
                           summary=summary_data, 
                           skip_data=skip_final,
                           trbl_data=trbl_final,
                           read_data=read_final,
                           current_ab=ab,
                           periode_aktif=periode_filter)

@sbrs_bp.route('/analisa')
def sbrs_analisa():
    """
    Detail Analisa Kasus SBRS.
    Menampilkan daftar pelanggan yang butuh audit lapangan.
    """
    ab = request.args.get('ab', 'AB Sunter')
    kat = request.args.get('kategori')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    # Join ke MasterPetugas via kolom pcez yang sudah stabil
    query = db.session.query(
        DataSBRS.nomen,
        DataSBRS.nama, 
        DataSBRS.kelurahan,
        DataSBRS.pcez,
        DataSBRS.bulan_ini,
        DataSBRS.rata_rata,
        DataSBRS.kategori_anomali,
        DataSBRS.status_audit,
        MasterPetugas.nama_petugas.label('nama_petugas_anomali')
    ).select_from(DataSBRS)\
     .outerjoin(MasterPetugas, and_(
         DataSBRS.pcez == MasterPetugas.pcez, 
         MasterPetugas.peran == 'SBRS'
     )).filter(DataSBRS.periode == periode_filter)

    if ab != 'all':
        query = query.filter(DataSBRS.ab == ab)

    if kat and kat != 'all':
        query = query.filter(DataSBRS.kategori_anomali == kat)

    results = query.order_by(DataSBRS.bulan_ini.desc()).limit(1000).all()
    
    return render_template('sbrs_analisa.html', 
                           data=results, 
                           current_ab=ab, 
                           current_kat=kat,
                           periode_aktif=periode_filter)

@sbrs_bp.route('/api-stats')
def get_sbrs_api_stats():
    """API untuk pembaruan widget angka secara real-time di frontend."""
    ab = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    res = db.session.query(
        func.count(DataSBRS.id).label('total'),
        func.sum(case((DataSBRS.kategori_anomali == 'ZERO', 1), else_=0)).label('zero'),
        func.sum(case((DataSBRS.kategori_anomali == 'EKSTREM', 1), else_=0)).label('ekstrem'),
        func.sum(case((DataSBRS.kategori_anomali == 'TURUN', 1), else_=0)).label('turun')
    ).select_from(DataSBRS).filter(DataSBRS.periode == periode_filter)

    if ab != 'all':
        res = res.filter(DataSBRS.ab == ab)

    stats = res.first()

    return jsonify({
        "total": stats.total or 0,
        "zero": int(stats.zero or 0),
        "ekstrem": int(stats.ekstrem or 0),
        "turun": int(stats.turun or 0),
        "periode_text": periode_filter
    })
