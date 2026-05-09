"""
API Module - Monitoring Belum Bayar (V16.6 Sinergi Edition)
---------------------------------------------------------
Logic 1: Jatuh Tempo -> Monitoring MC (Tagihan Baru), Status Overdue jika > Tgl 20.
Logic 2: Berekor -> Monitoring ARDEBT (Hutang Lama), Fokus pada panjang tunggakan.
Konektivitas: Integrasi penuh Geolocation & Contact dari Master Pelanggan.
"""

from flask import Blueprint, jsonify, request
from models import db, MasterPelanggan, TransaksiTagihan
from sqlalchemy import func
from datetime import datetime

# Definisi Blueprint
belum_bayar_bp = Blueprint('belum_bayar', __name__)

@belum_bayar_bp.route('/get-data', methods=['GET'])
def get_belum_bayar_data():
    # Parameter Filter
    tipe = request.args.get('type', 'jatuh_tempo') # 'jatuh_tempo' atau 'berekor'
    ab_filter = request.args.get('ab', 'all')
    
    hari_ini = datetime.now()
    tgl_sekarang = hari_ini.day
    
    try:
        # --- LOGIKA 1: JATUH TEMPO (Tagihan Berjalan dari MC) ---
        if tipe == 'jatuh_tempo':
            # Kita tarik data per-item tagihan
            results = db.session.query(
                TransaksiTagihan.nomen,
                MasterPelanggan.nama,
                MasterPelanggan.ab,
                MasterPelanggan.hp,
                MasterPelanggan.tlp,
                MasterPelanggan.wa,
                MasterPelanggan.latitude,
                MasterPelanggan.longitude,
                TransaksiTagihan.nominal_tagihan,
                TransaksiTagihan.periode_tagihan
            ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
             .filter(TransaksiTagihan.status_lunas == 0)\
             .filter(TransaksiTagihan.sumber_data == 'MC')

            # Filter Wilayah (AB)
            if ab_filter != 'all':
                results = results.filter(MasterPelanggan.ab == ab_filter)

            # Urutkan dari nominal paling besar (Prioritas Auditor)
            results = results.order_by(TransaksiTagihan.nominal_tagihan.desc()).all()
            
            data = []
            for r in results:
                # Alarm Tanggal 20: Jika lewat tgl 20 status otomatis OVERDUE
                status_tempo = "OVERDUE" if tgl_sekarang > 20 else "BELUM TEMPO"
                
                data.append({
                    "nomen": r.nomen,
                    "nama": r.nama,
                    "ab": r.ab,
                    "kontak": {
                        "hp": r.hp if r.hp else "-",
                        "tlp": r.tlp if r.tlp else "-",
                        "wa": r.wa if r.wa else r.hp # Fallback ke HP jika WA kosong
                    },
                    "lokasi": {
                        "lat": r.latitude,
                        "lng": r.longitude
                    },
                    "nominal": r.nominal_tagihan,
                    "periode": r.periode_tagihan,
                    "status_label": status_tempo
                })

        # --- LOGIKA 2: BEREKOR (Tunggakan Lama dari ARDEBT) ---
        else:
            # Agregasi: Menjumlahkan semua tunggakan per pelanggan (Nomen)
            # Kita gunakan func.max untuk data profil agar tidak duplikat saat group by
            results = db.session.query(
                TransaksiTagihan.nomen,
                MasterPelanggan.nama,
                MasterPelanggan.ab,
                func.max(MasterPelanggan.hp).label('hp'),
                func.max(MasterPelanggan.tlp).label('tlp'),
                func.max(MasterPelanggan.wa).label('wa'),
                func.max(MasterPelanggan.latitude).label('lat'),
                func.max(MasterPelanggan.longitude).label('lng'),
                func.count(TransaksiTagihan.id).label('panjang_ekor'),
                func.sum(TransaksiTagihan.nominal_tagihan).label('total_tunggakan')
            ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
             .filter(TransaksiTagihan.status_lunas == 0)\
             .filter(TransaksiTagihan.sumber_data == 'ARDEBT')

            if ab_filter != 'all':
                results = results.filter(MasterPelanggan.ab == ab_filter)

            # Grouping per Nomen dan urutkan dari Ekor yang paling panjang
            results = results.group_by(TransaksiTagihan.nomen)\
                             .order_by(func.count(TransaksiTagihan.id).desc())\
                             .all()

            data = []
            for r in results:
                data.append({
                    "nomen": r.nomen,
                    "nama": r.nama,
                    "ab": r.ab,
                    "kontak": {
                        "hp": r.hp,
                        "tlp": r.tlp,
                        "wa": r.wa if r.wa else r.hp
                    },
                    "lokasi": {
                        "lat": r.lat,
                        "lng": r.lng
                    },
                    "ekor": f"{r.panjang_ekor} Bulan",
                    "nominal": r.total_tunggakan,
                    "status_label": "PIUTANG LAMA"
                })

        return jsonify({
            "status": "success",
            "tipe_data": tipe,
            "total_records": len(data),
            "data": data
        })

    except Exception as e:
        # Logging error untuk mempermudah perbaikan jika file CID/Ardebt ngaco
        print(f"Error Sinergi: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": "Gagal menarik data sinergi. Pastikan master CID sudah di-upload."
        }), 500

@belum_bayar_bp.route('/get-summary-stats', methods=['GET'])
def get_summary():
    """API untuk Widget Ringkasan di Dashboard Atas"""
    try:
        # Total Rupiah MC yang belum lunas
        total_mc = db.session.query(func.sum(TransaksiTagihan.nominal_tagihan))\
            .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.sumber_data == 'MC').scalar() or 0
            
        # Total Rupiah Ardebt yang belum lunas
        total_ardebt = db.session.query(func.sum(TransaksiTagihan.nominal_tagihan))\
            .filter(TransaksiTagihan.status_lunas == 0, TransaksiTagihan.sumber_data == 'ARDEBT').scalar() or 0
            
        return jsonify({
            "status": "success",
            "rupiah_mc": total_mc,
            "rupiah_ardebt": total_ardebt,
            "grand_total": total_mc + total_ardebt
        })
    except:
        return jsonify({"status": "error"})
