from flask import Blueprint, render_template, request
from datetime import datetime, timedelta
import calendar
from sqlalchemy import func
from models import db, TransaksiTagihan, MasterPelanggan, DataMB, DataDaily

daily_bp = Blueprint('daily', __name__)

# --- FUNGSI HELPER ---
def parse_db_date(date_str):
    """
    Pembersih & Parsing Tanggal Dinamis.
    Mampu membaca '25/04/2026', '25-04-2026', atau '25/04/2026 00:00:00'
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
            latest_pay = db.session.query(func.max(DataDaily.pay_dt)).scalar()
            dt_latest = parse_db_date(latest_pay)
            # Default ke hari pertama di bulan tersebut
            curr_mon_date = dt_latest.replace(day=1) if dt_latest else datetime.now().replace(day=1)
        else:
            curr_mon_date = datetime.strptime(periode_input, '%Y-%m')

        # Format pencarian database berdasarkan Smart Periode dari Importer (Contoh: '202604')
        p_report_db = curr_mon_date.strftime('%Y%m')          
        prev_month_date = (curr_mon_date.replace(day=1) - timedelta(days=1))

        # ==========================================
        # 2. PROSES MC (TARGET TAGIHAN)
        # ==========================================
        mc_query = db.session.query(
            TransaksiTagihan.nomen,
            TransaksiTagihan.total_tagihan,
            MasterPelanggan.cc
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == p_report_db).all()

        targets = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'ab_sunter': {'rp': 0, 'count': 0}}
        
        # Dictionary Lookup SANGAT PENTING: Untuk menyimpan Nominal Asli MC
        mc_lookup = {} 

        for nomen, nom, cc in mc_query:
            unit = str(cc or "").strip()
            if unit not in ['34', '35']: continue
            
            val = float(nom or 0)
            n_key = str(nomen).strip()
            mc_lookup[n_key] = val # Simpan Target Rupiah Asli ke memori

            # Hitung target per unit
            targets[unit]['rp'] += val
            targets[unit]['count'] += 1
            
            # AB SUNTER = Penjumlahan CC 34 + CC 35
            targets['ab_sunter']['rp'] += val
            targets['ab_sunter']['count'] += 1

        # ==========================================
        # 3. PROSES MB (REALISASI UNDUE / TEPAT WAKTU)
        # ==========================================
        undue = {'34': {'rp': 0, 'count': 0}, '35': {'rp': 0, 'count': 0}, 'ab_sunter': {'rp': 0, 'count': 0}}
        
        # Karena importer sudah merapikan DataMB.periode, kita cukup panggil kolom intinya
        mb_query = db.session.query(
            DataMB.nomen,
            MasterPelanggan.cc
        ).join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
         .filter(DataMB.periode == p_report_db).all()

        for nomen_mb, cc in mb_query:
            unit = str(cc or "").strip()
            if unit not in ['34', '35']: continue
            
            n_key = str(nomen_mb).strip()
            
            # LOGIKA PINTAR: Tarik Nominal dari MC, BUKAN dari nominal yang di MB
            val_mc_undue = mc_lookup.get(n_key, 0)
            
            if val_mc_undue > 0:
                undue[unit]['rp'] += val_mc_undue
                undue[unit]['count'] += 1
                undue['ab_sunter']['rp'] += val_mc_undue
                undue['ab_sunter']['count'] += 1

        # ==========================================
        # 4. PROSES DAILY (REALISASI HARIAN CURRENT)
        # ==========================================
        daily_map = {i: {'34': {'cust': 0, 'rp': 0}, '35': {'cust': 0, 'rp': 0}} for i in range(1, 32)}

        # Karena importer sudah mengubah format BILL_PERIOD menjadi DataDaily.periode yang rapi
        daily_query = db.session.query(
            DataDaily.nomen,
            DataDaily.pay_dt,
            MasterPelanggan.cc
        ).join(MasterPelanggan, DataDaily.nomen == MasterPelanggan.nomen)\
         .filter(DataDaily.periode == p_report_db).all()

        for nomen_d, pay_dt_raw, cc in daily_query:
            unit = str(cc or "").strip()
            if unit not in ['34', '35']: continue
            
            dt_bayar = parse_db_date(pay_dt_raw)
            if not dt_bayar: continue

            # Pastikan tanggal pembayaran betul-betul terjadi pada bulan laporan saat ini
            if dt_bayar.month == curr_mon_date.month and dt_bayar.year == curr_mon_date.year:
                
                n_key = str(nomen_d).strip()
                
                # LOGIKA PINTAR: Tarik Nominal dari MC, BUKAN dari PAY_AMT yang diunggah
                val_mc = mc_lookup.get(n_key, 0)
                
                if val_mc > 0:
                    d = dt_bayar.day
                    daily_map[d][unit]['cust'] += 1
                    daily_map[d][unit]['rp'] += val_mc

        # ==========================================
        # 5. PENYUSUNAN TABEL FINAL & KALKULASI
        # ==========================================
        table_data = []
        kum = {'34': 0, '35': 0, 'total': 0}
        _, last_day = calendar.monthrange(curr_mon_date.year, curr_mon_date.month)

        # Fungsi hitung persentase pencapaian (Collection Ratio)
        def coll(k, u, t): return ((k + u) / t * 100) if t > 0 else 0

        for d in range(1, last_day + 1):
            d34, d35 = daily_map[d]['34'], daily_map[d]['35']
            
            # Hitung Kumulatif (Hari ini + Hari sebelumnya)
            kum['34'] += d34['rp']
            kum['35'] += d35['rp']
            kum['total'] += (d34['rp'] + d35['rp'])

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
