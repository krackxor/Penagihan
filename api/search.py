from flask import Blueprint, render_template, request, jsonify
from models import db, MasterPelanggan
from sqlalchemy import or_

# Inisialisasi Blueprint untuk modul Pencarian Global
search_bp = Blueprint('search', __name__)

@search_bp.route('/')
def search_page():
    """Menampilkan UI Halaman Pencarian Universal"""
    return render_template('search.html')

@search_bp.route('/api/query', methods=['GET'])
def execute_search():
    """
    API Mesin Pencari Real-Time V18.
    Merespons permintaan secara instan dengan dukungan ekstraksi No Meter & No HP.
    """
    keyword = request.args.get('q', '').strip()
    
    # PROTEKSI: Batasi pencarian minimal 3 karakter agar RAM/CPU Server tidak terbebani
    if len(keyword) < 3:
        return jsonify([])

    # Gunakan wildcard % agar bisa mencari kata di tengah kalimat (Fleksibel)
    search_term = f"%{keyword}%"

    try:
        # Eksekusi pencarian ke beberapa kolom sekaligus (OR)
        # Sesuai dengan 28 Kolom di skema V18 (serial = No Meter)
        query = MasterPelanggan.query.filter(
            or_(
                MasterPelanggan.nomen.ilike(search_term),
                MasterPelanggan.nama.ilike(search_term),
                MasterPelanggan.alamat.ilike(search_term),
                MasterPelanggan.serial.ilike(search_term),
                MasterPelanggan.wa.ilike(search_term),
                MasterPelanggan.hp.ilike(search_term)
            )
        ).limit(20).all() # Batasi maksimal 20 hasil agar browser HP tidak lag/stuck

        results = []
        for p in query:
            # Logika Pembersihan Tampilan Teks Kosong (None)
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
                "no_hp": no_hp_aktif
            })
            
        return jsonify(results)

    except Exception as e:
        import traceback
        print(traceback.format_exc()) # Cetak ke log Docker jika terjadi kegagalan query
        return jsonify({"error": str(e)}), 500
