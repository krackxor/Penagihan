"""
Ardebt (Tagihan Berekor) API - V6.8 (Sunter Dashboard Pro - Full Sync)
Update: 2026-01-20
---------------------------------------------------------------------------
Pembaruan Strategis:
1. Column Sync: Mengganti 'notagihan' menjadi 'nomen' (Fix: OperationalError).
2. Live Realization: Validasi status lunas via Master Bayar & Collection Harian.
3. Intelligence Layer: Deteksi lonjakan ekstrem atau meteran macet (Kubik 0).
4. Auto-Hide: Data otomatis hilang dari daftar jika sudah dikunjungi hari ini.
"""

from flask import Blueprint, request, jsonify, session, current_app
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

def get_active_target_period(cursor):
    """Mendeteksi periode aktif terbaru yang tersedia di database."""
    res = cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1").fetchone()
    return res['periode'] if res else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/petugas', methods=['GET'])
def get_list_petugas_ardebt():
    """Mengambil daftar petugas unik dari pemetaan rute terbaru."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT DISTINCT petugas FROM rute_petugas WHERE petugas IS NOT NULL ORDER BY petugas ASC"
        cursor.execute(query)
        return jsonify([row['petugas'] for row in cursor.fetchall()])
    except Exception as e:
        return jsonify({"error": f"Sync Petugas Gagal: {str(e)}"}), 500
    finally:
        conn.close()

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_full_intelligence(nomen):
    """Analisis mendalam riwayat pelanggan & deteksi anomali (FIXED: nomen sync)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # [VERIFIKASI RIWAYAT] - Mencocokkan pembayaran Bank & Lapangan secara Live
        cursor.execute("""
            SELECT 
                p.periode, p.kubik as pemakaian_air, p.nominal as rupiah, p.tarif, 
                COALESCE(p.nomet, '-') as no_seri_meter, p.nomen,
                CASE 
                    WHEN EXISTS (
                        SELECT 1 FROM master_bayar mb 
                        WHERE mb.nomen = p.nomen AND mb.periode = p.periode
                    ) THEN 1
                    WHEN EXISTS (
                        SELECT 1 FROM collection_harian ch 
                        WHERE ch.nomen = p.nomen AND ch.periode = p.periode
                    ) THEN 1
                    ELSE p.status_lunas
                END as status_lunas
            FROM master_pelanggan p
            WHERE p.nomen = ? 
            ORDER BY p.id DESC
        """, (nomen,))
        
        history = [dict(row) for row in cursor.fetchall()]

        if not history:
            return jsonify({"status": "not_available", "message": "Data tidak ditemukan"})

        # [SMART ANALYSIS] - Deteksi lonjakan pemakaian (Indikasi bocor)
        analysis = {"saran": "Pemakaian normal.", "level": "success", "count_nunggak": 0}
        analysis["count_nunggak"] = sum(1 for item in history if item['status_lunas'] == 0)

        if len(history) >= 2:
            curr, prev = history[0], history[1]
            if curr['pemakaian_air'] > (prev['pemakaian_air'] * 2) and prev['pemakaian_air'] > 0:
                analysis.update({"saran": "⚠️ LONJAKAN EKSTREM: Indikasi kebocoran pipa!", "level": "danger"})
            elif curr['pemakaian_air'] == 0 and prev['pemakaian_air'] > 0:
                analysis.update({"saran": "🔍 KUBIK 0: Waspada meteran macet/rusak.", "level": "warning"})

        return jsonify({
            "status": "available", 
            "nomen": nomen,
            "analysis": analysis,
            "history": history
        })
    finally:
        conn.close()

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """Daftar kerja Ardebt (Tagihan Berekor) dengan Ultra-Fast Join."""
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    search_query = request.args.get('search', '').strip()
    petugas_filter = request.args.get('petugas', 'all')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        active_period = get_active_target_period(cursor)

        # [QUERY INTI] - Join efisien antara Ardebt (Piutang) dan Master Pelanggan
        query = """
            SELECT 
                a.nomen, a.periode_bill as rincian_periode, 
                a.jumlah as nominal_ardebt, a.volume as volume_ardebt,
                p.nama, p.alamat, COALESCE(p.nomet, '-') as no_seri_meter, 
                p.tarif, p.kubik as pemakaian_air, p.pcez, p.nominal as nominal_mc,
                COALESCE(r.petugas, 'UNMAPPED') as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? AND p.status_lunas = 0
            AND p.nomen NOT IN (SELECT nomen FROM master_bayar WHERE periode = ?)
            AND p.nomen NOT IN (SELECT nomen FROM collection_harian WHERE periode = ?)
        """
        params = [active_period, active_period, active_period]

        # [AUTO-HIDE] - Sembunyikan data yang sudah dikunjungi hari ini
        if not search_query:
            query += """ AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = p.nomen AND k.periode = p.periode
            )"""

        # Role Filtering
        if user_role == 'petugas' and user_petugas_id:
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
            query += " ORDER BY p.kubik DESC"
        else:
            query += " ORDER BY p.kubik DESC LIMIT 50"
        
        cursor.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()])
    except Exception as e:
        current_app.logger.error(f"Ardebt Engine Error: {str(e)}")
        return jsonify({"error": f"Sistem Gagal: {str(e)}"}), 500
    finally:
        conn.close()
