import os
from flask import Blueprint, request, jsonify, current_app
from api.helpers import APIResponse
from core.database import get_db_connection
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar', __name__)

def register_belum_bayar_routes(app, get_db):
    """
    Mendaftarkan rute terkait penagihan dan kunjungan petugas.
    Mendukung kategori: All, Undue, Current, dan Berekor.
    """

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        db = get_db()
        
        # Parameter filter dari aplikasi HP
        kategori_filter = request.args.get('kategori', 'all')
        # Konfigurasi Jatuh Tempo (SOP: Tanggal 20)
        TGL_JATUH_TEMPO = 20
        tgl_hari_ini = datetime.now().day

        # Query Utama: Menggabungkan MC, Rute Petugas, Ardebt, dan Filter Collection
        # Rumus Kategori:
        # 1. Berekor = Jika ada saldo di Ardebt (COALESCE(a.jumlah, 0) > 0)
        # 2. Undue = Jika belum bayar, tidak ada ardebt, dan belum tanggal 20
        # 3. Current = Jika belum bayar, tidak ada ardebt, dan sudah tanggal 20 keatas
        query = """
        SELECT 
            m.nomen, 
            m.nama, 
            m.pcez, 
            m.rayon,
            m.block,
            m.no_hp,
            r.petugas as nama_petugas,
            COALESCE(m.nominal, 0) as bill_current,
            COALESCE(a.jumlah, 0) as bill_tail,
            COALESCE(a.periode_bill, 0) as lembar_tunggakan,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            CASE 
                WHEN COALESCE(a.jumlah, 0) > 0 THEN 'Berekor'
                WHEN ? < ? THEN 'Undue'
                ELSE 'Current'
            END as status_tagihan
        FROM master_pelanggan m
        LEFT JOIN rute_petugas r ON m.pcez = r.pcez
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
            AND m.periode_tahun = c.periode_tahun
        WHERE c.id IS NULL 
        AND (m.nominal > 0 OR COALESCE(a.jumlah, 0) > 0)
        """

        params = [tgl_hari_ini, TGL_JATUH_TEMPO]

        # Menambahkan filter dinamis berdasarkan pilihan di menu HP
        if kategori_filter == 'berekor':
            query += " AND COALESCE(a.jumlah, 0) > 0"
        elif kategori_filter == 'undue':
            query += " AND COALESCE(a.jumlah, 0) = 0 AND ? < ?"
            params.extend([tgl_hari_ini, TGL_JATUH_TEMPO])
        elif kategori_filter == 'current':
            query += " AND COALESCE(a.jumlah, 0) = 0 AND ? >= ?"
            params.extend([tgl_hari_ini, TGL_JATUH_TEMPO])

        # Urutkan berdasarkan nominal terbesar (Prioritas Penagihan)
        query += " ORDER BY total_tagihan DESC"
        
        try:
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """
        Menyimpan hasil laporan petugas dari lapangan.
        Termasuk koordinat (opsional), keterangan, dan foto bukti.
        """
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        lat = request.form.get('lat')
        lng = request.form.get('lng')
        
        # Proses Simpan Foto
        foto = request.files.get('foto')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"KUNJUNGI_{nomen}_{timestamp}.jpg"
        
        if foto:
            save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            foto.save(save_path)

        try:
            # 1. Masukkan ke tabel kunjungan_petugas
            db.execute("""
                INSERT INTO kunjungan_petugas 
                (nomen, petugas_name, keterangan, foto_path, latitude, longitude, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, filename, lat, lng, datetime.now()))
            
            # 2. Catat aktivitas ke upload_history agar muncul di LOG
            db.execute("""
                INSERT INTO upload_history (filename, file_type, periode, status)
                VALUES (?, ?, ?, ?)
            """, (filename, 'LAPORAN KUNJUNGAN', datetime.now().strftime('%m/%Y'), 'Berhasil'))
            
            db.commit()
            return APIResponse.success(message="Laporan berhasil terkirim!")
        except Exception as e:
            db.rollback()
            return jsonify({"error": "Gagal menyimpan laporan: " + str(e)}), 500

    @app.route('/api/belum-bayar/summary-pcez', methods=['GET'])
    def get_summary_pcez():
        """
        Menampilkan ringkasan tagihan per PCEZ untuk dashboard mandor/analis.
        """
        db = get_db()
        query = """
        SELECT 
            m.pcez, 
            r.petugas,
            COUNT(m.nomen) as total_pelanggan,
            SUM(m.nominal + COALESCE(a.jumlah, 0)) as total_rupiah
        FROM master_pelanggan m
        LEFT JOIN rute_petugas r ON m.pcez = r.pcez
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
        WHERE c.id IS NULL
        GROUP BY m.pcez
        ORDER BY total_rupiah DESC
        """
        rows = db.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
