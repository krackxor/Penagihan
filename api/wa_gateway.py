"""
API WA Gateway - Enterprise Communication Bridge (V12.40 Stable)
Update: 2026-01-20
---------------------------------------------------------------------------
Fitur Utama:
1. Transmisi pesan WhatsApp melalui API Provider eksternal.
2. Logging otomatis setiap aktivitas pengiriman ke tabel system_logs.
3. Pengaturan Busy Timeout untuk mencegah 'Database is Locked' saat blast.
"""

from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
import requests
import sqlite3

wa_bp = Blueprint('wa', __name__)

@wa_bp.route('/send', methods=['POST'])
def send_whatsapp():
    """
    Endpoint untuk mengirim pesan WhatsApp individu atau massal.
    Payload JSON: { "number": "628...", "message": "isi pesan" }
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Payload JSON tidak ditemukan"}), 400

    number = data.get('number')
    message = data.get('message')
    
    # Validasi input dasar
    if not number or not message:
        return jsonify({"status": "error", "message": "Nomor tujuan dan pesan wajib diisi"}), 400

    # Mengambil kredensial dari Config
    api_url = current_app.config.get('WA_GATEWAY_URL')
    api_key = current_app.config.get('WA_GATEWAY_KEY')

    if not api_url or not api_key:
        return jsonify({"status": "error", "message": "Konfigurasi WA_GATEWAY belum disetel di config.py"}), 500

    try:
        # Payload standar untuk sebagian besar provider WA Gateway API
        payload = {
            "api_key": api_key,
            "receiver": number,
            "data": {
                "message": message
            }
        }
        
        # Eksekusi POST ke Provider dengan timeout 10 detik agar tidak blocking
        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status() # Pastikan status HTTP 200 OK
        res_data = response.json()

        # AUDIT LOG: Catat upaya pengiriman ke database
        # Menggunakan koneksi terpisah untuk menjamin logging berhasil meski database sibuk
        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO system_logs (user_id, action, module, details)
                VALUES (?, ?, ?, ?)
            """, (
                'SYSTEM_GATEWAY', 
                'WA_SEND', 
                'WA_GATEWAY', 
                f"Kirim ke {number} | Status: {res_data.get('status', 'Sent')}"
            ))
            conn.commit()
        except sqlite3.Error as db_err:
            current_app.logger.warning(f"Logging WA Gagal: {db_err}")
        finally:
            conn.close()

        return jsonify({
            "status": "success", 
            "message": "Pesan diteruskan ke provider",
            "gateway_info": res_data
        })

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"WA Gateway Error: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": f"Koneksi ke Provider WA gagal: {str(e)}"
        }), 502
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@wa_bp.route('/status', methods=['GET'])
def get_gateway_status():
    """Endpoint untuk mengecek kesehatan modul gateway"""
    return jsonify({
        "status": "active",
        "module": "WhatsApp Gateway Bridge",
        "version": "12.40-V1"
    })
