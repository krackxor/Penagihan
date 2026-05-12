from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan, TransaksiTagihan, DataMB, DataMainbill, DataSBRS
from sqlalchemy import or_, desc

# Inisialisasi Blueprint untuk modul Pencarian Global
search_bp = Blueprint('search', __name__)

@search_bp.route('/')
def search_page():
    """Menampilkan UI Halaman Pencarian Universal Sinergi V18"""
    return render_template('search.html')

# =====================================================================
# 1. API PENCARIAN CEPAT (AUTOCOMPLETE)
# =====================================================================
@search_bp.route('/api/query', methods=['GET'])
def execute_search():
    """
    API Mesin Pencari Real-Time V18.
    Hanya mengembalikan data identitas dasar agar pencarian secepat kilat.
    """
    keyword = request.args.get('q', '').strip()
    
    # PROTEKSI: Batasi pencarian minimal 3 karakter agar RAM Server aman
    if len(keyword) < 3:
        return jsonify([])

    search_term = f"%{keyword}%"

    try:
        # Eksekusi pencarian ke 6 kolom sekaligus (Nomen, Nama, Alamat, Meter, WA, HP)
        query = MasterPelanggan.query.filter(
            or_(
                MasterPelanggan.nomen.ilike(search_term),
                MasterPelanggan.nama.ilike(search_term),
                MasterPelanggan.alamat.ilike(search_term),
                MasterPelanggan.serial.ilike(search_term),
                MasterPelanggan.wa.ilike(search_term),
                MasterPelanggan.hp.ilike(search_term)
            )
        ).limit(20).all() # Batasi maksimal 20 hasil agar browser ringan

        results = []
        for p in query:
            # Pembersihan visual teks kosong
            no_hp_aktif = p.wa if p.wa and str(p.wa).strip() not in ['', 'None', '-'] else p.hp
            if not no_hp_aktif or str(no_hp_aktif).strip() in ['', 'None']:
                no_hp_aktif = '-'
                
            no_meter_aktif = p.serial if p.serial and str(p.serial).strip() not in ['', 'None'] else '-'

            results.append({
                "nomen": p.nomen,
                "nama": p.nama,
                "alamat": p.alamat,
                "kelurahan": p.kelurahan,
                "pcez": p.pcez,
                "no_meter": no_meter_aktif,
                "no_hp": no_hp_aktif,
                "tarif": p.tarif,
                "status": p.status
            })
            
        return jsonify(results)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# =====================================================================
# 2. API DETAIL SUPER LENGKAP (UNTUK TAB DINAMIS 360 DERAJAT)
# =====================================================================
@search_bp.route('/api/detail/<nomen>', methods=['GET'])
def get_customer_360(nomen):
    """
    API 360 Derajat: Menarik SEMUA sejarah pelanggan untuk dirender di Tab Dinamis.
    (CID, MC, MB, Mainbill, SBRS)
    """
    try:
        # 1. Tarik Data Master (CID)
        cid = MasterPelanggan.query.get(nomen)
        if not cid:
            return jsonify({"error": "Data Pelanggan Tidak Ditemukan di Master CID"}), 404

        # Parsing Raw Data CID (Banyak info tersembunyi di sini)
        raw_cid = cid.raw_data if isinstance(cid.raw_data, dict) else {}

        # 2. Tarik Riwayat Tagihan (MC) - Maksimal 12 Bulan Terakhir
        mc_query = TransaksiTagihan.query.filter_by(nomen=nomen).order_by(desc(TransaksiTagihan.periode)).limit(12).all()
        mc_data = [{
            "periode": mc.periode,
            "nominal": float(mc.total_tagihan or 0),
            "status_lunas": mc.status_lunas,
            "zona_novak": mc.zona_novak
        } for mc in mc_query]

        # 3. Tarik Riwayat Pembayaran (MB) - Maksimal 12 Transaksi Terakhir
        mb_query = DataMB.query.filter_by(nomen=nomen).order_by(desc(DataMB.periode)).limit(12).all()
        mb_data = [{
            "periode": mb.periode,
            "bulan_rek": mb.bulan_rek,
            "tgl_bayar": mb.tgl_bayar,
            "nominal": float(mb.nominal or 0),
            "denda": float(mb.denda or 0),
            "lks_bayar": mb.lks_bayar
        } for mb in mb_query]

        # 4. Tarik Riwayat Meteran (Mainbill) - Maksimal 12 Bulan
        mainbill_query = DataMainbill.query.filter_by(nomen=nomen).order_by(desc(DataMainbill.periode)).limit(12).all()
        mainbill_data = [{
            "periode": mb.periode,
            "read_method": mb.read_method,
            "konsumsi": float(mb.konsumsi or 0),
            "start_read": mb.start_read_stan,
            "end_read": mb.end_read_stan,
            "tagihan_air": float(mb.tagihan_air or 0)
        } for mb in mainbill_query]

        # 5. Tarik Riwayat Anomali Lapangan (SBRS) - Maksimal 12 Bulan
        sbrs_query = DataSBRS.query.filter_by(nomen=nomen).order_by(desc(DataSBRS.periode)).limit(12).all()
        sbrs_data = [{
            "periode": sb.periode,
            "kategori_anomali": sb.kategori_anomali,
            "stand_meter": float(sb.stand_meter or 0),
            "bulan_ini": float(sb.bulan_ini or 0),
            "rata_rata": float(sb.rata_rata or 0),
            "indikasi": sb.raw_data.get('INDIKASI_SINERGI', 'Aman') if sb.raw_data else 'Aman'
        } for sb in sbrs_query]

        # ==========================================
        # SUSUN PAYLOAD SUPER LENGKAP UNTUK FRONTEND
        # ==========================================
        response_payload = {
            "profil_utama": {
                "nomen": cid.nomen,
                "norek": cid.norek,
                "nama": cid.nama,
                "status": cid.status,
                "tarif": cid.tarif,
                "tipe_pelanggan": cid.tipeplggn,
                "merk_meter": cid.merk,
                "no_meter": cid.serial,
                "kontak_wa": cid.wa or cid.hp or "-",
            },
            "detail_alamat": {
                "alamat_lengkap": cid.alamat,
                "kelurahan": cid.kelurahan,
                "kecamatan": cid.kecamatan,
                "wilayah_ab": cid.ab,
                "pcez": cid.pcez,
                "rayon": cid.rayon,
                "kode_pos": cid.kodepos,
                "koordinat": f"{cid.latitude}, {cid.longitude}" if cid.latitude else "Tidak Ada",
                "raw_info_tambahan": raw_cid # Semua 28+ kolom JSONB tumpah di sini
            },
            "history_mc": mc_data,
            "history_mb": mb_data,
            "history_mainbill": mainbill_data,
            "history_sbrs": sbrs_data
        }

        return jsonify(response_payload)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
