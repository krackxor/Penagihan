import io
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
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
    Dashboard Eksekutif SBRS.
    Menampilkan Total Nomen, Zero Lama/Baru, dan Rincian Teknis dengan Filter Cycle.
    """
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()
    
    # Kalkulasi periode sebelumnya untuk melacak status Zero Lama
    try:
        yyyy = int(periode_filter[:4])
        mm = int(periode_filter[4:])
        if mm == 1:
            prev_periode = f"{yyyy-1}12"
        else:
            prev_periode = f"{yyyy}{mm-1:02d}"
    except:
        prev_periode = periode_filter

    # --- 1. HITUNG STATISTIK DASAR & TOTAL NOMEN ---
    base_q = DataSBRS.query.filter(DataSBRS.periode == periode_filter)
    if ab != 'all': base_q = base_q.filter(DataSBRS.ab == ab)
    if cycle != 'all': base_q = base_q.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    
    total_nomen = base_q.count()

    stats_query = db.session.query(
        DataSBRS.kategori_anomali, func.count(DataSBRS.id)
    ).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': stats_query = stats_query.filter(DataSBRS.ab == ab)
    if cycle != 'all': stats_query = stats_query.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    
    summary_dict = {k: v for k, v in stats_query.group_by(DataSBRS.kategori_anomali).all() if k}

    # --- 2. DETEKSI ZERO LAMA VS ZERO BARU ---
    zero_lama_q = db.session.query(func.count(DataSBRS.id)).filter(
        DataSBRS.periode == periode_filter,
        DataSBRS.kategori_anomali == 'ZERO',
        DataSBRS.nomen.in_(
            db.session.query(DataSBRS.nomen).filter(
                DataSBRS.periode == prev_periode, 
                DataSBRS.kategori_anomali == 'ZERO'
            )
        )
    )
    if ab != 'all': zero_lama_q = zero_lama_q.filter(DataSBRS.ab == ab)
    if cycle != 'all': zero_lama_q = zero_lama_q.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    
    zero_lama = zero_lama_q.scalar() or 0
    zero_baru = summary_dict.get('ZERO', 0) - zero_lama

    # --- 3. TARIK DATA JSONB & MAPPING KODE ---
    skip_stats = db.session.query(DataSBRS.raw_data['CMR_SKIP_CODE'].astext.label('code'), func.count(DataSBRS.id)).filter(DataSBRS.periode == periode_filter)
    trbl_stats = db.session.query(DataSBRS.raw_data['CMR_TRBL1_CODE'].astext.label('code'), func.count(DataSBRS.id)).filter(DataSBRS.periode == periode_filter)
    read_stats = db.session.query(DataSBRS.raw_data['READ_METHOD'].astext.label('method'), func.count(DataSBRS.id)).filter(DataSBRS.periode == periode_filter)

    if ab != 'all':
        skip_stats = skip_stats.filter(DataSBRS.ab == ab)
        trbl_stats = trbl_stats.filter(DataSBRS.ab == ab)
        read_stats = read_stats.filter(DataSBRS.ab == ab)
        
    if cycle != 'all':
        skip_stats = skip_stats.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
        trbl_stats = trbl_stats.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
        read_stats = read_stats.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)

    skip_raw = skip_stats.group_by('code').all()
    trbl_raw = trbl_stats.group_by('code').all()
    read_raw = read_stats.group_by('method').all()

    skip_final = [{"code": c, "desc": SKIP_LABELS.get(c, 'Lainnya'), "count": count} for c, count in skip_raw if c and c != 'None']
    trbl_final = [{"code": c, "desc": TRBL_LABELS.get(c, 'Lainnya'), "count": count} for c, count in trbl_raw if c and c != 'None']
    read_final = [{"code": c, "desc": READ_LABELS.get(c, 'Manual/Other'), "count": count} for c, count in read_raw if c and c != 'None']

    # --- 4. KUMPULKAN KE DALAM MASTER OBJECT ---
    master_totals = {
        "total_nomen": total_nomen,
        "zero_baru": zero_baru,
        "zero_lama": zero_lama,
        "total_skip": sum(i['count'] for i in skip_final),
        "total_trbl": sum(i['count'] for i in trbl_final),
        "ekstrem": summary_dict.get('EKSTREM', 0),
        "turun": summary_dict.get('TURUN', 0)
    }

    # --- 5. TARIK SEBARAN KELURAHAN ---
    kelurahan_stats = db.session.query(DataSBRS.kelurahan, func.count(DataSBRS.id)).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': kelurahan_stats = kelurahan_stats.filter(DataSBRS.ab == ab)
    if cycle != 'all': kelurahan_stats = kelurahan_stats.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    kelurahan_results = kelurahan_stats.group_by(DataSBRS.kelurahan).order_by(func.count(DataSBRS.id).desc()).all()

    # --- 6. SIAPKAN LIST CYCLE UNTUK DROPDOWN ---
    available_cycles = db.session.query(DataSBRS.raw_data['CYCLE'].astext).filter(DataSBRS.periode == periode_filter).distinct().all()
    cycles_list = sorted([c[0] for c in available_cycles if c[0] and c[0] != 'None'])

    return render_template('sbrs_summary.html', 
                           totals=master_totals, 
                           cycles=cycles_list,
                           current_cycle=cycle,
                           skip_data=skip_final,
                           trbl_data=trbl_final,
                           read_data=read_final,
                           kelurahan_data=kelurahan_results,
                           current_ab=ab,
                           periode_aktif=periode_filter)

@sbrs_bp.route('/analisa')
def sbrs_analisa():
    """
    Detail Analisa Kasus SBRS.
    Dilengkapi filter Cycle agar pencarian target audit lebih spesifik.
    """
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    kat = request.args.get('kategori')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

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
    if cycle != 'all':
        query = query.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    if kat and kat != 'all':
        query = query.filter(DataSBRS.kategori_anomali == kat)

    results = query.order_by(DataSBRS.bulan_ini.desc()).limit(1000).all()
    
    return render_template('sbrs_analisa.html', 
                           data=results, 
                           current_ab=ab,
                           current_cycle=cycle,
                           current_kat=kat,
                           periode_aktif=periode_filter)

# ==========================================
# FITUR BARU: MESIN EXPORT DATA KE EXCEL
# ==========================================

@sbrs_bp.route('/export/summary')
def export_summary():
    """Mengunduh Dashboard Ringkasan ke format Excel (Multi-Sheet)."""
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    try:
        yyyy = int(periode_filter[:4])
        mm = int(periode_filter[4:])
        prev_periode = f"{yyyy-1}12" if mm == 1 else f"{yyyy}{mm-1:02d}"
    except:
        prev_periode = periode_filter

    # Tarik Data Identik dengan Summary
    base_q = DataSBRS.query.filter(DataSBRS.periode == periode_filter)
    if ab != 'all': base_q = base_q.filter(DataSBRS.ab == ab)
    if cycle != 'all': base_q = base_q.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    total_nomen = base_q.count()

    stats_query = db.session.query(DataSBRS.kategori_anomali, func.count(DataSBRS.id)).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': stats_query = stats_query.filter(DataSBRS.ab == ab)
    if cycle != 'all': stats_query = stats_query.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    summary_dict = {k: v for k, v in stats_query.group_by(DataSBRS.kategori_anomali).all() if k}

    zero_lama_q = db.session.query(func.count(DataSBRS.id)).filter(
        DataSBRS.periode == periode_filter, DataSBRS.kategori_anomali == 'ZERO',
        DataSBRS.nomen.in_(db.session.query(DataSBRS.nomen).filter(DataSBRS.periode == prev_periode, DataSBRS.kategori_anomali == 'ZERO'))
    )
    if ab != 'all': zero_lama_q = zero_lama_q.filter(DataSBRS.ab == ab)
    if cycle != 'all': zero_lama_q = zero_lama_q.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    zero_lama = zero_lama_q.scalar() or 0
    zero_baru = summary_dict.get('ZERO', 0) - zero_lama

    skip_stats = db.session.query(DataSBRS.raw_data['CMR_SKIP_CODE'].astext.label('code'), func.count(DataSBRS.id)).filter(DataSBRS.periode == periode_filter)
    if ab != 'all': skip_stats = skip_stats.filter(DataSBRS.ab == ab)
    if cycle != 'all': skip_stats = skip_stats.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    skip_final = [{"Kode": c, "Keterangan": SKIP_LABELS.get(c, 'Lainnya'), "Total": count} for c, count in skip_stats.group_by('code').all() if c and c != 'None']

    # Pembentukan File Excel
    df_utama = pd.DataFrame([
        {"Indikator": "Total Data Nomen", "Jumlah": total_nomen},
        {"Indikator": "Zero Baru (Macet)", "Jumlah": zero_baru},
        {"Indikator": "Zero Lama (Kronis)", "Jumlah": zero_lama},
        {"Indikator": "Total Skip", "Jumlah": sum(i['Total'] for i in skip_final)},
        {"Indikator": "Ekstrem", "Jumlah": summary_dict.get('EKSTREM', 0)},
        {"Indikator": "Turun Drastis", "Jumlah": summary_dict.get('TURUN', 0)},
    ])
    df_skip = pd.DataFrame(skip_final)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_utama.to_excel(writer, sheet_name='Ringkasan_Utama', index=False)
        if not df_skip.empty: df_skip.to_excel(writer, sheet_name='Rincian_Skip', index=False)
    
    output.seek(0)
    nama_file = f"Laporan_SBRS_Summary_{ab}_Cycle_{cycle}_{periode_filter}.xlsx"
    return send_file(output, download_name=nama_file, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@sbrs_bp.route('/export/analisa')
def export_analisa():
    """Mengunduh Hasil Append Data (Seluruh Rincian Pelanggan) ke format Excel."""
    ab = request.args.get('ab', 'AB Sunter')
    cycle = request.args.get('cycle', 'all')
    kat = request.args.get('kategori', 'all')
    periode_raw = request.args.get('periode')
    periode_filter = periode_raw.replace('-', '') if periode_raw else get_current_periode()

    query = db.session.query(
        DataSBRS.nomen, DataSBRS.nama, DataSBRS.kelurahan, DataSBRS.pcez, 
        DataSBRS.stand_meter, DataSBRS.bulan_ini, DataSBRS.rata_rata, 
        DataSBRS.kategori_anomali, DataSBRS.raw_data
    ).filter(DataSBRS.periode == periode_filter)

    if ab != 'all': query = query.filter(DataSBRS.ab == ab)
    if cycle != 'all': query = query.filter(DataSBRS.raw_data['CYCLE'].astext == cycle)
    if kat != 'all': query = query.filter(DataSBRS.kategori_anomali == kat)

    results = query.all()
    
    data_list = []
    for r in results:
        raw = r.raw_data or {}
        data_list.append({
            "Nomen": r.nomen,
            "Nama Pelanggan": r.nama,
            "Kelurahan": r.kelurahan,
            "Wilayah PCEZ": r.pcez,
            "Cycle": raw.get('CYCLE', '-'),
            "Meter Bulan Ini": r.stand_meter,
            "Pakai (m3)": r.bulan_ini,
            "Rata-rata (m3)": r.rata_rata,
            "Kategori Anomali": r.kategori_anomali,
            "Skip Code": raw.get('CMR_SKIP_CODE', ''),
            "Trouble Code": raw.get('CMR_TRBL1_CODE', ''),
            "Metode Baca": raw.get('READ_METHOD', '')
        })

    df = pd.DataFrame(data_list)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Data_Analisa_SBRS', index=False)
    
    output.seek(0)
    nama_file = f"Data_SBRS_Append_{ab}_Cycle_{cycle}_{periode_filter}.xlsx"
    return send_file(output, download_name=nama_file, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
