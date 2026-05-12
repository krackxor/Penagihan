from flask import Blueprint, render_template, request
from datetime import datetime, timedelta
import calendar
from models import db, TransaksiTagihan, MasterPelanggan, DataMB
from sqlalchemy import text

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER ---
def get_val(data, keys):
    """Mencari nilai di JSON (JSONB Support) tanpa case sensitive"""
    if not data or not isinstance(data, dict): return ""
    for k in keys:
        for option in [k, k.upper(), k.lower(), k.capitalize()]:
            if option in data: 
                val = data[option]
                return str(val).strip() if val is not None else ""
    return ""

def safe_month_math(date_obj, minus_months):
    """Logika mundur bulan untuk menentukan target (N-1)"""
    first_of_current = date_obj.replace(day=1)
    target_date = first_of_current - timedelta(days=1)
    return target_date

def parse_db_date(date_str):
    """Parsing tanggal bayar secara cerdas dari berbagai format database"""
    if not date_str: return None
    s = str(date_str).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d', '%d-%m-%Y'):
        try: return datetime.strptime(s[:10], fmt)
        except: continue
    return None

@daily_bp.route('/')
def index():
    try:
        # 1. PARAMETER PERIODE (Bulan Pemantauan Daily, misal: April 2026)
        periode_input = request.args.get('periode') 
        curr_mon_date = datetime.strptime(periode_input, '%Y-%m') if periode_input else datetime.now()

        # Logika Target Periode (N-1, misal: Maret 2026)
        target_date = safe_month_math(curr_mon_date, 1)
        t_month, t_year = target_date.month, target_date.year
        
        # Format Filter Database
        p_mc = target_date.strftime('%Y%m')                  # e.g. 202603
        p_mb_rek = f"{t_month:02d}{t_year}"                  # e.g. 032026
        p_bill_period = f"01/{t_month:02d}/{t_year}"         # e.g. 01/03/2026

        # ==========================================
        # 2. PROSES TARGET (MC - MASTER CETAK)
        # Filter: CUST_TYPE = 'R', Kategori: 34 & 35
        # ==========================================
        # PERBAIKAN V18: Menggunakan 'total_tagihan' (Baris ini yang membuat sistem crash sebelumnya)
        mc_query = db.session.query(
            TransaksiTagihan.nomen,
            TransaksiTagihan.total_tagihan,
            MasterPelanggan.raw_data
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == p_mc).all()

        targets = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        mc_nominal_map = {} # Kunci performa: Map Nomen -> Nominal MC

        for nomen, nom, raw_cid in mc_query:
            # Filter hanya tipe Regular (R)
            if get_val(raw_cid, ['CUST_TYPE', 'TypeCust']) == 'R':
                cc = get_val(raw_cid, ['CC', 'Cc'])
                unit = '34' if '34' in cc else '35'
                val = float(nom or 0)
                
                targets[unit]['rp'] += val
                targets[unit]['count'] += 1
                targets['total']['rp'] += val
                targets['total']['count'] += 1
                
                # Simpan di map untuk memastikan Daily MB menarik nominal MC
                mc_nominal_map[str(nomen).strip()] = val

        # ==========================================
        # 3. PROSES REALISASI (MB - MASTER BAYAR)
        # ==========================================
        # Note: Tabel DataMB memang memiliki kolom bernama 'nominal' di app.py, jadi ini aman.
        mb_query = db.session.query(
            DataMB.nomen,
            DataMB.nominal,
            DataMB.tgl_bayar,
            DataMB.raw_data,
            MasterPelanggan.raw_data.label('cid_raw')
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen).all()

        undue = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}
        current_total = {'34': 0, '35': 0, 'total': 0}

        for nomen_mb, nom_mb, tgl, raw_mb, raw_cid in mb_query:
            nomen_key = str(nomen_mb).strip()
            cc = get_val(raw_cid, ['CC', 'Cc'])
            unit = '34' if '34' in cc else '35'
            dt_bayar = parse_db_date(tgl)
            if not dt_bayar: continue

            # A. LOGIKA UNDUE
            # Bayar di bulan yang sama dengan bulan rekening (Misal: Rek 032026, bayar di bulan 03)
            b_rek = get_val(raw_mb, ['BULAN_REK', 'BulanRek'])
            if b_rek == p_mb_rek and dt_bayar.month == t_month and dt_bayar.year == t_year:
                val = float(nom_mb or 0)
                undue[unit]['rp'] += val
                undue[unit]['count'] += 1
                undue['total']['rp'] += val
                undue['total']['count'] += 1

            # B. LOGIKA DAILY COLLECTION
            # Parameter: BILL_PERIOD (01/03/2026), WATER, REGULAR, bayar di bulan berjalan (April)
            b_period = get_val(raw_mb, ['BILL_PERIOD', 'BillPeriod'])
            b_type = get_val(raw_mb, ['BILL_TYPE', 'BillType'])
            t_cust = get_val(raw_mb, ['TypeCust1', 'TYPE_CUST_1'])

            if b_period == p_bill_period and 'WATER' in b_type.upper() and 'REGULAR' in t_cust.upper():
                if dt_bayar.month == curr_mon_date.month and dt_bayar.year == curr_mon_date.year:
                    # KUNCI AKURASI: Ambil nominal ASLI dari MC, BUKAN dari MB
                    val_mc = mc_nominal_map.get(nomen_key, 0)
                    
                    if val_mc > 0:
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

            def get_coll(k_val, u_val, t_val):
                return ((k_val + u_val) / t_val * 100) if t_val > 0 else 0

            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': d34['cust'], 'u34_rp': d34['rp'], 'u34_kum': kum['34'], 
                'u34_coll': get_coll(kum['34'], undue['34']['rp'], targets['34']['rp']),
                'u34_coll_mar': 0, # Area untuk Coll Bulan Lalu jika ada
                
                'u35_cust': d35['cust'], 'u35_rp': d35['rp'], 'u35_kum': kum['35'], 
                'u35_coll': get_coll(kum['35'], undue['35']['rp'], targets['35']['rp']),
                'u35_coll_mar': 0,
                
                'tot_cust': d34['cust'] + d35['cust'],
                'tot_rp': d34['rp'] + d35['rp'],
                'tot_coll': get_coll(kum['total'], undue['total']['rp'], targets['total']['rp']),
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
        return f"<div style='background:#0f172a;color:#ef4444;padding:20px;font-family:monospace;border-radius:10px'><h3>[V18_CALC_ERROR]</h3><pre>{traceback.format_exc()}</pre></div>", 500
