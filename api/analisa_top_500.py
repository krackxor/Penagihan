from flask import Blueprint, jsonify, request
from models import db, MasterPelanggan, TransaksiTagihan

analisa_top500_bp = Blueprint('analisa_top500', __name__)

@analisa_top500_bp.route('/get-top-500', methods=['GET'])
def get_top_500():
    periode = request.args.get('periode') # Contoh: 202604
    ab_filter = request.args.get('ab')     # Contoh: AB Dewaruci
    
    if not periode:
        return jsonify({"status": "error", "message": "Periode harus dipilih"}), 400

    # Query Utama Sinergi
    query = db.session.query(
        TransaksiTagihan.nomen,
        MasterPelanggan.nama,
        MasterPelanggan.ab,
        MasterPelanggan.type_cust1,
        TransaksiTagihan.nominal_tagihan,
        TransaksiTagihan.status_lunas
    ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
     .filter(TransaksiTagihan.periode_tagihan == periode)

    # Filter AB jika dipilih
    if ab_filter and ab_filter != 'all':
        query = query.filter(MasterPelanggan.ab == ab_filter)

    # Ambil Top 500 berdasarkan Nominal Terbesar
    results = query.order_by(TransaksiTagihan.nominal_tagihan.desc()).limit(500).all()

    data = []
    for r in results:
        data.append({
            "nomen": r.nomen,
            "nama": r.nama,
            "ab": r.ab,
            "tipe": r.type_cust1,
            "nominal": r.nominal_tagihan,
            "lunas": "LUNAS" if r.status_lunas == 1 else "BELUM BAYAR"
        })

    return jsonify({"status": "success", "data": data})
