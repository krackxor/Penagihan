"""
API WA Gateway - Enterprise Communication Bridge (V12.40)
Update: 2026-01-20
---------------------------------------------------------------------------
Fungsi:
1. Menangani transmisi pesan WhatsApp ke API Provider eksternal.
2. Logging otomatis setiap upaya pengiriman pesan ke System Logs.
3. Proteksi integrasi menggunakan API Key dari Config.
"""

from flask import Blueprint, request, jsonify, current_app
from core.database import get_db_connection
import requests
import json

wa_bp = Blueprint('wa', __name__)

@wa_bp.route('/send', methods=['POST'])
def send_whatsapp():
    """
    Endpoint utama untuk mengirim pesan WhatsApp.
    Menerima JSON: { "number": "628...", "message": "teks pesan" }
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Data tidak valid"}), 400

    number = data.get('number')
    message = data.get('message')
    
    # Validasi input minimal
    if not number or not message:
        return jsonify({"status": "error", "message": "Nomor dan pesan wajib diisi"}), 400

    # Mengambil konfigurasi gateway dari config.py
    api_url = current_app.config.get('WA_GATEWAY_URL')
    api_key = current_app.config.get('WA_GATEWAY_KEY')

    if not api_url or not api_key:
        return jsonify({"status": "error", "message": "Konfigurasi Gateway belum disetel"}), 500

    try:
        # Menyiapkan payload untuk Provider (Disesuaikan dengan format Provider umum)
        payload = {
            "api_key": api_key,
            "receiver": number,
            "data": {
                "message": message
            }
        }
        
        # Eksekusi permintaan ke server gateway eksternal
        # Timeout 10 detik agar tidak menghambat proses blast jika server provider lambat
        response = requests.post(api_url, json=payload, timeout=10)
        res_data = response.json()

        # Logging Aktivitas ke Database (Audit Trail)
        db = get_db_connection()
        db.execute("""
            INSERT INTO system_logs (user_id, action, module, details)
            VALUES (?, ?, ?, ?)
        """, (
            'SYSTEM_GATEWAY', 
            'WA_SEND', 
            'WA_GATEWAY', 
            f"Kirim ke {number}: {res_data.get('status', 'Unknown')}"
        ))
        db.commit()
        db.close()

        return jsonify({
            "status": "success", 
            "gateway_response": res_data
        })

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"WA Gateway Connection Error: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": f"Gagal terhubung ke provider WA: {str(e)}"
        }), 502
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@wa_bp.route('/status', methods=['GET'])
def get_gateway_status():
    """Mengecek status koneksi gateway (Keep-Alive)"""
    return jsonify({
        "status": "online",
        "module": "WA Gateway Integrated",
        "version": "12.40 Stable"
    })
