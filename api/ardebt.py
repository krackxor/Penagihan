"""
Ardebt (Tagihan Berekor) API - V5.0 (Triple-Check Sinergi)
Sinergi & Smart Update:
1. Triple-Check Logic: Verifikasi status lunas melalui Master Bayar (MB) DAN Collection Harian.
2. Active User Priority: Memfilter pelanggan yang masih memiliki pemakaian air (Kubik > 0).
3. Unlimited History: Menarik seluruh riwayat tanpa batas untuk audit piutang berekor.
4. Maintenance Friendly: Komentar teknis di setiap blok untuk kemudahan audit/edit.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

def get_latest_periode_available(cursor):
    """
    FUNGSI: Mencari periode terbaru di Master Pelanggan.
    Digunakan untuk menentukan status pemakaian air aktif (Kubik) saat ini.
    """
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_full_intelligence(nomen):
    """
    FUNGSI: Laporan Cerdas Riwayat (Skakmat Logic).
    LOGIKA: 
    - Baris WAJIB MERAH (Status 0) jika p.notagihan TIDAK ADA di MB dan TIDAK ADA di COLLECTION.
    - Menghitung jumlah baris merah sebagai 'Count Periode Bill' (tunggakan lembar).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # --- 1. QUERY SINERGI: VERIFIKASI TIGA ARAH (MC vs MB vs COLLECTION) ---
        # CASE WHEN mengecek ketersediaan notagihan di dua tabel pembayaran sekaligus
        cursor.execute("""
            SELECT 
                p.periode, 
                p.kubik as pemakaian_air, 
                p.nominal as rupiah, 
                p.tarif, 
                p.nomet as no_seri_meter, 
                p.notagihan,
                CASE 
                    WHEN EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = p.notagihan) THEN 1
                    WHEN EXISTS (SELECT 1 FROM collection_harian ch WHERE ch.notag = p.notagihan) THEN 1
                    ELSE 0 
                END as status_lunas
            FROM master_pelanggan p
            WHERE CAST(p.nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY p.id DESC
        """, (nomen,))
        
        all_history = [dict(row) for row in cursor.fetchall()]

        # --- 2. VALIDASI DATA ---
        if len(all_history) <= 1:
            return jsonify({
                "status": "not_available",
                "message": "Data riwayat pembanding belum tersedia (Pelanggan Baru).",
                "history": all_history
            })

        # --- 3. LOGIKA ANALISIS TREN & COUNT TUNGGAKAN ---
        curr, prev = all_history[0], all_history[1]
        diff_kubik = curr['pemakaian_air'] - prev['pemakaian_air']
        status_tren = "NAIK" if diff_kubik > 0 else "TURUN"
        
        # Hitung manual jumlah lembar yang status_lunas-nya 0
        count_nunggak = sum(1 for item in all_history if item['status_lunas'] == 0)
        
        saran, alert_level = "Pemakaian air terpantau normal.", "success"
        if curr['pemakaian_air'] > (prev['pemakaian_air'] * 2) and prev['pemakaian_air'] > 0:
            saran, alert_level = "⚠️ POTENSI KEBOCORAN: Lonjakan air >100%!", "danger"
        elif curr['pemakaian_air'] == 0 and prev['pemakaian_air'] > 0:
            saran, alert_level = "🔍 CEK METER: Pemakaian 0 m3. Waspada meter macet.", "warning"

        return jsonify({
            "status": "available",
            "nomen": nomen,
            "analysis": {
                "perubahan": f"{abs(diff_kubik)} m3 ({status_tren})",
                "saran": saran, 
                "level": alert_level,
                "count_nunggak": count_nunggak  # Mengirimkan jumlah bulan nunggak ke frontend
            },
            "history": all_history
        })
    finally:
        conn.close()

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    ENDPOINT UTAMA: Daftar Ardebt Prioritas Pengguna Aktif.
    LOGIKA: Driver Ardebt JOIN Master Pelanggan dengan filter Kubik > 0.
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        curr_period = get_latest_periode_available(cursor)

        query = """
            SELECT 
                a.nomen, a.periode_bill as rincian_periode, 
                a.jumlah as nominal_ardebt, a.volume as volume_ardebt,
                p.nama, p.alamat, p.nomet as no_seri_meter, p.tarif,
                p.kubik as pemakaian_air, p.pcez, p.pc, p.ez, p.blok,
                COALESCE(p.nominal, 0) as nominal_mc,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON CAST(a.nomen AS TEXT) = CAST(p.nomen AS TEXT)
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
              AND p.kubik > 0 
              AND p.status_lunas = 0
        """
        params = [curr_period]

        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)

        if search_query:
            query += " AND (a.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        
        query += " ORDER BY a.jumlah DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()
