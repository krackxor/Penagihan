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
    API Mesin Pencari Real-Time.
    Merespons permintaan dari Alpine.js secara instan.
    """
    keyword = request.args.get('q', '').strip()
    
    # PROTEKSI: Batasi pencarian minimal 3 karakter agar RAM/CPU Server tidak jebol
    if len(keyword) < 3:
        return jsonify([])

    # Gunakan wildcard % agar bisa mencari kata di tengah kalimat (Fleksibel)
    search_term = f"%{keyword}%"

    try:
        # Eksekusi pencarian ke beberapa kolom sekaligus (OR)
        query = MasterPelanggan.query.filter(
            or_(
                MasterPelanggan.nomen.ilike(search_term),
                MasterPelanggan.nama.ilike(search_term),
                MasterPelanggan.alamat.ilike(search_term)
                # Catatan: Jika di models.py Anda ada kolom 'wa' atau 'no_meter', 
                # hapus tanda '#' di bawah ini agar bisa dicari juga:
                # MasterPelanggan.wa.ilike(search_term),
                # MasterPelanggan.no_meter.ilike(search_term)
            )
        ).limit(20).all() # Batasi maksimal 20 hasil agar browser HP tidak lag

        results = []
        for p in query:
            results.append({
                "nomen": p.nomen,
                "nama": p.nama,
                "alamat": p.alamat,
                "kelurahan": p.kelurahan,
                "pcez": p.pcez,
                # Menggunakan getattr sebagai pengaman. 
                # Jika kolom 'no_meter' atau 'wa' tidak ada di database, tidak akan error (Crash).
                "no_meter": getattr(p, 'no_meter', '-'),
                "no_hp": getattr(p, 'wa', getattr(p, 'telp', '-'))
            })
            
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
