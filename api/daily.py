from flask import Blueprint, render_template, request
from datetime import datetime, timedelta
import calendar
from models import db, TransaksiTagihan, MasterPelanggan, DataMB
from sqlalchemy import text

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER JSONB ---
def get_val(data, keys):
    """Mencari nilai di JSONB tanpa case sensitive"""
    if not data or not isinstance(data, dict): return ""
    for k in keys:
        for option in [k, k.upper(), k.lower(), k.capitalize()]:
            if option in data: 
                val = data[option]
                return str(val).strip() if val is not None else ""
    return ""

def safe_month_math(date_obj):
    """Logika mundur 1 bulan (N-1) untuk menentukan bulan rekening asli"""
    first = date_obj.replace(day=1)
    prev = first - timedelta(days=1)
    return prev

def parse_db_date(date_str):
    """Parsing tanggal bayar dari database ke objek Python"""
    if not date_str: return None
    s = str(date_str).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d', '%d-%m-%Y'):
        try: return datetime.strptime(s[:10], fmt)
        except: continue
    return None

@daily_bp.route('/')
def index():
    try:
        # 1. IDENTIFIKASI PERIODE
        periode_input = request.args.get('periode') 
        curr_mon_date = datetime.strptime(periode_input, '%Y-%m') if periode_input else datetime.now()
        
        # Target N-1 (Bulan Tagihan Asli: Maret 2026 jika sekarang April)
        target_date = safe_month_math(curr_mon_date)
        t_month, t_year = target_date.month, target_date.year
        t_year_short = str(t_year)[2:] 
        
        # String Matcher
        p_target_db = curr_mon_date.strftime('%Y%m')         
        p_mb_rek = f"{t_month:02d}{t_year}"                  
        p_bill_period = f"1/{t_month}/{t_year_short}"        

        # ==========================================
        # 2. PROSES MC (TARGET)
        # ==========================================
        mc_query = db.session.query(
            TransaksiTagihan.nomen,
            TransaksiTagihan.total_tagihan,
            MasterPelanggan.raw_data
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == p_target_db).all()

        targets = {
            '34': {'rp': 0, 'count': 0}, 
            '35': {'rp': 0, 'count': 0}, 
            'total': {'rp': 0, 'count': 0} 
        }
        mc_nominal_map = {} 

        for nomen, nom, raw_cid in mc_query:
            cust_type = get_val(raw_cid, ['CUST_TYPE', 'TypeCust1', 'TIPEPLGGN']).upper()
            if cust_type == 'R' or 'REG' in cust_type:
                cc = get_val(raw_cid, ['CC', 'Cc'])
                val = float(nom or 0)
                nomen_key = str(nomen).strip()
                
                mc_nominal_map[nomen_key] = val

                if '34' in cc:
                    targets['34']['rp'] += val
                    targets['34']['count'] += 1
                elif '35' in cc:
                    targets['35']['rp'] += val
                    targets['35']['count'] += 1
                
                if '34' in cc or '35' in cc:
                    targets['total']['rp'] += val
                    targets['total']['count'] += 1

        # ==========================================
        # 3. PROSES MB (UNDUE) & DAILY COLLECTION
        # ==========================================
        mb_query = db.session.query(
            DataMB.nomen,
            DataMB.nominal,
            DataMB.tgl_bayar,
            DataMB.raw_data,
            MasterPelanggan.raw_data.label('cid_raw')
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
         .filter(DataMB.periode == p_target_db).all()

        undue = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}
        current_total = {'34': 0, '35': 0, 'total': 0}

        for nomen_mb, nom_mb, tgl, raw_mb, raw_cid in mb_query:
            nomen_key = str(nomen_mb).strip()
            cc = get_val(raw_cid, ['CC', 'Cc'])
            dt_bayar = parse_db_date(tgl)
            if not dt_bayar: continue

            b_rek = get_val(raw_mb, ['BULAN_REK', 'BulanRek'])
            if b_rek == p_mb_rek and dt_bayar.month == t_month:
                val = float(nom_mb or 0)
                unit = '34' if '34' in cc else ('35' if '35' in cc else None)
                if unit:
                    undue[unit]['rp'] += val
                    undue[unit]['count'] += 1
                    undue['total']['rp'] += val
                    undue['total']['count'] += 1

            b_period = get_val(raw_mb, ['BILL_PERIOD', 'BillPeriod'])
            b_type = get_val(raw_mb, ['BILL_TYPE', 'BillType']).upper()
            t_cust = get_val(raw_mb, ['TypeCust1', 'TYPE_CUST_1']).upper()

            if p_bill_period in b_period and 'WATER' in b_type and 'REG' in t_cust:
                if dt_bayar.month == curr_mon_date.month:
                    val_mc = mc_nominal_map.get(nomen_key, 0)
                    if val_mc > 0:
                        unit = '34' if '34' in cc else ('35' if '35' in cc else None)
                        if unit:
                            current_total[unit] += val_mc
                            current_total['total'] += val_mc
                            d = dt_bayar.day
                            if d in daily_map:
                                daily_map[d][unit]['cust'] += 1
                                daily_map[d][unit]['rp'] += val_mc

        # ==========================================
        # 4. FINALISASI DATA TABEL (KUMULATIF)
        # ==========================================
        table_data = []
        kum = {'34': 0, '35': 0, 'total': 0}
        _, last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)

        for d in range(1, last_day + 1):
            d34, d35 = daily_map[d]['34'], daily_map[d]['35']
            kum['34'] += d34['rp']
            kum['35'] += d35['rp']
            kum['total'] += (d34['rp'] + d35['rp'])

            def calc_coll(k_val, u_val, t_val):
                return ((k_val + u_val) / t_val * 100) if t_val > 0 else 0

            # PERBAIKAN: Menambahkan kunci 'var_tot' dan atribut coll_mar yang dibutuhkan template
            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': d34['cust'], 'u34_rp': d34['rp'], 'u34_kum': kum['34'], 
                'u34_coll': calc_coll(kum['34'], undue['34']['rp'], targets['34']['rp']),
                'u34_coll_mar': 0.0,
                
                'u35_cust': d35['cust'], 'u35_rp': d35['rp'], 'u35_kum': kum['35'], 
                'u35_coll': calc_coll(kum['35'], undue['35']['rp'], targets['35']['rp']),
                'u35_coll_mar': 0.0,
                
                'tot_cust': d34['cust'] + d35['cust'],
                'tot_rp': d34['rp'] + d35['rp'],
                'tot_coll': calc_coll(kum['total'], undue['total']['rp'], targets['total']['rp']),
                'tot_coll_mar': 0.0,
                'var_tot': 0.0 # <--- INI PERBAIKAN UNTUK ERROR TERAKHIR
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
        return f"<div style='background:#000;color:red;padding:20px'>{traceback.format_exc()}</div>", 500
