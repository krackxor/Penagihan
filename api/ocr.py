import io
import os
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, ImageEnhance # Ditambah ImageEnhance untuk ketajaman teks
import pytesseract

# Inisialisasi Blueprint untuk modul BAAE Intelligence OCR
ocr_bp = Blueprint('ocr', __name__)

# Ekstensi file gambar yang diizinkan oleh sistem BAAE
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    """Memvalidasi ekstensi file gambar."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@ocr_bp.route('/')
def ocr_page():
    """Menampilkan UI Tools OCR BAAE Nexus."""
    return render_template('ocr.html')

@ocr_bp.route('/extract', methods=['POST'])
def extract_text():
    """
    BAAE Neural Extraction Engine V18:
    Memproses gambar dengan Tesseract OCR dilengkapi Filter Kontras Tingkat Tinggi.
    """
    try:
        # 1. Validasi keberadaan file
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "Neural Error: File gambar tidak terdeteksi!"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"status": "error", "message": "Neural Error: Input kosong!"}), 400
            
        if not allowed_file(file.filename):
            return jsonify({"status": "error", "message": "Neural Error: Format file ditolak sistem BAAE!"}), 400

        # 2. Proses gambar langsung di memori (Memory-Efficient)
        img = Image.open(file.stream)
        
        # [OPTIMASI 1] Luruskan Orientasi Gambar (Mencegah teks miring/terbalik dari kamera HP)
        img = ImageOps.exif_transpose(img)
        
        # [OPTIMASI 2] Ubah gambar menjadi Grayscale (Hitam-Putih)
        if img.mode != 'L':
            img = img.convert('L')
            
        # [OPTIMASI 3] Tingkatkan Kontras 2x Lipat (Sangat ampuh untuk foto buram/struk pudar)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # 3. Eksekusi Mesin Tesseract
        # Menggunakan bahasa Indonesia & Inggris. 
        # config '--psm 6' mengasumsikan teks adalah satu blok seragam, mencegah teks berantakan.
        language_pack = 'ind+eng'
        custom_config = r'--oem 3 --psm 6'
        
        text_result = pytesseract.image_to_string(img, lang=language_pack, config=custom_config)

        # Bebaskan memori gambar setelah selesai dibaca
        img.close()

        # 4. Validasi hasil ekstraksi
        if not text_result.strip():
            return jsonify({
                "status": "error", 
                "message": "Neural Error: Gagal mengekstrak teks. Pastikan gambar tajam dan pencahayaan cukup."
            }), 400

        # 5. Konversi hasil ke stream file .txt untuk download otomatis
        proxy = io.BytesIO()
        proxy.write(text_result.encode('utf-8'))
        proxy.seek(0)

        # 6. Formatting Nama File Output BAAE
        safe_filename = secure_filename(file.filename)
        output_filename = f"BAAE_OCR_{safe_filename.rsplit('.', 1)[0]}.txt"
        
        return send_file(
            proxy,
            as_attachment=True,
            download_name=output_filename,
            mimetype='text/plain'
        )

    except Exception as e:
        # Menangkap kegagalan inisialisasi model bahasa atau error sistem lainnya
        import traceback
        print(traceback.format_exc()) # Tulis ke log Docker untuk debugging
        return jsonify({
            "status": "error", 
            "message": f"Fatal System Crash (OCR Engine): Pastikan tesseract-ocr dan tesseract-ocr-ind sudah terinstall di server. Detail: {str(e)}"
        }), 500
