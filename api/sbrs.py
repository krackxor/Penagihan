from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan, MasterPetugas, DataSBRS
from sqlalchemy import func, and_, case
from datetime import datetime

sbrs_bp = Blueprint('sbrs', __name__)

def get_current_periode():
    """Mendapatkan periode berjalan dalam format YYYYMM."""
    return datetime.now().strftime('%Y%m')

@sbrs_bp.route('/summary')
def sbrs_summary():
    """
    Dashboard Ringkasan SBRS.
    Menampilkan statistik anomali (Zero, Ekstrem, Turun) per Periode.
    """
    ab = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    # PERBAIKAN: Gunakan select_from agar tidak InvalidRequestError
    # Hitung total per kategori anomali
    stats_query = db.session.query(
        DataSBRS.kategori_anomali, 
        func.count(DataSBRS.id)
    ).select_from(DataSBRS).filter(
        DataSBRS.periode == periode_filter
    )
    
    if ab != 'all':
        stats_query = stats_query.filter(DataSBRS.ab == ab if hasattr(DataSBRS, 'ab') else True)
        
    stats = stats_query.group_by(DataSBRS.kategori_anomali).all()
    summary_data = {k: v for k, v in stats if k}
    
    # Hitung sebaran anomali per Kelurahan
    kelurahan_stats = db.session.query(
        DataSBRS.kelurahan, 
        func.count(DataSBRS.id)
    ).select_from(DataSBRS).filter(
        DataSBRS.periode == periode_filter
    ).group_by(DataSBRS.kelurahan)\
     .order_by(func.count(DataSBRS.id).desc()).all()

    return render_template('summary_sbrs.html', 
                           summary=summary_data, 
                           kelurahan_data=kelurahan_stats,
                           current_ab=ab,
                           periode_aktif=periode_filter)

@sbrs_bp.route('/analisa')
def sbrs_analisa():
    """
    Detail Analisa Kasus SBRS.
    Daftar pelanggan yang butuh audit lapangan karena pemakaian tidak wajar.
    """
    ab = request.args.get('ab', 'AB Sunter')
    kat = request.args.get('kategori')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    # PERBAIKAN: Gunakan select_from dan join eksplisit
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
         MasterPetugas.peran == 'SBRS' # Sesuaikan dengan peran di MasterPetugas
     )).filter(DataSBRS.periode == periode_filter)

    if ab != 'all':
        query = query.filter(DataSBRS.ab == ab if hasattr(DataSBRS, 'ab') else True)

    if kat and kat != 'all':
        query = query.filter(DataSBRS.kategori_anomali == kat)

    results = query.order_by(DataSBRS.bulan_ini.desc()).limit(1000).all()
    
    return render_template('analisa_sbrs.html', 
                           data=results, 
                           current_ab=ab, 
                           current_kat=kat,
                           periode_aktif=periode_filter)

@sbrs_bp.route('/api-stats')
def get_sbrs_api_stats():
    """API untuk memperbarui widget angka secara real-time di frontend."""
    ab = request.args.get('ab', 'AB Sunter')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    res = db.session.query(
        func.count(DataSBRS.id).label('total'),
        func.sum(case((DataSBRS.kategori_anomali == 'ZERO', 1), else_=0)).label('zero'),
        func.sum(case((DataSBRS.kategori_anomali == 'EKSTREM', 1), else_=0)).label('ekstrem'),
        func.sum(case((DataSBRS.kategori_anomali == 'TURUN', 1), else_=0)).label('turun')
    ).select_from(DataSBRS).filter(DataSBRS.periode == periode_filter).first()

    return jsonify({
        "total": res.total or 0,
        "zero": int(res.zero or 0),
        "ekstrem": int(res.ekstrem or 0),
        "turun": int(res.turun or 0),
        "periode_text": periode_filter
    })
