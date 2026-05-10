import io
import os
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image
import pytesseract

# Inisialisasi Blueprint untuk modul BAAE Intelligence OCR
ocr_bp = Blueprint('ocr', __name__)

# Ekstensi file gambar yang diizinkan oleh sistem BAAE
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

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
    BAAE Neural Extraction Engine:
    Memproses gambar dengan Tesseract OCR menggunakan model multi-bahasa global.
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
        
        # 3. Eksekusi Mesin Tesseract dengan Dukungan Multi-Bahasa Global
        # ind: Indonesia, eng: Inggris, jpn: Jepang, kor: Korea, 
        # chi_sim/tra: China (Simp/Trad), ara: Arab
        language_pack = 'ind+eng+jpn+kor+chi_sim+chi_tra+ara'
        
        text_result = pytesseract.image_to_string(img, lang=language_pack)

        # 4. Validasi hasil ekstraksi
        if not text_result.strip():
            return jsonify({
                "status": "error", 
                "message": "Neural Error: Gagal mengekstrak teks. Pastikan gambar tajam dan tidak noise."
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
        return jsonify({
            "status": "error", 
            "message": f"Fatal System Crash (OCR Engine): {str(e)}"
        }), 500
