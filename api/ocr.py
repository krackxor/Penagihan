import io
import os
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image
import pytesseract

# Inisialisasi Blueprint untuk modul OCR
ocr_bp = Blueprint('ocr', __name__)

# Kumpulan ekstensi file gambar yang diizinkan untuk di-upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    """Fungsi helper untuk memvalidasi ekstensi file agar hanya menerima gambar."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@ocr_bp.route('/')
def ocr_page():
    """
    Menampilkan Halaman Antarmuka (UI) untuk Tool OCR.
    Pastikan Anda sudah membuat file templates/ocr.html.
    """
    return render_template('ocr.html')

@ocr_bp.route('/extract', methods=['POST'])
def extract_text():
    """
    Mesin Utama: Menerima unggahan gambar, memprosesnya dengan Tesseract OCR,
    dan mengembalikan hasilnya secara langsung dalam bentuk file .txt yang diunduh.
    """
    try:
        # 1. Validasi apakah ada file yang dikirim
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "File gambar tidak ditemukan!"}), 400
        
        file = request.files['file']
        
        # 2. Validasi apakah user tidak memilih file namun menekan submit
        if file.filename == '':
            return jsonify({"status": "error", "message": "Tidak ada file yang dipilih!"}), 400
            
        # 3. Validasi format file (hanya izinkan gambar)
        if not allowed_file(file.filename):
            return jsonify({"status": "error", "message": "Format tidak didukung! Gunakan file PNG, JPG, atau JPEG."}), 400

        # 4. Baca gambar langsung dari stream (RAM) tanpa menyimpannya ke hard disk server
        img = Image.open(file.stream)
        
        # 5. Eksekusi Mesin Tesseract
        # lang='ind' digunakan untuk mengenali teks berbahasa Indonesia dengan lebih akurat
        text_result = pytesseract.image_to_string(img, lang='ind')

        # Jika gambar kosong dari teks atau buram
        if not text_result.strip():
            return jsonify({"status": "error", "message": "Gagal membaca teks. Pastikan foto dokumen terang dan jelas."}), 400

        # 6. Menyiapkan file teks (.txt) di memori virtual menggunakan BytesIO
        proxy = io.BytesIO()
        # Tulis hasil teks ke dalam memori
        proxy.write(text_result.encode('utf-8'))
        # Kembalikan kursor baca ke posisi awal memori
        proxy.seek(0)

        # 7. Siapkan nama file output yang aman
        safe_filename = secure_filename(file.filename)
        output_filename = safe_filename.rsplit('.', 1)[0] + "_Hasil_Ekstrak.txt"
        
        # 8. Tembakkan file tersebut kembali ke browser pengguna untuk otomatis terunduh
        return send_file(
            proxy,
            as_attachment=True,
            download_name=output_filename,
            mimetype='text/plain'
        )

    except Exception as e:
        # Menangkap error bawaan sistem atau library
        return jsonify({"status": "error", "message": f"Kegagalan Sistem Mesin OCR: {str(e)}"}), 500
