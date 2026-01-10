"""
Ardebt (Tagihan Berekor) API - V4.9 (Active User & Ardebt Priority)
Sinergi & Smart Update:
1. Active Filter: Menampilkan hanya pelanggan Ardebt yang memiliki pemakaian air (Kubik > 0).
2. Ardebt Driver: Data utama bersumber dari tabel 'ardebt' (Hasil upload Excel Ardebt).
3. Data Linking: Melengkapi informasi profil (Alamat, Nomet, Tarif) dari Master Pelanggan.
4. Maintenance Friendly: Komentar teknis di setiap blok untuk kemudahan audit/edit.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

def get_latest_periode_available(cursor):
    """
    FUNGSI: Mencari periode terakhir di Master Pelanggan untuk cek status pemakaian (Kubik).
    Mencegah data kosong saat masa transisi awal bulan.
    """
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    # Fallback ke bulan berjalan jika database benar-benar kosong
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_full_intelligence(nomen):
    """
    FUNGSI: Laporan Cerdas Riwayat (Tombol History).
    Menampilkan SEMUA riwayat pemakaian air tanpa batasan limit.
    Mendeteksi potensi kebocoran atau meteran macet secara otomatis.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # --- 1. AMBIL SELURUH RIWAYAT ---
        # CAST AS TEXT digunakan untuk menjaga konsistensi IDPEL
        cursor.execute("""
            SELECT 
                periode, kubik as pemakaian_air, nominal as rupiah, 
                tarif, nomet as no_seri_meter, status_lunas, tgl_lunas
            FROM master_pelanggan 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY id DESC
        """, (nomen,))
        
        all_history = [dict(row) for row in cursor.fetchall()]

        # --- 2. VALIDASI KETERSEDIAAN DATA ---
        if len(all_history) <= 1:
            return jsonify({
                "status": "not_available",
                "message": "Data riwayat pembanding belum tersedia (Pelanggan Baru).",
                "history": all_history
            })

        # --- 3. LOGIKA ANALISIS TREN (SMART ANALYTICS) ---
        curr, prev = all_history[0], all_history[1]
        diff_kubik = curr['pemakaian_air'] - prev['pemakaian_air']
        status_tren = "NAIK" if diff_kubik > 0 else "TURUN"
        saran, alert_level = "Pemakaian air terpantau normal.", "success"
        
        # Deteksi lonjakan drastis
        if curr['pemakaian_air'] > (prev['pemakaian_air'] * 2) and prev['pemakaian_air'] > 0:
            saran, alert_level = "⚠️ POTENSI KEBOCORAN: Pemakaian melonjak >100%!", "danger"
        # Deteksi meteran macet / tidak terbaca
        elif curr['pemakaian_air'] == 0 and prev['pemakaian_air'] > 0:
            saran, alert_level = "🔍 CEK METER: Pemakaian 0 m3. Waspada meter macet.", "warning"

        return jsonify({
            "status": "available",
            "analysis": {
                "perubahan": f"{abs(diff_kubik)} m3 ({status_tren})",
                "saran": saran, "level": alert_level
            },
            "history": all_history
        })
    finally:
        conn.close()

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    ENDPOINT UTAMA: Daftar Penagihan Ardebt Prioritas Pengguna Aktif.
    LOGIKA SINERGI:
    - Hanya mengambil ID yang ada di file Ardebt.
    - Hanya mengambil yang memiliki pemakaian air (Kubik > 0) di periode terbaru.
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        curr_period = get_latest_periode_available(cursor)

        # --- QUERY SINERGI: ARDEBT X ACTIVE MASTER ---
        # Menggunakan INNER JOIN agar hanya pelanggan yang aktif di kedua tabel yang muncul
        query = """
            SELECT 
                a.nomen, 
                a.periode_bill as rincian_periode, 
                a.jumlah as nominal_ardebt, 
                a.volume as volume_ardebt,
                p.nama, 
                p.alamat, 
                p.nomet as no_seri_meter,
                p.tarif,
                p.kubik as pemakaian_air, -- Cek pemakaian air bulan ini
                p.pcez, p.pc, p.ez, p.blok,
                COALESCE(p.nominal, 0) as nominal_mc,
                r.petugas as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON CAST(a.nomen AS TEXT) = CAST(p.nomen AS TEXT)
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
              AND p.kubik > 0        -- [SMART FILTER]: Pastikan ada pemakaian air
              AND p.status_lunas = 0 -- Belum lunas tagihan berjalannya
        """
        params = [curr_period]

        # Keamanan Role: Petugas hanya melihat area kerjanya
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)

        # Filter Pencarian (Nomen atau Nama)
        if search_query:
            query += " AND (a.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        
        # Urutan: Berdasarkan jumlah hutang Ardebt terbesar (Potensi Rupiah)
        query += " ORDER BY a.jumlah DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()
