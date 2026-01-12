"""
Belum Bayar API - Sunter Dashboard Pro (V7.9 Strict Logic Edition)
Sinergi & Smart Update:
1. Strict Current: Mengecualikan nomen yang terdaftar di tabel 'ardebt' agar tidak tercampur.
2. Payment Integrity (Anti-NULL): Mengecek realisasi di MB & Collection menggunakan 'nomen' 
   dan 'periode' untuk menangani kasus di mana 'notagihan' atau 'notag' bernilai NULL.
3. High Value Filter: Tetap mempertahankan batasan nominal >= 300.000 untuk prioritas penagihan.
4. Ultra-Fast Join: Menghapus CAST() agar database menggunakan INDEX secara maksimal.
"""

import os, sqlite3
from flask import Blueprint, jsonify, request, current_app, session
from core.database import get_db_connection
from core.helpers import APIResponse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

belum_bayar_bp = Blueprint('belum_bayar', __name__)

# =========================================================================
# 1. LOGIKA WATERMARK (BUKTI VISUAL LAPANGAN)
# =========================================================================

def add_watermark(image_path, info):
    """ Fungsi Watermark: Menanamkan info penagihan ke foto. """
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        font_size = int(width * 0.035)
        font = None
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
        font = font or ImageFont.load_default()

        text = (
            f"PETUGAS   : {info['petugas']}\n"
            f"IDPEL/NM : {info['nomen']} ({info['nama'][:12]}...)\n"
            f"STATUS    : {info['keterangan']}\n"
            f"TAGIHAN   : Rp {info['nominal']}"
        )

        margin = int(width * 0.04)
        line_height = font_size + 10
        y_pos = height - (line_height * 5) - margin

        # Shadow & Text Utama
        draw.multiline_text((margin + 2, y_pos + 2), text, font=font, fill="black", spacing=10)
        draw.multiline_text((margin, y_pos), text, font=font, fill="#FFFF00", spacing=10)
        
        img.save(image_path, quality=85, optimize=True)
    except Exception as e:
        current_app.logger.error(f"❌ Watermark Error: {str(e)}")

# =========================================================================
# 2. ENDPOINT DAFTAR TARGET (BELUM BAYAR CURRENT ONLY)
# =========================================================================

@belum_bayar_bp.route('', methods=['GET'])
def get_belum_bayar():
    """ 
    [DAFTAR KERJA HARIAN: FOKUS CURRENT & MURNI BELUM BAYAR] 
    Menyaring data agar murni tagihan berjalan yang belum lunas.
    """
    user_role = str(session.get('role', 'guest')).lower()
    user_petugas_id = session.get('petugas_id') 

    petugas_filter = request.args.get('petugas')
    # Sinkronisasi periode agar selalu menggunakan format MM-YYYY
    raw_period = request.args.get('periode') or datetime.now().strftime('%m-%Y
