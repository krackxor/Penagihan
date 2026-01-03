import os
from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
from datetime import datetime

# Inisialisasi Blueprint
belum_bayar_bp = Blueprint('belum_bayar_api', __name__)

def register_belum_bayar_routes(app, get_db):
    
    @app.route('/api/belum-bayar/petugas-tabs', methods=['GET'])
    def get_petugas_tabs():
        """Mengambil daftar nama petugas unik untuk navigasi Tab"""
        db = get_db()
        try:
            rows = db.execute("""
                SELECT DISTINCT petugas FROM rute_petugas 
                WHERE petugas IS NOT NULL AND petugas != '' 
                ORDER BY petugas ASC
            """).fetchall()
            return jsonify([row['petugas'] for row in rows])
        except Exception as e:
            return jsonify([])

    @app.route('/api/belum-bayar/list', methods=['GET'])
    def get_list_kunjungan():
        """Mengambil data 10 pelanggan per hari (Urut Blok Terdekat)"""
        db = get_db()
        petugas_name = request.args.get('petugas', '')
        search_query = request.args.get('search', '')
        
        TGL_JATUH_TEMPO = 20
        tgl_hari_ini = datetime.now().day

        query = """
        SELECT 
            m.nomen, m.nama, m.pcez, m.block, m.no_hp,
            r.petugas as nama_petugas,
            (COALESCE(m.nominal, 0) + COALESCE(a.jumlah, 0)) as total_tagihan,
            CASE 
                WHEN COALESCE(a.jumlah, 0) > 0 THEN 'Berekor'
                WHEN ? < ? THEN 'Undue'
                ELSE 'Current'
            END as status_kategori
        FROM master_pelanggan m
        INNER JOIN rute_petugas r ON m.pcez = r.pcez
        LEFT JOIN ardebt a ON m.nomen = a.nomen
        LEFT JOIN collection_harian c ON m.nomen = c.nomen 
            AND m.periode_bulan = c.periode_bulan
        WHERE c.id IS NULL
        """
        params = [tgl_hari_ini, TGL_JATUH_TEMPO]

        if petugas_name and petugas_name != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_name)
        
        if search_query:
            query += " AND (m.nomen LIKE ? OR m.nama LIKE ? OR m.block LIKE ?)"
            params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

        # Cerdas: Rute terdekat (PCEZ & BLOK) dengan LIMIT 10
        query += " ORDER BY m.pcez ASC, m.block ASC LIMIT 10"
        
        try:
            rows = db.execute(query, params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/simpan-kunjungan', methods=['POST'])
    def simpan_kunjungan():
        """Simpan ke Database dan Kirim Teks WA ke Frontend"""
        db = get_db()
        nomen = request.form.get('nomen')
        petugas = request.form.get('petugas')
        keterangan = request.form.get('keterangan')
        no_hp = request.form.get('no_hp')
        foto = request.files.get('foto')

        # Ambil detail untuk pesan WA
        pel = db.execute("SELECT nama, pcez, block FROM master_pelanggan WHERE nomen = ?", (nomen,)).fetchone()
        nama_pel = pel['nama'] if pel else "-"
        pcez_pel = pel['pcez'] if pel else "-"

        filename = None
        if foto:
            filename = f"BUKTI_{nomen}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            save_path = os.path.join(current_app.config['KUNJUNGAN_FOLDER'], filename)
            foto.save(save_path)

        try:
            # 1. Simpan Laporan
            db.execute("""
                INSERT INTO kunjungan_petugas (nomen, petugas_name, keterangan, foto_path, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (nomen, petugas, keterangan, filename, datetime.now()))

            # 2. Update No HP (Enrichment)
            if no_hp:
                db.execute("UPDATE master_pelanggan SET no_hp = ? WHERE nomen = ?", (no_hp, nomen))
            
            db.commit()

            # 3. Buat Format Pesan WA
            wa_text = (
                f"📢 *LAPORAN PENAGIHAN*\n"
                f"--------------------------------\n"
                f"👤 *Petugas:* {petugas}\n"
                f"🆔 *Nomen:* {nomen}\n"
                f"🏠 *Nama:* {nama_pel}\n"
                f"📍 *PCEZ:* {pcez_pel}\n"
                f"📝 *Hasil:* {keterangan}\n"
                f"📱 *No HP:* {no_hp if no_hp else '-'}\n"
                f"--------------------------------"
            )

            return jsonify({"status": "success", "wa_text": wa_text})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/belum-bayar/stats-harian', methods=['GET'])
    def get_stats_harian():
        db = get_db()
        petugas = request.args.get('petugas', '')
        today = datetime.now().strftime('%Y-%m-%d')
        row = db.execute("SELECT COUNT(*) as done FROM kunjungan_petugas WHERE petugas_name = ? AND date(created_at) = date(?)", (petugas, today)).fetchone()
        return jsonify({"done": row['done'] if row else 0, "target": 10})
