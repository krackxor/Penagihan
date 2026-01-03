import os
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar', __name__)

def register_belum_bayar_routes(app, get_db):
    """
    Rute API Cerdas untuk Manajemen Penagihan Lapangan.
    Fitur: Auto-Detect Petugas, Jalur Terdekat, & Target 10 Pelanggan/Hari.
    """

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        
        # Parameter filter dari aplikasi
        petugas_name = request.args.get('petugas', '') # Nama petugas (Pian/Teguh/dll)
        search_query = request.args.get('search', '')  # Pencarian Nomen/Nama
        kategori = request.args.get('kategori', 'all') # all, berekor, undue, current
        
        # Konfigurasi Jatuh Tempo SOP
        TGL_JATUH_TEMPO = 20
        tgl_sekarang = datetime.now().day

        # Query Cerdas: Menggabungkan Master Pelanggan, Ardebt (Ekor), dan Rute Petugas
        # Logika Kategori: Berekor, Undue (Belum JT), Current (Sudah JT)
        query = """
        SELECT 
            m.nomen, m.nama, m.pcez, m.block, m.rayon, m.no_hp,
            r.petugas as nama_petugas,
            COALESCE(m.nominal, 0) as bill_current,
            COALESCE(a.jumlah, 0) as bill_tunggakan,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            CASE 
                WHEN COALESCE(a.jumlah, 0) > 0 THEN 'Berekor'
                WHEN ? < ? THEN 'Undue'
                ELSE 'Current'
            END as status_kategori
        FROM master_pelanggan m
        LEFT JOIN rute_petugas r ON m.pcez = r.pcez
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
            AND m.periode_tahun = c.periode_tahun
        WHERE c.id IS NULL 
        AND (m.nominal > 0 OR COALESCE(a.jumlah, 0) > 0)
        """
        
        params = [tgl_sekarang, TGL_JATUH_TEMPO]

        # Filter berdasarkan Petugas yang dipilih (Mapping Otomatis)
        if petugas_name:
            query += " AND r.petugas = ?"
            params.append(petugas_name)
        
        # Fitur Pencarian Cepat
        if search_query:
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%'])

        # Filter Kategori Tunggakan
        if kategori == 'berekor':
            query += " AND COALESCE(a.jumlah, 0) > 0"

        # LOGIKA CERDAS:
        # 1. Urutkan berdasarkan PCEZ & BLOCK (Jalur terdekat rumah ke rumah)
        # 2. Prioritaskan Tunggakan Berekor (Ardebt) yang paling besar
        # 3. LIMIT 10 agar petugas fokus pada target harian
        query += " ORDER BY m.pcez ASC, m.block ASC, bill_tunggakan DESC LIMIT 10"
        
        try:
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """
        Menyimpan laporan hasil kunjungan lapangan.
        Menyertakan Geo-tagging (GPS) dan bukti foto (Anti-Fraud).
        """
        db = get_db()
        
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        lat = request.form.get('lat') # Koordinat dari HP
        lng = request.form.get('lng') # Koordinat dari HP
        
        # Simpan Foto Bukti Kunjungan
        foto = request.files.get('foto')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"LAPORAN_{nomen}_{timestamp}.jpg"
        
        if foto:
            save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            foto.save(save_path)

        try:
            # 1. Simpan detail kunjungan ke database
            db.execute("""
                INSERT INTO kunjungan_petugas 
                (nomen, petugas_name, keterangan, foto_path, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, filename, lat, lng))
            
            # 2. Update Log Riwayat Aktivitas
            db.execute("""
                INSERT INTO upload_history (filename, file_type, periode, status)
                VALUES (?, 'LAPORAN LAPANGAN', ?, 'Berhasil')
            """, (filename, datetime.now().strftime('%m/%Y')))
            
            db.commit()
            return jsonify({"status": "success", "message": "Target kunjungan berhasil dilaporkan!"})
        except Exception as e:
            db.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/stats-harian', methods=['GET'])
    def get_stats_harian():
        """Mengambil progres 10 target harian petugas"""
        db = get_db()
        petugas = request.args.get('petugas', '')
        today = datetime.now().strftime('%Y-%m-%d')
        
        query = """
            SELECT COUNT(*) as total_done 
            FROM kunjungan_petugas 
            WHERE petugas_name = ? AND date(created_at) = date(?)
        """
        row = db.execute(query, [petugas, today]).fetchone()
        return jsonify({"done": row['total_done'], "target": 10})
