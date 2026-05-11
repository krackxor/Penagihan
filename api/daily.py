from flask import Blueprint, render_template, request
from datetime import datetime
import calendar

# Import sesuai struktur proyek Anda
from models import db, TransaksiTagihan, MasterPelanggan, DataMB

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER ---

def get_unit_from_cc(raw_p):
    """Identifikasi Unit 34 atau 35 berdasarkan header 'CC' di raw_data CID"""
    if not raw_p or not isinstance(raw_p, dict):
        return '35' # Default fallback
    cc = str(raw_p.get('CC', '')).strip()
    if '34' in cc: return '34'
    if '35' in cc: return '35'
    return '35'

def parse_db_date(date_str):
    """Membaca format tanggal string dari Database secara aman"""
    if not date_str: return None
    date_str = str(date_str).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y%m%d'):
        try:
            return datetime.strptime(date_str[:10], fmt)
        except ValueError:
            continue
    return None

@daily_bp.route('/')
def index():
    try:
        # 1. PARAMETER PERIODE
        periode_input = request.args.get('periode') 
        curr_mon_date = datetime.strptime(periode_input, '%Y-%m') if periode_input else datetime.now()

        # Logika N-1 (Contoh: Monitoring Mei -> Target April)
        target_month = curr_mon_date.month - 1 if curr_mon_date.month > 1 else 12
        target_year = curr_mon_date.year if curr_mon_date.month > 1 else curr_mon_date.year - 1
        
        # Format string untuk filter DB sesuai permintaan
        p_mc = f"{target_year}{target_month:02d}"             # YYYYMM (e.g. 202603)
        p_mb_rek = f"{target_month:02d}{target_year}"         # MMYYYY (e.g. 032026)
        p_bill_period = f"01/{target_month:02d}/{target_year}" # 01/MM/YYYY (e.g. 01/03/2026)

        # ==========================================
        # 2. QUERY MASTER CETAK (MC) - TARGET
        # Filter: CUST_TYPE = 'R'
        # ==========================================
        mc_data = db.session.query(
            TransaksiTagihan.nomen,
            TransaksiTagihan.nominal,
            MasterPelanggan.raw_data
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == p_mc)\
         .filter(db.func.jsonb_extract_path_text(MasterPelanggan.raw_data, 'CUST_TYPE') == 'R').all()

        targets = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        
        for nomen, nom, raw in mc_data:
            unit = get_unit_from_cc(raw)
            val = float(nom or 0)
            
            targets[unit]['rp'] += val
            targets[unit]['count'] += 1
            targets['total']['rp'] += val
            targets['total']['count'] += 1

        # ==========================================
        # 3. QUERY MASTER BAYAR (MB) - UNDUE
        # Filter: BULAN_REK = MMYYYY & Tgl Bayar di Bulan yang sama
        # ==========================================
        mb_undue_data = db.session.query(
            DataMB.nominal,
            MasterPelanggan.raw_data,
            DataMB.tgl_bayar
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
         .filter(db.func.jsonb_extract_path_text(DataMB.raw_data, 'BULAN_REK') == p_mb_rek).all()

        undue = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        
        for nom, raw, tgl in mb_undue_data:
            unit = get_unit_from_cc(raw)
            dt_bayar = parse_db_date(tgl)
            
            # Cek jika tgl bayar == bulan rekening (Contoh: Rekening Mar bayar di Mar)
            if dt_bayar and dt_bayar.month == target_month and dt_bayar.year == target_year:
                val = float(nom or 0)
                undue[unit]['rp'] += val
                undue[unit]['count'] += 1
                undue['total']['rp'] += val
                undue['total']['count'] += 1

        # ==========================================
        # 4. QUERY DAILY COLLECTION (CURRENT)
        # Filter: BILL_PERIOD, BILL_TYPE=WATER, TypeCust1=REGULAR
        # NOMINAL DIAMBIL DARI MC
        # ==========================================
        daily_query = db.session.query(
            DataMB.tgl_bayar,
            MasterPelanggan.raw_data,
            TransaksiTagihan.nominal # Nominal dari MC
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
         .join(TransaksiTagihan, DataMB.nomen == TransaksiTagihan.nomen)\
         .filter(TransaksiTagihan.periode == p_mc)\
         .filter(db.func.jsonb_extract_path_text(DataMB.raw_data, 'BILL_PERIOD') == p_bill_period)\
         .filter(db.func.jsonb_extract_path_text(DataMB.raw_data, 'BILL_TYPE') == 'WATER')\
         .filter(db.func.jsonb_extract_path_text(DataMB.raw_data, 'TypeCust1') == 'REGULAR').all()

        current_res = {'34': 0, '35': 0, 'total': 0}
        daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}

        for tgl, raw, nom_mc in daily_query:
            unit = get_unit_from_cc(raw)
            dt_bayar = parse_db_date(tgl)
            
            # Filter hanya yang bayar di bulan monitoring (N)
            if dt_bayar and dt_bayar.month == curr_mon_date.month and dt_bayar.year == curr_mon_date.year:
                val_mc = float(nom_mc or 0)
                current_res[unit] += val_mc
                current_res['total'] += val_mc
                
                d = dt_bayar.day
                daily_map[d][unit]['cust'] += 1
                daily_map[d][unit]['rp'] += val_mc

        # ==========================================
        # 5. RANGKAI DATA TABEL
        # ==========================================
        table_data = []
        kum = {'34': 0, '35': 0, 'total': 0}
        last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)[1]

        for d in range(1, last_day + 1):
            r34_rp = daily_map[d]['34']['rp']
            r35_rp = daily_map[d]['35']['rp']
            
            kum['34'] += r34_rp
            kum['35'] += r35_rp
            kum['total'] += (r34_rp + r35_rp)

            # Hitung COLL %: (Kumulatif + Undue) / Target MC
            def calc_coll(k_val, u_val, t_val):
                return (k_val + u_val) / t_val if t_val > 0 else 0

            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': daily_map[d]['34']['cust'],
                'u34_rp': r34_rp,
                'u34_kum': kum['34'],
                'u34_coll': calc_coll(kum['34'], undue['34']['rp'], targets['34']['rp']),
                'u34_coll_mar': 0, # Placeholder komparasi
                
                'u35_cust': daily_map[d]['35']['cust'],
                'u35_rp': r35_rp,
                'u35_kum': kum['35'],
                'u35_coll': calc_coll(kum['35'], undue['35']['rp'], targets['35']['rp']),
                'u35_coll_mar': 0,
                
                'tot_cust': daily_map[d]['34']['cust'] + daily_map[d]['35']['cust'],
                'tot_rp': r34_rp + r35_rp,
                'tot_coll': calc_coll(kum['total'], undue['total']['rp'], targets['total']['rp']),
                'tot_coll_mar': 0,
                'var_tot': 0
            })

        return render_template('daily.html', 
                               data=table_data, 
                               targets=targets, 
                               undue=undue, 
                               current=current_res,
                               periode=curr_mon_date.strftime('%Y-%m'),
                               mon_name=curr_mon_date.strftime('%B %Y'),
                               prev_mon_name=f"{calendar.month_name[target_month]} {target_year}")

    except Exception as e:
        import traceback
        print("CRASH_LOG:", traceback.format_exc())
        return f"<div style='background:#000;color:red;padding:20px;font-family:monospace;'><h1>[500_CORE_ERROR]</h1><pre>{traceback.format_exc()}</pre></div>", 500
