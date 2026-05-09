"""
API Module - Top 500 Integrated Analysis
Fungsi: Mengambil 500 pelanggan dengan tagihan terbesar secara real-time
Sinergi: Menggabungkan data MC (Tagihan) dan CID (Wilayah/Tipe)
"""

from flask import Blueprint, jsonify, request, send_file
from models import db, MasterPelanggan, TransaksiTagihan
import pandas as pd
import io
from datetime import datetime

analisa_top500_bp = Blueprint('analisa_top500', __name__)

@analisa_top500_bp.route('/get-top-500', methods=['GET'])
def get_top_500():
    """Mengambil data Top 500 untuk tampilan tabel di Dashboard"""
    periode = request.args.get('periode')  # Format: YYYYMM
    ab_filter = request.args.get('ab')      # Contoh: AB Dewaruci
    tipe_filter = request.args.get('tipe')  # Regular / Corporate
    
    if not periode:
        return jsonify({"status": "error", "message": "Periode harus ditentukan (YYYYMM)."}), 400

    try:
        # QUERY SINERGI: Join Tagihan (MC/Ardebt) dengan Master Pelanggan (CID)
        query = db.session.query(
            TransaksiTagihan.nomen,
            MasterPelanggan.nama,
            MasterPelanggan.ab,
            MasterPelanggan.type_cust1,
            TransaksiTagihan.nominal_tagihan,
            TransaksiTagihan.status_lunas,
            TransaksiTagihan.periode_tagihan
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)

        # Filter Periode
        query = query.filter(TransaksiTagihan.periode_tagihan == periode)

        # Filter Area Bisnis (AB)
        if ab_filter and ab_filter != 'all':
            query = query.filter(MasterPelanggan.ab == ab_filter)
            
        # Filter Tipe Pelanggan
        if tipe_filter and tipe_filter != 'all':
            query = query.filter(MasterPelanggan.type_cust1 == tipe_filter)

        # ORDER & LIMIT: Ambil 500 Terbesar
        results = query.order_by(TransaksiTagihan.nominal_tagihan.desc()).limit(500).all()

        data = []
        for r in results:
            data.append({
                "nomen": r.nomen,
                "nama": r.nama,
                "ab": r.ab,
                "tipe": r.type_cust1,
                "nominal": r.nominal_tagihan,
                "status": "LUNAS" if r.status_lunas == 1 else "BELUM BAYAR"
            })

        return jsonify({
            "status": "success",
            "count": len(data),
            "data": data
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@analisa_top500_bp.route('/export-top-500', methods=['GET'])
def export_top_500():
    """Mengekspor daftar Top 500 ke Excel menggunakan BytesIO (Anti-Leak)"""
    periode = request.args.get('periode')
    ab_filter = request.args.get('ab')

    try:
        # Logika query sama dengan get_top_500
        query = db.session.query(
            TransaksiTagihan.nomen.label('NOMEN'),
            MasterPelanggan.nama.label('NAMA_PELANGGAN'),
            MasterPelanggan.ab.label('AREA_BISNIS'),
            MasterPelanggan.type_cust1.label('TIPE'),
            TransaksiTagihan.nominal_tagihan.label('NOMINAL'),
            TransaksiTagihan.status_lunas.label('STATUS_LUNAS')
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode_tagihan == periode)

        if ab_filter and ab_filter != 'all':
            query = query.filter(MasterPelanggan.ab == ab_filter)

        results = query.order_by(TransaksiTagihan.nominal_tagihan.desc()).limit(500).all()

        # Konversi ke Pandas DataFrame
        df = pd.DataFrame([r._asdict() for r in results])
        
        # Mapping Status Lunas agar lebih mudah dibaca di Excel
        if not df.empty:
            df['STATUS_LUNAS'] = df['STATUS_LUNAS'].apply(lambda x: 'LUNAS' if x == 1 else 'BELUM BAYAR')

        # Simpan ke memory buffer (Bukan harddisk) untuk mencegah storage leak
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Top500')
        
        output.seek(0)
        
        filename = f"Top_500_{ab_filter or 'Semua_AB'}_{periode}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return f"Gagal ekspor: {str(e)}", 500
