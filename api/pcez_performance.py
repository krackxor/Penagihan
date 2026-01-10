"""
PCEZ Performance API - Sunter Dashboard Pro (Smart Autopilot Edition)
Sinergi & Smart Update:
1. Autopilot Transition: Otomatis mendeteksi periode aktif terbaru jika data bulan ini belum tersedia.
2. Smart Casting & Linkage: Normalisasi NOMEN dan NOTAGIHAN untuk akurasi sinkronisasi 100%.
3. Multi-Path Validation: Verifikasi pelunasan real-time via Master Bayar (MB) & Collection Harian.
4. Access Intelligence: Filter dinamis berdasarkan role (Admin Global vs Petugas Personal).
"""

from flask import jsonify, request, session
from datetime import datetime

def register_pcez_routes(app, get_db):
    
    def get_autopilot_periode(db):
        """
        LOGIKA AUTOPILOT:
        Mencari periode terakhir yang tersedia di database. 
        Mencegah dashboard kosong saat tanggal 1-10 (masa transisi data).
        """
        row = db.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
        return row['periode'] if row else datetime.now().strftime('%m-%Y')

    @app.route('/api/performance/full-stats', methods=['GET'])
    def get_full_stats():
        """
        Dashboard Intelijen:
        Mengambil statistik target vs realisasi dengan audit pelunasan ganda.
        """
        try:
            db = get_db()
            today = datetime.now()
            
            # --- 1. IDENTIFIKASI LOGIN & LEVEL AKSES ---
            user_role = str(session.get('role', 'publik')).lower()
            user_petugas_id = session.get('petugas_id') 
            
            # --- 2. PENGATURAN PERIODE (SMART AUTOPILOT) ---
            req_periode = request.args.get('periode')
            if not req_periode:
                # Gunakan Autopilot jika user tidak memilih periode secara manual
                req_periode = get_autopilot_periode(db)

            # --- 3. LOGIKA SMART FILTERING ---
            target_filter = ""
            params_global = []

            # Sinergi Level Akses: Membatasi jangkauan data sesuai identitas petugas
            if user_role == 'petugas':
                target_filter = " AND pcez IN (SELECT pcez FROM rute_petugas WHERE petugas = ?)"
                for _ in range(5):
                    params_global.extend([req_periode, user_petugas_id])
            else:
                # Admin/Guest melihat data global (5 sub-query = 5 periode params)
                params_global = [req_periode] * 5

            # --- 4. QUERY GLOBAL DASHBOARD (SMART SYNC) ---
            # Menggunakan CAST ke TEXT pada NOMEN & NOTAG untuk menjamin kecocokan data (Match)
            global_query = f"""
                SELECT 
                    COALESCE((SELECT COUNT(*) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ? {target_filter}), 0) as total_nomen_mc,
                    COALESCE((SELECT SUM(nominal) FROM master_pelanggan WHERE tipe = 'MC' AND periode = ? {target_filter}), 0) as total_nominal_mc,
                    COALESCE((SELECT SUM(m.nominal) FROM master_pelanggan m 
                        WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                        AND (
                            -- Pintu 1: Cek pelunasan via Master Bayar (Kantor)
                            EXISTS (SELECT 1 FROM master_bayar mb WHERE CAST(mb.nomen AS TEXT) = CAST(m.nomen AS TEXT))
                            OR 
                            -- Pintu 2: Cek pelunasan via Collection Harian (Input Lapangan)
                            EXISTS (SELECT 1 FROM collection_harian c WHERE CAST(c.notag AS TEXT) = CAST(m.notagihan AS TEXT))
                        )
                    ), 0) as nom_terbayar,
                    COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                        WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                        AND EXISTS (SELECT 1 FROM master_bayar mb WHERE CAST(mb.nomen AS TEXT) = CAST(m.nomen AS TEXT))
                    ), 0) as count_undue,
                    COALESCE((SELECT COUNT(DISTINCT m.nomen) FROM master_pelanggan m 
                        WHERE m.tipe = 'MC' AND m.periode = ? {target_filter.replace('pcez', 'm.pcez')}
                        AND EXISTS (SELECT 1 FROM collection_harian c WHERE CAST(c.notag AS TEXT) = CAST(m.notagihan AS TEXT))
                    ), 0) as count_current
            """
            
            # --- 5. QUERY RANKING & PERFORMA PETUGAS ---
            officer_ranking_query = """
                SELECT 
                    COALESCE(r.petugas, k.petugas_name, 'Umum') as petugas,
                    COUNT(*) as total_dijalan,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN 1 ELSE 0 END) as jml_bayar,
                    SUM(CASE WHEN k.keterangan LIKE '%Janji%' THEN 1 ELSE 0 END) as jml_janji,
                    SUM(CASE WHEN k.keterangan LIKE '%Sudah%' THEN (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) ELSE 0 END) as total_nominal
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan mp ON CAST(k.nomen AS TEXT) = CAST(mp.nomen AS TEXT)
                LEFT JOIN rute_petugas r ON mp.pcez = r.pcez
                WHERE k.periode = ?
            """
            
            rank_params = [req_periode]
            if user_role == 'petugas':
                officer_ranking_query += " AND (r.petugas = ? OR k.petugas_name = ?)"
                rank_params.extend([user_petugas_id, user_petugas_id])

            officer_ranking_query += " GROUP BY petugas ORDER BY total_nominal DESC"

            # --- 6. EKSEKUSI & SINKRONISASI AKHIR ---
            g_stat = db.execute(global_query, params_global).fetchone()
            o_rank = db.execute(officer_ranking_query, rank_params).fetchall()
            
            # --- 7. LOG AKTIVITAS LIVE FEED ---
            log_q = """
                SELECT strftime('%H:%M', k.created_at, '+7 hours') as waktu, 
                       k.nomen, mp.nama, k.keterangan, 
                       COALESCE(r.petugas, k.petugas_name) as petugas,
                       (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) as nominal
                FROM kunjungan_petugas k 
                LEFT JOIN master_pelanggan mp ON CAST(k.nomen AS TEXT) = CAST(mp.nomen AS TEXT)
                LEFT JOIN rute_petugas r ON mp.pcez = r.pcez 
                WHERE k.periode = ?
            """
            log_params = [req_periode]
            if user_role == 'petugas':
                log_q += " AND (r.petugas = ? OR k.petugas_name = ?)"
                log_params.extend([user_petugas_id, user_petugas_id])
            
            l_recent = db.execute(log_q + " ORDER BY k.created_at DESC LIMIT 10", log_params).fetchall()
            
            # --- 8. SMART CALCULATION ---
            res_global = dict(g_stat) if g_stat else {}
            # Total Lunas Gabungan (Pintu Kantor + Pintu Lapangan)
            res_global['total_lunas_mc'] = res_global.get('count_undue', 0) + res_global.get('count_current', 0)
            res_global['sisa_nomen'] = max(0, res_global.get('total_nomen_mc', 0) - res_global.get('total_lunas_mc', 0))

            return jsonify({
                "status": "success",
                "active_periode": req_periode, # Memberitahu frontend periode mana yang sedang aktif
                "global": res_global,
                "officers": [dict(row) for row in o_rank],
                "log_petugas": [dict(row) for row in l_recent],
                "role": user_role
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/performance/reminders', methods=['GET'])
    def get_reminders():
        """Janji Bayar dengan Validasi Pelunasan Otomatis."""
        try:
            db = get_db()
            user_role = str(session.get('role', 'publik')).lower()
            user_petugas_id = session.get('petugas_id')
            req_periode = request.args.get('periode') or get_autopilot_periode(db)

            query = """
                SELECT 
                    k.nomen, m.nama, k.no_hp, k.janji_bayar_dt as tanggal_janji,
                    k.catatan, COALESCE(r.petugas, k.petugas_name) as petugas_name,
                    (COALESCE(k.mc, 0) + COALESCE(k.ardebt, 0)) as nominal,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM master_bayar mb WHERE CAST(mb.nomen AS TEXT) = CAST(m.nomen AS TEXT)) OR 
                             EXISTS (SELECT 1 FROM collection_harian c WHERE CAST(c.notag AS TEXT) = CAST(m.notagihan AS TEXT))
                        THEN 'LUNAS' ELSE 'PENDING'
                    END as status_bayar
                FROM kunjungan_petugas k
                LEFT JOIN master_pelanggan m ON CAST(k.nomen AS TEXT) = CAST(m.nomen AS TEXT)
                LEFT JOIN rute_petugas r ON m.pcez = r.pcez
                WHERE k.periode = ? AND k.keterangan LIKE '%Janji%'
            """
            
            params = [req_periode]
            if user_role == 'petugas':
                query += " AND (r.petugas = ? OR k.petugas_name = ?)"
                params.extend([user_petugas_id, user_petugas_id])

            rows = db.execute(query + " ORDER BY k.janji_bayar_dt ASC", params).fetchall()
            return jsonify([dict(row) for row in rows])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
