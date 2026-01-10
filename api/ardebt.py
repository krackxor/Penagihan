"""
Ardebt (Tagihan Berekor) API - V6.0 (Smart Routing & Professional Logic)
Sinergi & Smart Update:
1. High Priority: Mengurutkan data berdasarkan pemakaian air (Kubik) tertinggi.
2. Smart Auto-Hide: Data otomatis hilang dari daftar jika sudah dikunjungi pada periode berjalan.
3. Daily Quota: Membatasi tampilan 20 target per hari untuk efektivitas petugas.
4. Global Search: Fitur pencarian tetap dapat menemukan data meskipun sudah dikunjungi.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

def get_latest_periode_available(cursor):
    """
    FUNGSI: Mencari periode terbaru di Master Pelanggan.
    Kegunaan: Menentukan 'Current Period' untuk sinkronisasi data MC dan Ardebt.
    """
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_full_intelligence(nomen):
    """
    FUNGSI: Laporan Audit Riwayat Pelanggan.
    Logic: 
    - Melakukan verifikasi 3 arah (Master Pelanggan, Master Bayar, dan Collection).
    - Menghitung 'J-Count' (Jumlah lembar tunggakan).
    - Menganalisis lonjakan kubikasi (Potensi Kebocoran).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # --- 1. QUERY VERIFIKASI TIGA ARAH ---
        # Memastikan status bayar akurat antara Bank (MB) dan Setoran Lapangan (CH)
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

        # --- 2. VALIDASI DATA KOSONG ---
        if len(all_history) <= 1:
            return jsonify({
                "status": "not_available",
                "message": "Data riwayat pembanding belum tersedia.",
                "history": all_history
            })

        # --- 3. ANALISIS TREN & J-COUNT ---
        curr, prev = all_history[0], all_history[1]
        diff_kubik = curr['pemakaian_air'] - prev['pemakaian_air']
        status_tren = "NAIK" if diff_kubik > 0 else "TURUN"
        
        # J-COUNT: Menghitung jumlah lembar yang belum terbayar (Status 0)
        count_nunggak = sum(1 for item in all_history if item['status_lunas'] == 0)
        
        saran, alert_level = "Pemakaian air terpantau normal.", "success"
        if curr['pemakaian_air'] > (prev['pemakaian_air'] * 2) and prev['pemakaian_air'] > 0:
            saran, alert_level = "⚠️ Lonjakan >100%: Cek potensi kebocoran!", "danger"
        elif curr['pemakaian_air'] == 0 and prev['pemakaian_air'] > 0:
            saran, alert_level = "🔍 Kubik 0: Waspada meteran macet.", "warning"

        return jsonify({
            "status": "available",
            "nomen": nomen,
            "analysis": {
                "perubahan": f"{abs(diff_kubik)} m3 ({status_tren})",
                "saran": saran, 
                "level": alert_level,
                "count_nunggak": count_nunggak
            },
            "history": all_history
        })
    finally:
        conn.close()

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    ENDPOINT UTAMA: Daftar Target Harian Petugas (Smart Routing).
    Logika Sinergi V6.0:
    1. Filter Kubik > 0 (Hanya rumah berpenghuni/aktif).
    2. NOT EXISTS: Menghilangkan data yang sudah dikunjungi hari ini/periode ini.
    3. Order By Kubik DESC: Prioritas pelanggan dengan pemakaian air tertinggi.
    4. Limit 20: Memberikan kuota harian yang terukur untuk petugas.
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        curr_period = get_latest_periode_available(cursor)

        # --- 1. BASE QUERY DENGAN LOGIKA AUTO-HIDE ---
        # Menampilkan IDPEL yang ada di ARDEBT tapi belum dikunjungi di periode ini
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

        # --- 2. LOGIKA AUTO-HIDE KUNJUNGAN ---
        # Hanya aktif jika TIDAK dalam mode pencarian (Search mengabaikan filter ini)
        if not search_query:
            query += """ AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE CAST(k.nomen AS TEXT) = CAST(a.nomen AS TEXT) 
                AND k.periode = p.periode
            )"""

        # Filter Keamanan Role Petugas
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)

        # --- 3. FILTER PENCARIAN & PRIORITAS KUBIKASI ---
        if search_query:
            query += " AND (a.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
            # Mode cari: Tanpa limit agar semua data lama ketemu
            query += " ORDER BY p.kubik DESC"
        else:
            # Mode Standar: Prioritas Kubik Tinggi & Limit 20 (Target Harian)
            query += " ORDER BY p.kubik DESC LIMIT 20"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()
