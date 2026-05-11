from flask import Blueprint, render_template, request
from datetime import datetime
import calendar

# Import sesuai struktur proyek Anda
from models import db, TransaksiTagihan, MasterPelanggan, DataMB

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER AMAN (ANTI-CRASH) ---

def safe_month_math(date_obj, minus_months):
    """Mundur beberapa bulan tanpa library tambahan (Dateutil)"""
    m = date_obj.month - minus_months
    y = date_obj.year
    while m < 1:
        m += 12
        y -= 1
    return date_obj.replace(year=y, month=m, day=1)

def parse_db_date(date_str):
    """Membaca format tanggal string dari Database secara cerdas"""
    if not date_str: return None
    date_str = str(date_str).strip()
    
    # Deteksi Format YYYY-MM-DD
    if len(date_str) >= 10 and date_str[4] == '-':
        try:
            return datetime.strptime(date_str[:10], '%Y-%m-%d')
        except ValueError: pass
    
    # Deteksi Format DD/MM/YYYY atau lainnya menggunakan Pandas (Fallback)
    try:
        import pandas as pd
        dt = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
        if pd.notnull(dt): return dt
    except Exception: pass
    
    return None

@daily_bp.route('/')
def index():
    try:
        # 1. PARAMETER PERIODE DINAMIS
        periode_input = request.args.get('periode') 
        if periode_input:
            curr_mon_date = datetime.strptime(periode_input, '%Y-%m')
        else:
            curr_mon_date = datetime.now()

        # Logika Waktu N-1 dan N-2
        target_date = safe_month_math(curr_mon_date, 1)
        prev_target_date = safe_month_math(curr_mon_date, 2)

        p_target = target_date.strftime('%Y%m')              
        p_prev_target = prev_target_date.strftime('%Y%m')   

        # --- FUNGSI QUERY LOKAL ---

        def get_mc_target(periode_rek):
            """Menghitung Target MC dari Master Cetak"""
            res = db.session.query(
                MasterPelanggan.rayon, 
                db.func.sum(TransaksiTagihan.nominal).label('tot')
            ).join(TransaksiTagihan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
             .filter(TransaksiTagihan.periode == periode_rek).group_by(MasterPelanggan.rayon).all()
            
            tgt = {'34': 0, '35': 0, 'total': 0}
            for ray, nom in res:
                unit = '34' if '34' in str(ray) else '35'
                val = float(nom or 0)
                tgt[unit] += val
                tgt['total'] += val
            return tgt

        def get_mb_processed(periode_rek, mon_daily, yr_daily, mon_undue, yr_undue):
            """Memproses DataMB menjadi Undue, Current, dan Rincian Harian"""
            raw_mb = db.session.query(
                DataMB.tgl_bayar, DataMB.nominal, MasterPelanggan.rayon
            ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
             .filter(DataMB.periode == periode_rek).all()
            
            undue = {'34': 0, '35': 0, 'total': 0}
            current_total = {'34': 0, '35': 0, 'total': 0}
            daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}
            
            for tgl, nom_str, rayon in raw_mb:
                nom = float(nom_str or 0)
                unit = '34' if '34' in str(rayon) else '35'
                dt = parse_db_date(tgl)
                if not dt: continue
                
                # UNDUE: Bayar di bulan yang sama dengan bulan rekening (Maret)
                if dt.month == mon_undue and dt.year == yr_undue:
                    undue[unit] += nom
                    undue['total'] += nom
                
                # CURRENT: Bayar di bulan monitoring (April)
                elif dt.month == mon_daily and dt.year == yr_daily:
                    current_total[unit] += nom
                    current_total['total'] += nom
                    daily_map[dt.day][unit]['cust'] += 1
                    daily_map[dt.day][unit]['rp'] += nom
            
            return undue, current_total, daily_map

        # ==========================================
        # EKSEKUSI DATA
        # ==========================================
        
        # Data Bulan Berjalan (Contoh: Rekening Maret yang dibayar April)
        targets_now = get_mc_target(p_target)
        undue_now, current_now, daily_now = get_mb_processed(
            p_target, 
            curr_mon_date.month, curr_mon_date.year, 
            target_date.month, target_date.year
        )

        # Data Bulan Lalu untuk Komparasi (Contoh: Rekening Feb yang dibayar Maret)
        targets_prev = get_mc_target(p_prev_target)
        undue_prev, _, daily_prev = get_mb_processed(
            p_prev_target, 
            target_date.month, target_date.year,           
            prev_target_date.month, prev_target_date.year  
        )

        # ==========================================
        # RANGKAI DATA UNTUK TABEL
        # ==========================================
        
        table_data = []
        kum_now = {'34': 0, '35': 0, 'total': 0}
        kum_prev = {'34': 0, '35': 0, 'total': 0}
        last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)[1]

        for d in range(1, last_day + 1):
            # Data Bulan Berjalan
            r34_n, r35_n = daily_now[d]['34'], daily_now[d]['35']
            kum_now['34'] += r34_n['rp']
            kum_now['35'] += r35_n['rp']
            kum_now['total'] += (r34_n['rp'] + r35_n['rp'])

            # Data Bulan Lalu (Pembanding)
            r34_p, r35_p = daily_prev[d]['34'], daily_prev[d]['35']
            kum_prev['34'] += r34_p['rp']
            kum_prev['35'] += r35_p['rp']
            kum_prev['total'] += (r34_p['rp'] + r35_p['rp'])

            # Hitung COLL % ( (Kumulatif + Undue) / Target MC )
            def calc_coll(kum_val, ud_val, tgt_val):
                return (kum_val + ud_val) / tgt_val * 100 if tgt_val > 0 else 0

            coll34_n = calc_coll(kum_now['34'], undue_now['34'], targets_now['34'])
            coll35_n = calc_coll(kum_now['35'], undue_now['35'], targets_now['35'])
            collTot_n = calc_coll(kum_now['total'], undue_now['total'], targets_now['total'])

            coll34_p = calc_coll(kum_prev['34'], undue_prev['34'], targets_prev['34'])
            coll35_p = calc_coll(kum_prev['35'], undue_prev['35'], targets_prev['35'])
            collTot_p = calc_coll(kum_prev['total'], undue_prev['total'], targets_prev['total'])

            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': r34_n['cust'], 'u34_rp': r34_n['rp'], 'u34_kum': kum_now['34'], 
                'u34_coll': coll34_n, 'u34_coll_mar': coll34_p,
                'u35_cust': r35_n['cust'], 'u35_rp': r35_n['rp'], 'u35_kum': kum_now['35'], 
                'u35_coll': coll35_n, 'u35_coll_mar': coll35_p,
                'tot_cust': r34_n['cust'] + r35_n['cust'],
                'tot_rp': r34_n['rp'] + r35_n['rp'],
                'tot_coll': collTot_n, 'tot_coll_mar': collTot_p,
                'var_tot': collTot_n - collTot_p
            })

        return render_template('daily.html', 
                               data=table_data, 
                               periode=curr_mon_date.strftime('%Y-%m'),
                               mon_name=curr_mon_date.strftime('%B %Y'),
                               prev_mon_name=target_date.strftime('%B %Y'),
                               targets=targets_now, # Untuk Executive Summary
                               undue=undue_now,     # Untuk Executive Summary
                               current=current_now) # Untuk Executive Summary

    except Exception as e:
        import traceback
        print("ERROR IN DAILY ROUTE:", traceback.format_exc())
        return f"""
        <div style="background:#0a0e17; color:#00ff41; padding:2rem; font-family:monospace; border: 1px solid #ff073a;">
            <h1 style="color:#ff073a;">[ 500_SYSTEM_ERROR ]</h1>
            <p>Terjadi kegagalan fatal saat mesin mencoba mengolah data harian.</p>
            <hr style="border-color:#333;">
            <p style="color:#ffbd2e;"><b>Lokasi Masalah:</b> api/daily.py</p>
            <p style="color:#e2e8f0;"><b>Detail Crash:</b> {str(e)}</p>
        </div>
        """, 500
