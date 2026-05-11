import io
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps

# Inisialisasi Blueprint khusus untuk Optimizer
optimizer_bp = Blueprint('optimizer', __name__)

@optimizer_bp.route('/')
def optimizer_page():
    """Halaman Antarmuka Khusus Kompresi Gambar"""
    return render_template('optimizer.html')

@optimizer_bp.route('/compress', methods=['POST'])
def image_optimizer():
    """API Backend: Kompresi ukuran file gambar sesuai kualitas yang diminta user"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400
        
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return jsonify({"status": "error", "message": "Format harus berupa gambar (.jpg, .png, .webp)!"}), 400
    
    # Ambil tingkat kualitas dari dropdown HTML
    kualitas_str = request.form.get('kualitas', '60')
    try:
        kualitas_val = int(kualitas_str)
    except ValueError:
        kualitas_val = 60
    
    try:
        # Buka gambar menggunakan Pillow
        img = Image.open(file.stream)
        
        # 1. FIX EXIF ORIENTATION: Cegah foto dari kamera HP menjadi miring/terbalik
        img = ImageOps.exif_transpose(img)
        
        # 2. CONVERT TO RGB: Wajib agar support format JPEG
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        # 3. SMART RESIZING: Sesuaikan dimensi maksimal berdasarkan pilihan kualitas
        # Ini menjamin file turun drastis tanpa merusak gambar menjadi kotak-kotak
        max_size = (4000, 4000) # Resolusi Asli / Ringan (85%)
        if kualitas_val <= 15:
            max_size = (800, 800)   # Super Ekstrem
        elif kualitas_val <= 30:
            max_size = (1280, 1280) # Ekstrem
        elif kualitas_val <= 60:
            max_size = (1920, 1920) # Sedang (Standar Email)
            
        # Terapkan resizer dengan metode LANCZOS (Anti-Aliasing terbaik)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 4. MEMORY-ONLY PROCESSING: Gunakan BytesIO agar tidak menulis file sampah di SSD Server
        img_io = io.BytesIO()
        img.save(img_io, "JPEG", quality=kualitas_val, optimize=True)
        img_io.seek(0)
        
        safe_filename = secure_filename(file.filename)
        optimized_filename = safe_filename.rsplit('.', 1)[0] + "_Optimized.jpg"
        
        return send_file(
            img_io, 
            as_attachment=True, 
            download_name=optimized_filename,
            mimetype='image/jpeg'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengompresi gambar: {str(e)}"}), 500
