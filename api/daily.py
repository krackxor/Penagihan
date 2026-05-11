from flask import Blueprint, render_template, request
from datetime import datetime
import calendar

# Sesuaikan dengan struktur proyek Anda
from models import db, TransaksiTagihan, MasterPelanggan, DataMB

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER AMAN (TANPA LIBRARY TAMBAHAN) ---
def safe_month_math(date_obj, minus_months):
    """Mundur beberapa bulan ke belakang tanpa menggunakan dateutil (Anti-Crash)"""
    m = date_obj.month - minus_months
    y = date_obj.year
    while m < 1:
        m += 12
        y -= 1
    return date_obj.replace(year=y, month=m, day=1)

def parse_db_date(date_str):
    """Fungsi fleksibel untuk membaca format tanggal string dari Database"""
    if not date_str: return None
    date_str = str(date_str).strip()
    
    # Deteksi Format YYYY-MM-DD
    if len(date_str) >= 10 and date_str[4] == '-':
        try:
            return datetime.strptime(date_str[:10], '%Y-%m-%d')
        except: pass
    
    # Deteksi Format DD/MM/YYYY atau lainnya menggunakan Pandas (Fallback)
    try:
        import pandas as pd
        dt = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
        if pd.notnull(dt): return dt
    except: pass
    
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

        def get_mc_target(periode_rek):
            """Tarik data Master Cetak sebagai Target"""
            res = db.session.query(
                MasterPelanggan.rayon, 
                db.func.sum(TransaksiTagihan.nominal).label('tot')
            ).join(TransaksiTagihan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
             .filter(TransaksiTagihan.periode == periode_rek).group_by(MasterPelanggan.rayon).all()
            
            tgt = {'34': 0, '35': 0, 'total': 0}
            for ray, nom in res:
                unit = '34' if '34' in str(ray) else '35'
                tgt[unit] += float(nom or 0)
                tgt['total'] += float(nom or 0)
            return tgt

        def get_mb_processed(periode_rek, mon_daily, yr_daily, mon_undue, yr_undue):
            """
            Tarik data bayar sekaligus dan olah menggunakan CPU Python
            Ini mengamankan server dari Error Tipe Data SQL (String vs Date)
            """
            raw_mb = db.session.query(
                DataMB.tgl_bayar,
                DataMB.nominal,
                MasterPelanggan.rayon
            ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
             .filter(DataMB.periode == periode_rek).all()
            
            undue = {'34': 0, '35': 0, 'total': 0}
            daily = {}
            for i in range(1, 32):
                daily[i] = {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}}
            
            for tgl, nom_str, rayon in raw_mb:
                nom = float(nom_str or 0)
                unit = '34' if '34' in str(rayon) else '35'
                
                dt = parse_db_date(tgl)
                if not dt: continue # Skip jika tanggal kosong atau korup
                
                # Masuk keranjang UNDUE (Bulan bayar = Bulan cetak)
                if dt.month == mon_undue and dt.year == yr_undue:
                    undue[unit] += nom
                    undue['total'] += nom
                
                # Masuk keranjang DAILY (Bulan bayar = Bulan target monitoring)
                elif dt.month == mon_daily and dt.year == yr_daily:
                    d = dt.day
                    daily[d][unit]['cust'] += 1
                    daily[d][unit]['rp'] += nom
            
            return undue, daily

        # ==========================================
        # EKSEKUSI PENGAMBILAN DATA
        # ==========================================
        targets_now = get_mc_target(p_target)
        undue_now, daily_now = get_mb_processed(
            p_target, 
            curr_mon_date.month, curr_mon_date.year, # Filter Daily
            target_date.month, target_date.year      # Filter Undue
        )

        targets_prev = get_mc_target(p_prev_target)
        undue_prev, daily_prev = get_mb_processed(
            p_prev_target, 
            target_date.month, target_date.year,           
            prev_target_date.month, prev_target_date.year  
        )

        # ==========================================
        # RANGKAI ARRAY TABEL HTML
        # ==========================================
        table_data = []
        kum_now = {'34': 0, '35': 0, 'total': 0}
        kum_prev = {'34': 0, '35': 0, 'total': 0}

        last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)[1]

        for d in range(1, last_day + 1):
            # Hitungan Bulan Berjalan
            c34_n = daily_now[d]['34']['cust']
            rp34_n = daily_now[d]['34']['rp']
            c35_n = daily_now[d]['35']['cust']
            rp35_n = daily_now[d]['35']['rp']

            kum_now['34'] += rp34_n
            kum_now['35'] += rp35_n
            kum_now['total'] += (rp34_n + rp35_n)

            coll34_n = ((kum_now['34'] + undue_now['34']) / targets_now['34']) * 100 if targets_now['34'] > 0 else 0
            coll35_n = ((kum_now['35'] + undue_now['35']) / targets_now['35']) * 100 if targets_now['35'] > 0 else 0
            collTot_n = ((kum_now['total'] + undue_now['total']) / targets_now['total']) * 100 if targets_now['total'] > 0 else 0

            # Hitungan Bulan Lalu (Pembanding)
            rp34_p = daily_prev[d]['34']['rp']
            rp35_p = daily_prev[d]['35']['rp']

            kum_prev['34'] += rp34_p
            kum_prev['35'] += rp35_p
            kum_prev['total'] += (rp34_p + rp35_p)

            coll34_p = ((kum_prev['34'] + undue_prev['34']) / targets_prev['34']) * 100 if targets_prev['34'] > 0 else 0
            coll35_p = ((kum_prev['35'] + undue_prev['35']) / targets_prev['35']) * 100 if targets_prev['35'] > 0 else 0
            collTot_p = ((kum_prev['total'] + undue_prev['total']) / targets_prev['total']) * 100 if targets_prev['total'] > 0 else 0

            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': c34_n, 'u34_rp': rp34_n, 'u34_kum': kum_now['34'], 
                'u34_coll': coll34_n, 'u34_coll_mar': coll34_p,
                
                'u35_cust': c35_n, 'u35_rp': rp35_n, 'u35_kum': kum_now['35'], 
                'u35_coll': coll35_n, 'u35_coll_mar': coll35_p,
                
                'tot_cust': c34_n + c35_n,
                'tot_rp': rp34_n + rp35_n,
                'tot_coll': collTot_n, 'tot_coll_mar': collTot_p,
                'var_tot': collTot_n - collTot_p
            })

        return render_template('daily.html', 
                               data=table_data, 
                               periode=curr_mon_date.strftime('%Y-%m'),
                               mon_name=curr_mon_date.strftime('%B %Y'),
                               prev_mon_name=target_date.strftime('%B %Y'))

    except Exception as e:
        import traceback
        print("ERROR IN DAILY ROUTE:", traceback.format_exc())
        return f"""
        <div style="background:#0a0e17; color:#00ff41; padding:2rem; font-family:monospace;">
            <h1>[ 500_SYSTEM_OVERLOAD ]</h1>
            <p>Terjadi kegagalan saat mesin mencoba membaca data dari Database.</p>
            <p style="color:#ff073a;"><b>Detail Crash:</b> {str(e)}</p>
            <p>Silakan laporkan detail merah di atas kepada tim pengembang.</p>
        </div>
        """, 500
