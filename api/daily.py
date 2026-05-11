from flask import Blueprint, render_template, request
from datetime import datetime
import calendar

# Import sesuai struktur proyek Anda
from models import db, TransaksiTagihan, MasterPelanggan, DataMB

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER AMAN ---

def get_val(data, keys):
    """Mencari nilai di JSON tanpa peduli huruf besar atau kecil (Anti-0)"""
    if not data or not isinstance(data, dict): return ""
    for k in keys:
        for option in [k, k.upper(), k.lower(), k.capitalize()]:
            if option in data: 
                val = data[option]
                return str(val).strip() if val is not None else ""
    return ""

def safe_month_math(date_obj, minus_months):
    m = date_obj.month - minus_months
    y = date_obj.year
    while m < 1:
        m += 12
        y -= 1
    return date_obj.replace(year=y, month=m, day=1)

def parse_db_date(date_str):
    if not date_str: return None
    s = str(date_str).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y%m%d'):
        try: return datetime.strptime(s[:10], fmt)
        except: continue
    return None

@daily_bp.route('/')
def index():
    try:
        # 1. PARAMETER PERIODE
        periode_input = request.args.get('periode') 
        curr_mon_date = datetime.strptime(periode_input, '%Y-%m') if periode_input else datetime.now()

        # Logika Periode (N-1)
        target_date = safe_month_math(curr_mon_date, 1)
        t_month, t_year = target_date.month, target_date.year
        
        # Format String Filter sesuai permintaan Anda
        p_mc = target_date.strftime('%Y%m')                  # YYYYMM (e.g. 202603)
        p_mb_rek = f"{t_month:02d}{t_year}"                  # MMYYYY (e.g. 032026)
        p_bill_period = f"01/{t_month:02d}/{t_year}"         # 01/MM/YYYY (e.g. 01/03/2026)

        # ==========================================
        # 2. PROSES MC (MASTER CETAK) - TARGET
        # Filter: CUST_TYPE = 'R'
        # Unit: 34/35 dari CC di CID
        # ==========================================
        mc_query = db.session.query(
            TransaksiTagihan.nomen,
            TransaksiTagihan.nominal,
            MasterPelanggan.raw_data
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == p_mc).all()

        targets = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        mc_nominal_map = {} # Kamus untuk Daily (Nominal harus dari MC)

        for nomen, nom, raw_cid in mc_query:
            # Filter CUST_TYPE = 'R'
            if get_val(raw_cid, ['CUST_TYPE', 'TypeCust']) == 'R':
                cc = get_val(raw_cid, ['CC'])
                unit = '34' if '34' in cc else '35'
                val = float(nom or 0)
                
                targets[unit]['rp'] += val
                targets[unit]['count'] += 1
                targets['total']['rp'] += val
                targets['total']['count'] += 1
                
                # Simpan nominal MC untuk referensi Daily nanti
                mc_nominal_map[str(nomen).strip()] = val

        # ==========================================
        # 3. PROSES MB (UNDUE) 
        # Filter: BULAN_REK = MMYYYY & Tgl Bayar di bulan yang sama
        # ==========================================
        mb_undue_query = db.session.query(
            DataMB.nomen,
            DataMB.nominal,
            DataMB.tgl_bayar,
            DataMB.raw_data,
            MasterPelanggan.raw_data.label('cid_raw')
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
         .all() # Loop manual lebih aman untuk JSONB kustom

        undue = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        
        # Penampung data harian (Current)
        current_total = {'34': 0, '35': 0, 'total': 0}
        daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}

        for nomen_mb, nom_mb, tgl, raw_mb, raw_cid in mb_undue_query:
            nomen_key = str(nomen_mb).strip()
            cc = get_val(raw_cid, ['CC'])
            unit = '34' if '34' in cc else '35'
            dt_bayar = parse_db_date(tgl)
            if not dt_bayar: continue

            # LOGIKA UNDUE (Bayar di bulan N-1)
            b_rek = get_val(raw_mb, ['BULAN_REK'])
            if b_rek == p_mb_rek and dt_bayar.month == t_month and dt_bayar.year == t_year:
                val = float(nom_mb or 0)
                undue[unit]['rp'] += val
                undue[unit]['count'] += 1
                undue['total']['rp'] += val
                undue['total']['count'] += 1

            # LOGIKA DAILY (Bayar di bulan N)
            # Filter: BILL_PERIOD, BILL_TYPE=WATER, TypeCust1=REGULAR
            b_period = get_val(raw_mb, ['BILL_PERIOD'])
            b_type = get_val(raw_mb, ['BILL_TYPE'])
            t_cust = get_val(raw_mb, ['TypeCust1'])

            if b_period == p_bill_period and b_type == 'WATER' and t_cust == 'REGULAR':
                if dt_bayar.month == curr_mon_date.month and dt_bayar.year == curr_mon_date.year:
                    # AMBIL NOMINAL DARI MASTER CETAK (MC)
                    val_mc = mc_nominal_map.get(nomen_key, 0)
                    
                    current_total[unit] += val_mc
                    current_total['total'] += val_mc
                    
                    d = dt_bayar.day
                    daily_map[d][unit]['cust'] += 1
                    daily_map[d][unit]['rp'] += val_mc

        # ==========================================
        # 4. RANGKAI DATA UNTUK TABEL
        # ==========================================
        table_data = []
        kum_now = {'34': 0, '35': 0, 'total': 0}
        last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)[1]

        for d in range(1, last_day + 1):
            r34_n, r35_n = daily_map[d]['34'], daily_map[d]['35']
            kum_now['34'] += r34_n['rp']
            kum_now['35'] += r35_n['rp']
            kum_now['total'] += (r34_n['rp'] + r35_n['rp'])

            def calc_ratio(k_val, u_val, t_val):
                return (k_val + u_val) / t_val if t_val > 0 else 0

            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': r34_n['cust'], 'u34_rp': r34_n['rp'], 'u34_kum': kum_now['34'], 
                'u34_coll': calc_ratio(kum_now['34'], undue['34']['rp'], targets['34']['rp']),
                'u34_coll_mar': 0, # Komparasi
                
                'u35_cust': r35_n['cust'], 'u35_rp': r35_n['rp'], 'u35_kum': kum_now['35'], 
                'u35_coll': calc_ratio(kum_now['35'], undue['35']['rp'], targets['35']['rp']),
                'u35_coll_mar': 0,
                
                'tot_cust': r34_n['cust'] + r35_n['cust'],
                'tot_rp': r34_n['rp'] + r35_n['rp'],
                'tot_coll': calc_ratio(kum_now['total'], undue['total']['rp'], targets['total']['rp']),
                'tot_coll_mar': 0, 'var_tot': 0
            })

        return render_template('daily.html', 
                               data=table_data, 
                               periode=curr_mon_date.strftime('%Y-%m'),
                               mon_name=curr_mon_date.strftime('%B %Y'),
                               prev_mon_name=f"{calendar.month_name[t_month]} {t_year}",
                               targets=targets, 
                               undue=undue, 
                               current=current_total)

    except Exception as e:
        import traceback
        print("ERROR IN DAILY:", traceback.format_exc())
        return f"<div style='background:#000;color:red;padding:20px;font-family:monospace;'><h1>[500_LOGIC_ERROR]</h1><pre>{traceback.format_exc()}</pre></div>", 500
