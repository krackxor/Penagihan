"""
Ardebt (Tagihan Berekor) API - V6.7 (Sunter Dashboard Pro - Ultra Fast)
Sinergi & Smart Update:
1. Ultra-Fast Join: Menghapus CAST() agar database menggunakan INDEX secara maksimal.
2. Simple Period Logic: Sinkronisasi target harian murni berdasarkan Bulan-Tahun (MM-YYYY).
3. High-Value Priority: Mengurutkan otomatis berdasarkan Kubik (pemakaian air) tertinggi.
4. Smart Auto-Hide: Data otomatis hilang dari daftar kerja jika sudah dikunjungi pada periode berjalan.
"""

from flask import Blueprint, request, jsonify, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime

# Inisialisasi Blueprint untuk modul Ardebt
ardebt_bp = Blueprint('ardebt', __name__)

def get_latest_periode_available(cursor):
    """ Mencari periode terbaru (MM-YYYY) di Master Pelanggan sebagai acuan target aktif. """
    cursor.execute("SELECT periode FROM master_pelanggan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['periode'] if row else datetime.now().strftime('%m-%Y')

@ardebt_bp.route('/petugas', methods=['GET'])
def get_list_petugas_ardebt():
    """ Menampilkan daftar petugas wilayah dengan standarisasi UPPER TRIM. """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT DISTINCT UPPER(TRIM(petugas)) as petugas FROM rute_petugas WHERE petugas != 'UNMAPPED' ORDER BY petugas ASC"
        cursor.execute(query)
        rows = cursor.fetchall()
        return jsonify([row['petugas'] for row in rows])
    except Exception as e:
        return jsonify({"error": f"Gagal sinkron petugas: {str(e)}"}), 500
    finally:
        conn.close()

@ardebt_bp.route('/history/<nomen>', methods=['GET'])
def get_customer_full_intelligence(nomen):
    """ 
    [FUNGSI: AUDIT RIWAYAT] 
    Optimasi: Menggunakan perbandingan TEXT langsung (Tanpa CAST) agar secepat kilat.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Verifikasi Tiga Arah: Langsung menggunakan Index pada nomen (TEXT)
        cursor.execute("""
            SELECT 
                p.periode, p.kubik as pemakaian_air, p.nominal as rupiah, p.tarif, 
                COALESCE(p.nomet, '-') as no_seri_meter, p.notagihan,
                CASE 
                    WHEN EXISTS (
                        SELECT 1 FROM master_bayar mb 
                        WHERE mb.nomen = p.nomen AND mb.notagihan = p.notagihan
                    ) THEN 1
                    WHEN EXISTS (
                        SELECT 1 FROM collection_harian ch 
                        WHERE ch.nomen = p.nomen AND ch.notag = p.notagihan
                    ) THEN 1
                    ELSE 0 
                END as status_lunas
            FROM master_pelanggan p
            WHERE p.nomen = ? 
            ORDER BY p.id DESC
        """, (nomen,))
        
        all_history = [dict(row) for row in cursor.fetchall()]

        if len(all_history) <= 1:
            return jsonify({"status": "not_available", "history": all_history})

        # Analisis Tren Pemakaian
        curr, prev = all_history[0], all_history[1]
        diff_kubik = curr['pemakaian_air'] - prev['pemakaian_air']
        count_nunggak = sum(1 for item in all_history if item['status_lunas'] == 0)
        
        saran, alert_level = "Pemakaian air normal.", "success"
        if curr['pemakaian_air'] > (prev['pemakaian_air'] * 2) and prev['pemakaian_air'] > 0:
            saran, alert_level = "⚠️ Lonjakan >100%: Cek kebocoran!", "danger"
        elif curr['pemakaian_air'] == 0 and prev['pemakaian_air'] > 0:
            saran, alert_level = "🔍 Kubik 0: Waspada meteran macet.", "warning"

        return jsonify({
            "status": "available", "nomen": nomen,
            "analysis": {
                "perubahan": f"{abs(diff_kubik)} m3", "saran": saran, 
                "level": alert_level, "count_nunggak": count_nunggak
            },
            "history": all_history
        })
    finally:
        conn.close()

@ardebt_bp.route('', methods=['GET'])
def get_tunggakan_berekor():
    """
    [ENDPOINT UTAMA: PUSAT KENDALI AREA SERVICE]
    Optimasi: Join tanpa CAST + LIMIT 50 agar loading halaman instant.
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id')
    search_query = request.args.get('search', '').strip()
    petugas_filter = request.args.get('petugas', 'all')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        curr_period = get_latest_periode_available(cursor)

        # Query Utama: Join cepat menggunakan Index MC_LOOKUP & MC_PCEZ
        query = """
            SELECT 
                a.nomen, a.periode_bill as rincian_periode, 
                a.jumlah as nominal_ardebt, a.volume as volume_ardebt,
                p.nama, p.alamat, COALESCE(TRIM(p.nomet), '-') as no_seri_meter, 
                p.tarif, p.kubik as pemakaian_air, p.pcez, p.pc, p.ez, p.blok,
                COALESCE(p.nominal, 0) as nominal_mc,
                COALESCE(UPPER(TRIM(r.petugas)), 'UNMAPPED') as nama_petugas
            FROM ardebt a
            INNER JOIN master_pelanggan p ON a.nomen = p.nomen
            LEFT JOIN rute_petugas r ON p.pcez = r.pcez
            WHERE p.periode = ? AND p.kubik > 0 AND p.status_lunas = 0
        """
        params = [curr_period]

        # Smart Auto-Hide (Menggunakan INDEX idx_kunjungan_nomen_periode agar instan)
        if not search_query:
            query += """ AND NOT EXISTS (
                SELECT 1 FROM kunjungan_petugas k 
                WHERE k.nomen = p.nomen AND k.periode = p.periode
            )"""

        # Filter Role (Petugas hanya melihat areanya sendiri)
        if user_role == 'petugas':
            query += " AND UPPER(TRIM(r.petugas)) = UPPER(TRIM(?))"
            params.append(user_petugas_id)
        elif petugas_filter != 'all':
            query += " AND UPPER(TRIM(r.petugas)) = UPPER(TRIM(?))"
            params.append(petugas_filter)

        # Pengurutan Berbasis Nilai Prioritas (Kubikasi)
        if search_query:
            query += " AND (p.nomen LIKE ? OR p.nama LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
            query += " ORDER BY p.kubik DESC"
        else:
            # LIMIT 50 untuk menjaga kecepatan render di browser HP petugas
            query += " ORDER BY p.kubik DESC LIMIT 50"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        print(f"❌ Error Ardebt List: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
