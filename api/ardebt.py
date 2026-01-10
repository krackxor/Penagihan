"""
Ardebt (Tagihan Berekor) API - Sunter Dashboard Pro (V4.2 Intelligence Edition)
Sinergi & Smart Update:
1. Unlimited History: Menampilkan seluruh rekam jejak pemakaian tanpa batas LIMIT.
2. Intelligence Analytics: Deteksi otomatis potensi kebocoran pipa & meter macet.
3. Availability Guard: Memberikan status "Data Belum Tersedia" jika pelanggan baru (1 periode).
4. Maintenance Friendly: Komentar teknis lengkap di setiap blok untuk kemudahan edit.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

ardebt_bp = Blueprint('ardebt', __name__)

def get_latest_periode_available(cursor):
    """
    FUNGSI CERDAS: Mencari periode terakhir yang tersedia di database.
    Mencegah dashboard kosong selama masa transisi data awal bulan (Tanggal 1-10).
    """
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    # Jika database kosong, gunakan bulan berjalan sebagai fallback
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_full_intelligence(nomen):
    """
    FUNGSI: Laporan Cerdas & Riwayat Tak Terbatas (History Button).
    Menganalisis tren kubikasi dan memberikan saran tindakan otomatis.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # --- 1. AMBIL SELURUH RIWAYAT (UNLIMITED) ---
        # Mengambil semua data dari awal hingga terbaru berdasarkan ID Pelanggan
        cursor.execute("""
            SELECT 
                periode, 
                kubik as pemakaian_air, 
                nominal as rupiah, 
                tarif, 
                nomet as no_seri_meter,
                status_lunas, 
                tgl_lunas
            FROM master_pelanggan 
            WHERE CAST(nomen AS TEXT) = CAST(? AS TEXT) 
            ORDER BY id DESC
        """, (nomen,))
        
        all_history = [dict(row) for row in cursor.fetchall()]

        # --- 2. VALIDASI KETERSEDIAAN DATA PEMBANDING ---
        if len(all_history) <= 1:
            return jsonify({
                "status": "not_available",
                "message": "Data riwayat pembanding belum tersedia (Pelanggan Baru).",
                "history": all_history
            })

        # --- 3. LOGIKA ANALISIS TREN (SINERGI ANALYTICS) ---
        curr = all_history[0]   # Periode Terbaru
        prev = all_history[1]   # Periode Sebelumnya
        
        diff_kubik = curr['pemakaian_air'] - prev['pemakaian_air']
        status_tren = "NAIK" if diff_kubik > 0 else "TURUN"
        
        # Default saran normal
        saran = "Pemakaian air terpantau normal."
        alert_level = "success"
        
        # A. Deteksi Potensi Kebocoran (Lonjakan > 100%)
        if curr['pemakaian_air'] > (prev['pemakaian_air'] * 2) and prev['pemakaian_air'] > 0:
            saran = "⚠️ POTENSI KEBOCORAN: Lonjakan air >100%. Mohon edukasi pelanggan cek instalasi pipa!"
            alert_level = "danger"
            
        # B. Deteksi Meter Macet / Rumah Kosong (Pemakaian 0)
        elif curr['pemakaian_air'] == 0 and prev['pemakaian_air'] > 0:
            saran = "🔍 AUDIT METER: Pemakaian 0 m3. Cek apakah meter macet atau rumah kosong."
            alert_level = "warning"
            
        # C. Deteksi Perubahan Tarif
        elif curr['tarif'] != prev['tarif']:
            saran = "ℹ️ PERUBAHAN TARIF: Ada perubahan golongan tarif dari bulan lalu."
            alert_level = "info"

        return jsonify({
            "status": "available",
            "nomen": nomen,
            "analysis": {
                "perubahan_pemakaian": f"{abs(diff_kubik)} m3 ({status_tren})",
                "saran_tindakan": saran,
                "alert_level": alert_level,
                "total_rekam_jejak": len(all_history)
            },
            "history": all_history # Mengeluarkan seluruh data tanpa batas
        })
        
    except Exception as e:
        print(f"❌ Intelligence API Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    Endpoint Utama: Menampilkan Daftar Tagihan Detail.
    NOMET = No Seri Meter | KUBIK = Pemakaian Air | NOMINAL = Rupiah Tagihan.
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    search_query = request.args.get('search', '').strip()
    petugas_filter = request.args.get('petugas')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        current_period = get_latest_periode_available(cursor)

        # QUERY DETAIL: Mengambil informasi pelanggan lengkap sesuai DB V3.8
        query = f"""
            SELECT 
                p.nomen, p.nama, p.alamat, p.tarif,
                p.nomet as no_seri_meter,    -- Informasi Seri Meter
                p.kubik as pemakaian_air,    -- Informasi Kubikasi
                p.nominal as nominal_mc,     -- Informasi Rupiah
                p.pcez, p.pc, p.ez, p.blok,
                -- SUBQUERY: Menghitung akumulasi rupiah tunggakan bulan-bulan sebelumnya
                COALESCE((
                    SELECT SUM(m2.nominal) FROM master_pelanggan m2 
                    WHERE CAST(m2.nomen AS TEXT) = CAST(p.nomen AS TEXT) AND m2.periode < p.periode
                    AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m2.notagihan)
                ), 0) as total_ardebt,
                -- SUBQUERY: Menghitung jumlah lembar rekening yang menunggak
                (
                    SELECT COUNT(*) FROM master_pelanggan m2 
                    WHERE CAST(m2.nomen AS TEXT) = CAST(p.nomen AS TEXT) AND m2.periode < p.periode
                    AND NOT EXISTS (SELECT 1 FROM master_bayar mb WHERE mb.notagihan = m2.notagihan)
                ) as lembar_berekor,
                r.petugas as nama_petugas
            FROM master_pelanggan p
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ?
            AND p.status_lunas = 0
            AND p.nominal >= 300000 
        """
        params = [current_period]

        # Logika pembatasan data sesuai login petugas
        if user_role == 'petugas':
            query += " AND r.petugas = ?"
            params.append(user_petugas_id)
        elif user_role == 'admin' and petugas_filter and petugas_filter != 'all':
            query += " AND r.petugas = ?"
            params.append(petugas_filter)

        # Logika pencarian cerdas
        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ? OR p.alamat LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
        # Urutkan berdasarkan potensi rupiah tertinggi (Tagihan + Tunggakan)
        query += " ORDER BY (nominal_mc + total_ardebt) DESC LIMIT 50"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()
