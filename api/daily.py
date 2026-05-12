from flask import Blueprint, render_template, request
from datetime import datetime, timedelta
import calendar
from models import db, TransaksiTagihan, MasterPelanggan, DataMB, DataDaily

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER ---
def get_val(data, keys):
    """Fungsi untuk mengambil nilai secara aman dari kolom raw_data (JSONB)"""
    if not data or not isinstance(data, dict): return ""
    for k in keys:
        if k in data: return str(data[k]).strip()
        if k.upper() in data: return str(data[k.upper()]).strip()
    return ""

def parse_db_date(date_str):
    """
    Pembersih & Parsing Tanggal Dinamis.
    Mampu membaca '25/04/2026', '25 04-2026', atau '25/04/2026 00:00:00'
    """
    if not date_str: return None
    s = str(date_str).strip().replace('-', '/').replace(' ', '/')
    s = s.split('/')[0:3] # Pastikan hanya mengambil DD, MM, YYYY
    s = "/".join(s)
    
    for fmt in ('%d/%m/%Y', '%Y/%m/%d', '%d/%m/%y', '%Y%m%d'):
        try: return datetime.strptime(s, fmt)
        except: continue
    return None

@daily_bp.route('/')
def index():
    try:
        # ==========================================
        # 1. TENTUKAN PERIODE LAPORAN (BULAN KOLEKSI)
        # ==========================================
        periode_input = request.args.get('periode') 
        
        # Jika tidak ada input, cari tanggal PAY_DT terakhir yang ada di database
        if not periode_input:
            latest_pay = db.session.query(db.func.max(DataDaily.pay_dt)).scalar()
            dt_latest = parse_db_date(latest_pay)
            # Default ke hari pertama di bulan tersebut (Misal 25/04/2026 menjadi 01/04/2026)
            curr_mon_date = dt_latest.replace(day=1) if dt_latest else datetime(2026, 4, 1)
        else:
            curr_mon_date = datetime.strptime(periode_input, '%Y-%m')

        # ==========================================
        # 2. LOGIKA N-1 (BULAN TAGIHAN / MC)
        # ==========================================
        # Mundur 1 bulan (Jika Koleksi = April, Target Tagihan = Maret)
        first_day_curr = curr_mon_date.replace(day=1)
        prev_month_date = first_day_curr - timedelta(days=1)
        
        p_report_db = curr_mon_date.strftime('%Y%m')          # Contoh: '202604'
        p_match_rek = prev_month_date.strftime('%m%Y')        # Contoh: '032026' (Format filter MB)
        
        # Filter Dinamis untuk Daily (Contoh: '01/03/2026' atau '1/3/2026')
        p_match_daily = f"01/{prev_month_date.month:02d}/{prev_month_date.year}"
        p_match_daily_alt = f"1/{prev_month_date.month}/{prev_month_date.year}"

        # ==========================================
        # 3. PROSES MC (TARGET TAGIHAN)
        # ==========================================
        mc_query = db.session.query(
            TransaksiTagihan.nomen,
            TransaksiTagihan.total_tagihan,
            MasterPelanggan.cc
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == p_report_db).all()

        targets = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'ab_sunter': {'rp': 0, 'count': 0}}
        
        # Dictionary ini sangat penting: Untuk menyimpan Nominal Asli agar bisa ditarik oleh Daily
        mc_lookup = {} 

        for nomen, nom, cc in mc_query:
            unit = str(cc or "").strip()
            if unit not in ['34', '35']: continue
            
            val = float(nom or 0)
            n_key = str(nomen).strip()
            mc_lookup[n_key] = val # Simpan ke memori lookup

            # Hitung target per unit
            targets[unit]['rp'] += val
            targets[unit]['count'] += 1
            
            # AB SUNTER = Penjumlahan CC 34 + CC 35
            targets['ab_sunter']['rp'] += val
            targets['ab_sunter']['count'] += 1

        # ==========================================
        # 4. PROSES MB (REALISASI UNDUE / LANCAR)
        # ==========================================
        undue = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'ab_sunter': {'rp': 0, 'count': 0}}
        
        mb_query = db.session.query(
            DataMB.nominal,
            DataMB.raw_data,
            MasterPelanggan.cc
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
         .filter(DataMB.periode == p_report_db).all()

        for nom_mb, raw_mb, cc in mb_query:
            unit = str(cc or "").strip()
            if unit not in ['34', '35']: continue
            
            # FILTER: Pastikan BULAN_REK di MB cocok dengan target N-1 (Misal: 032026)
            b_rek = get_val(raw_mb, ['BULAN_REK', 'BulanRek'])
            if b_rek == p_match_rek:
                val_mb = float(nom_mb or 0)
                undue[unit]['rp'] += val_mb
                undue[unit]['count'] += 1
                undue['ab_sunter']['rp'] += val_mb
                undue['ab_sunter']['count'] += 1

        # ==========================================
        # 5. PROSES DAILY (REALISASI HARIAN 1-31)
        # ==========================================
        daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}

        daily_query = db.session.query(
            DataDaily.nomen,
            DataDaily.pay_dt,
            DataDaily.bill_period,
            DataDaily.bill_type,
            DataDaily.typecust1,
            MasterPelanggan.cc
        ).join(MasterPelanggan, DataDaily.nomen == MasterPelanggan.nomen)\
         .filter(DataDaily.periode == p_report_db).all()

        for nomen, pay_dt_raw, b_period, b_type, t_cust, cc in daily_query:
            unit = str(cc or "").strip()
            if unit not in ['34', '35']: continue
            
            dt_bayar = parse_db_date(pay_dt_raw)
            if not dt_bayar: continue

            b_period_str = str(b_period or "")
            b_type_str = str(b_type or "").upper()
            t_cust_str = str(t_cust or "").upper()

            # FILTER KETAT: Bill Period (01/03/2026), Bill Type (WATER), Cust Type (REGULAR)
            if (p_match_daily in b_period_str or p_match_daily_alt in b_period_str) and \
               'WATER' in b_type_str and \
               ('REGULAR' in t_cust_str or 'REG' in t_cust_str or 'R' == t_cust_str):
                
                n_key = str(nomen).strip()
                
                # SANGAT PENTING: Ambil angka rupiah dari Nominal MC, BUKAN dari Data Daily
                val_mc = mc_lookup.get(n_key, 0)
                
                # Pastikan tanggal pembayaran terjadi pada bulan laporan (Misal April)
                if val_mc > 0 and dt_bayar.month == curr_mon_date.month:
                    d = dt_bayar.day
                    daily_map[d][unit]['cust'] += 1
                    daily_map[d][unit]['rp'] += val_mc

        # ==========================================
        # 6. PENYUSUNAN TABEL FINAL & KALKULASI
        # ==========================================
        table_data = []
        kum = {'34': 0, '35': 0, 'total': 0}
        _, last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)

        for d in range(1, last_day + 1):
            d34, d35 = daily_map[d]['34'], daily_map[d]['35']
            
            # Hitung Kumulatif (Hari ini + Hari sebelumnya)
            kum['34'] += d34['rp']
            kum['35'] += d35['rp']
            kum['total'] += (d34['rp'] + d35['rp'])

            # Fungsi hitung persentase pencapaian (Collection Ratio)
            def coll(k, u, t): return ((k + u) / t * 100) if t > 0 else 0

            table_data.append({
                'tgl': f"{d:02d}",
                'u34_cust': d34['cust'], 
                'u34_rp': d34['rp'], 
                'u34_kum': kum['34'], 
                'u34_coll': coll(kum['34'], undue['34']['rp'], targets['34']['rp']),
                
                'u35_cust': d35['cust'], 
                'u35_rp': d35['rp'], 
                'u35_kum': kum['35'], 
                'u35_coll': coll(kum['35'], undue['35']['rp'], targets['35']['rp']),
                
                'tot_cust': d34['cust'] + d35['cust'], 
                'tot_rp': d34['rp'] + d35['rp'],
                'tot_coll': coll(kum['total'], undue['ab_sunter']['rp'], targets['ab_sunter']['rp'])
            })

        return render_template('daily.html', 
                               data=table_data, 
                               periode=curr_mon_date.strftime('%Y-%m'),
                               mon_name=curr_mon_date.strftime('%B %Y'),
                               prev_mon_name=f"{calendar.month_name[prev_month_date.month]} {prev_month_date.year}",
                               targets=targets, 
                               undue=undue,
                               data_ready=True) 

    except Exception as e:
        import traceback
        return f"<pre>{traceback.format_exc()}</pre>", 500
