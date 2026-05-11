from flask import Blueprint, render_template, request
from datetime import datetime
import calendar
from dateutil.relativedelta import relativedelta
from sqlalchemy import func

# Sesuaikan import dengan struktur project Anda
from models import db, TransaksiTagihan, MasterPelanggan, DataMB

daily_bp = Blueprint('daily', __name__)

@daily_bp.route('/')
def index():
    # 1. PARAMETER PERIODE DINAMIS
    periode_input = request.args.get('periode') 
    if periode_input:
        curr_mon_date = datetime.strptime(periode_input, '%Y-%m')
    else:
        curr_mon_date = datetime.now()

    # Logika Waktu:
    # Jika user pilih April 2026 (Bulan N)
    # -> Target MC & Undue adalah Maret 2026 (Bulan N-1)
    # -> Pembanding (COLL LALU) adalah Februari 2026 yang dibayar Maret (Bulan N-2)
    target_date = curr_mon_date - relativedelta(months=1)
    prev_target_date = curr_mon_date - relativedelta(months=2)

    # Format YYYYMM untuk filter kolom `periode`
    p_target = target_date.strftime('%Y%m')             # cth: '202603'
    p_prev_target = prev_target_date.strftime('%Y%m')   # cth: '202602'

    # ==========================================
    # HELPER FUNCTIONS UNTUK DATABASE QUERY
    # ==========================================
    def get_mc_target(periode_rek):
        """Menghitung Target MC berdasarkan periode rekening"""
        res = db.session.query(
            MasterPelanggan.rayon, 
            func.sum(TransaksiTagihan.nominal).label('tot')
        ).join(TransaksiTagihan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == periode_rek).group_by(MasterPelanggan.rayon).all()
        
        tgt = {'34': 0, '35': 0, 'total': 0}
        for ray, nom in res:
            unit = '34' if '34' in str(ray) else '35'
            tgt[unit] += float(nom or 0)
            tgt['total'] += float(nom or 0)
        return tgt

    def get_undue(periode_rek, month_bayar, year_bayar):
        """Menghitung Undue (Tagihan dibayar di bulan yang sama dengan bulan cetak)"""
        res = db.session.query(
            MasterPelanggan.rayon, 
            func.sum(DataMB.nominal).label('tot')
        ).join(DataMB, DataMB.nomen == MasterPelanggan.nomen)\
         .filter(DataMB.periode == periode_rek)\
         .filter(func.extract('month', DataMB.tgl_bayar) == month_bayar)\
         .filter(func.extract('year', DataMB.tgl_bayar) == year_bayar)\
         .group_by(MasterPelanggan.rayon).all()
        
        ud = {'34': 0, '35': 0, 'total': 0}
        for ray, nom in res:
            unit = '34' if '34' in str(ray) else '35'
            ud[unit] += float(nom or 0)
            ud['total'] += float(nom or 0)
        return ud

    def get_daily_payments(periode_rek, month_bayar, year_bayar):
        """Menarik semua transaksi harian pada bulan berjalan"""
        return db.session.query(
            func.extract('day', DataMB.tgl_bayar).label('hari'),
            MasterPelanggan.rayon,
            func.count(DataMB.id).label('cust'),
            func.sum(DataMB.nominal).label('rp')
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
         .filter(DataMB.periode == periode_rek)\
         .filter(func.extract('month', DataMB.tgl_bayar) == month_bayar)\
         .filter(func.extract('year', DataMB.tgl_bayar) == year_bayar)\
         .group_by('hari', MasterPelanggan.rayon).all()

    # ==========================================
    # EKSEKUSI DATA BULAN INI (CURRENT)
    # ==========================================
    targets_now = get_mc_target(p_target)
    undue_now = get_undue(p_target, target_date.month, target_date.year)
    daily_now = get_daily_payments(p_target, curr_mon_date.month, curr_mon_date.year)

    # ==========================================
    # EKSEKUSI DATA BULAN LALU (PEMBANDING)
    # ==========================================
    targets_prev = get_mc_target(p_prev_target)
    undue_prev = get_undue(p_prev_target, prev_target_date.month, prev_target_date.year)
    daily_prev = get_daily_payments(p_prev_target, target_date.month, target_date.year)

    # ==========================================
    # PEMROSESAN ARRAY KE TABEL HTML
    # ==========================================
    table_data = []
    
    # Penampung Kumulatif Bulan Ini
    kum_now = {'34': 0, '35': 0, 'total': 0}
    
    # Penampung Kumulatif Bulan Lalu
    kum_prev = {'34': 0, '35': 0, 'total': 0}

    # Cari hari maksimal di bulan monitoring (28, 29, 30, atau 31)
    last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)[1]

    for d in range(1, last_day + 1):
        # --- Ambil baris data hari `d` untuk BULAN INI ---
        day_rows_now = [x for x in daily_now if int(x.hari) == d]
        r34_now = next((x for x in day_rows_now if '34' in str(x.rayon)), None)
        r35_now = next((x for x in day_rows_now if '35' in str(x.rayon)), None)

        rp34_now = float(r34_now.rp or 0) if r34_now else 0
        rp35_now = float(r35_now.rp or 0) if r35_now else 0
        
        # Tambah ke kumulatif Bulan Ini
        kum_now['34'] += rp34_now
        kum_now['35'] += rp35_now
        kum_now['total'] += (rp34_now + rp35_now)

        # Hitung Persentase (COLL) Bulan Ini
        coll34_now = ((kum_now['34'] + undue_now['34']) / targets_now['34']) * 100 if targets_now['34'] > 0 else 0
        coll35_now = ((kum_now['35'] + undue_now['35']) / targets_now['35']) * 100 if targets_now['35'] > 0 else 0
        collTot_now = ((kum_now['total'] + undue_now['total']) / targets_now['total']) * 100 if targets_now['total'] > 0 else 0

        # --- Ambil baris data hari `d` untuk BULAN LALU ---
        day_rows_prev = [x for x in daily_prev if int(x.hari) == d]
        r34_prev = next((x for x in day_rows_prev if '34' in str(x.rayon)), None)
        r35_prev = next((x for x in day_rows_prev if '35' in str(x.rayon)), None)

        rp34_prev = float(r34_prev.rp or 0) if r34_prev else 0
        rp35_prev = float(r35_prev.rp or 0) if r35_prev else 0
        
        # Tambah ke kumulatif Bulan Lalu
        kum_prev['34'] += rp34_prev
        kum_prev['35'] += rp35_prev
        kum_prev['total'] += (rp34_prev + rp35_prev)

        # Hitung Persentase (COLL) Bulan Lalu
        coll34_prev = ((kum_prev['34'] + undue_prev['34']) / targets_prev['34']) * 100 if targets_prev['34'] > 0 else 0
        coll35_prev = ((kum_prev['35'] + undue_prev['35']) / targets_prev['35']) * 100 if targets_prev['35'] > 0 else 0
        collTot_prev = ((kum_prev['total'] + undue_prev['total']) / targets_prev['total']) * 100 if targets_prev['total'] > 0 else 0

        # --- Gabungkan ke Final Row ---
        table_data.append({
            'tgl': f"{d:02d}",
            # Data Unit 34
            'u34_cust': r34_now.cust if r34_now else 0,
            'u34_rp': rp34_now,
            'u34_kum': kum_now['34'],
            'u34_coll': coll34_now,
            'u34_coll_mar': coll34_prev,
            
            # Data Unit 35
            'u35_cust': r35_now.cust if r35_now else 0,
            'u35_rp': rp35_now,
            'u35_kum': kum_now['35'],
            'u35_coll': coll35_now,
            'u35_coll_mar': coll35_prev,
            
            # Data Total AB Sunter
            'tot_cust': (r34_now.cust if r34_now else 0) + (r35_now.cust if r35_now else 0),
            'tot_rp': rp34_now + rp35_now,
            'tot_coll': collTot_now,
            'tot_coll_mar': collTot_prev,
            
            # Variance (Selisih Total COLL Bulan Ini vs LALU)
            'var_tot': collTot_now - collTot_prev
        })

    return render_template('daily.html', 
                           data=table_data, 
                           periode=curr_mon_date.strftime('%Y-%m'),
                           mon_name=curr_mon_date.strftime('%B %Y'),
                           prev_mon_name=target_date.strftime('%B %Y'))
