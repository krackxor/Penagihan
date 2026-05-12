from flask import Blueprint, render_template, request
from datetime import datetime, timedelta
import calendar
from models import db, TransaksiTagihan, MasterPelanggan, DataMB
from sqlalchemy import text

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER ---
def get_val(data, keys):
    if not data or not isinstance(data, dict): return ""
    for k in keys:
        for option in [k, k.upper(), k.lower(), k.capitalize()]:
            if option in data: 
                val = data[option]
                return str(val).strip() if val is not None else ""
    return ""

def parse_db_date(date_str):
    if not date_str: return None
    s = str(date_str).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d', '%d-%m-%Y'):
        try: return datetime.strptime(s[:10], fmt)
        except: continue
    return None

@daily_bp.route('/')
def index():
    try:
        # 1. AMBIL PERIODE DARI INPUT (Default ke April 2026 jika tidak ada)
        periode_input = request.args.get('periode') 
        if not periode_input:
            curr_mon_date = datetime(2026, 4, 1)
        else:
            curr_mon_date = datetime.strptime(periode_input, '%Y-%m')

        # 2. HITUNG BULAN N-1 SECARA DINAMIS (Tidak dipaksa bulan 3 lagi!)
        first_day_curr = curr_mon_date.replace(day=1)
        target_date = first_day_curr - timedelta(days=1)
        
        t_month = target_date.month
        t_year = target_date.year
        t_year_short = str(t_year)[2:]
        
        # String Matcher untuk Filter (Dinamis sesuai pilihan user)
        p_target_db = curr_mon_date.strftime('%Y%m')         # e.g. 202604
        p_mb_rek = f"{t_month:02d}{t_year}"                  # e.g. 032026
        p_bill_period = f"1/{t_month}/{t_year_short}"        # e.g. 1/3/26

        # ==========================================
        # 3. PROSES TARGET (MC - MASTER CETAK)
        # ==========================================
        mc_query = db.session.query(
            TransaksiTagihan.nomen,
            TransaksiTagihan.total_tagihan,
            MasterPelanggan.raw_data,
            MasterPelanggan.cc.label('cid_cc')
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == p_target_db).all()

        targets = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        mc_nominal_map = {} 

        for nomen, nom, raw_cid, cid_cc in mc_query:
            # Filter Longgar: R, REG, atau REGULAR
            tipe = str(get_val(raw_cid, ['CUST_TYPE', 'TypeCust1', 'TIPEPLGGN', 'tipeplggn'])).upper()
            if 'R' == tipe or 'REG' in tipe:
                cc = str(cid_cc or "").strip()
                val = float(nom or 0)
                nomen_key = str(nomen).strip()
                mc_nominal_map[nomen_key] = val

                unit = None
                if '34' in cc: unit = '34'
                elif '35' in cc: unit = '35'
                
                if unit:
                    targets[unit]['rp'] += val
                    targets[unit]['count'] += 1
                    targets['total']['rp'] += val
                    targets['total']['count'] += 1

        # ==========================================
        # 4. CEK APAKAH DATA ADA?
        # ==========================================
        # Jika total target masih 0, artinya user belum upload MC untuk periode ini.
        data_tersedia = True if targets['total']['count'] > 0 else False

        # ==========================================
        # 5. PROSES REALISASI (HANYA JALANKAN JIKA DATA ADA)
        # ==========================================
        undue = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'total': {'rp': 0, 'count': 0}}
        daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}
        current_total = {'34': 0, '35': 0, 'total': 0}

        if data_tersedia:
            mb_query = db.session.query(
                DataMB.nomen,
                DataMB.nominal,
                DataMB.tgl_bayar,
                DataMB.raw_data,
                MasterPelanggan.cc.label('cid_cc')
            ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
             .filter(DataMB.periode == p_target_db).all()

            for nomen_mb, nom_mb, tgl, raw_mb, cid_cc in mb_query:
                nomen_key = str(nomen_mb).strip()
                cc = str(cid_cc or "").strip()
                dt_bayar = parse_db_date(tgl)
                if not dt_bayar: continue

                # A. LOGIKA UNDUE
                b_rek = get_val(raw_mb, ['BULAN_REK', 'BulanRek'])
                if b_rek == p_mb_rek and dt_bayar.month == t_month:
                    val = float(nom_mb or 0)
                    unit = '34' if '34' in cc else ('35' if '35' in cc else None)
                    if unit:
                        undue[unit]['rp'] += val
                        undue[unit]['count'] += 1
                        undue['total']['rp'] += val
                        undue['total']['count'] += 1

                # B. LOGIKA DAILY (Nominal Wajib MC)
                b_period = get_val(raw_mb, ['BILL_PERIOD', 'BillPeriod'])
                b_type = get_val(raw_mb, ['BILL_TYPE', 'BillType']).upper()
                t_cust = get_val(raw_mb, ['TypeCust1', 'TYPE_CUST_1', 'CUST_TYPE']).upper()

                if p_bill_period in b_period and 'WATER' in b_type and ('REG' in t_cust or 'R' == t_cust):
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
        # 6. FINALISASI TABEL
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

            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': d34['cust'], 'u34_rp': d34['rp'], 'u34_kum': kum['34'], 
                'u34_coll': calc_coll(kum['34'], undue['34']['rp'], targets['34']['rp']),
                'u34_coll_mar': 0.0,
                'u35_cust': d35['cust'], 'u35_rp': d35['rp'], 'u35_kum': kum['35'], 
                'u35_coll': calc_coll(kum['35'], undue['35']['rp'], targets['35']['rp']),
                'u35_coll_mar': 0.0,
                'tot_cust': d34['cust'] + d35['cust'], 'tot_rp': d34['rp'] + d35['rp'],
                'tot_coll': calc_coll(kum['total'], undue['total']['rp'], targets['total']['rp']),
                'tot_coll_mar': 0.0, 'var_tot': 0.0
            })

        return render_template('daily.html', 
                               data=table_data, 
                               periode=curr_mon_date.strftime('%Y-%m'),
                               mon_name=curr_mon_date.strftime('%B %Y'),
                               prev_mon_name=f"{calendar.month_name[t_month]} {t_year}",
                               targets=targets, 
                               undue=undue, 
                               current=current_total,
                               data_ready=data_tersedia) # Kirim status ke template

    except Exception as e:
        import traceback
        return f"<pre>{traceback.format_exc()}</pre>", 500
