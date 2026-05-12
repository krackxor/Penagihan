import io
import traceback
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps

# Inisialisasi Blueprint khusus untuk Optimizer
optimizer_bp = Blueprint('optimizer', __name__)

@optimizer_bp.route('/')
def optimizer_page():
    """Halaman Antarmuka Khusus Kompresi Gambar BAAE V18"""
    return render_template('optimizer.html')

@optimizer_bp.route('/compress', methods=['POST'])
def image_optimizer():
    """
    API Backend BAAE Image Optimizer: 
    Kompresi ukuran file gambar secara dinamis dengan manajemen memori tingkat tinggi.
    """
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Neural Error: File tidak ditemukan!"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Neural Error: Tidak ada file yang dipilih!"}), 400
        
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return jsonify({"status": "error", "message": "Format ditolak! Hanya mendukung .jpg, .png, dan .webp."}), 400
    
    # Ambil tingkat kualitas dari antarmuka pengguna (Default: 60)
    kualitas_str = request.form.get('kualitas', '60')
    try:
        kualitas_val = int(kualitas_str)
    except ValueError:
        kualitas_val = 60
    
    img = None
    try:
        # Buka gambar menggunakan Pillow langsung dari stream memori
        img = Image.open(file.stream)
        
        # 1. FIX EXIF ORIENTATION: Mencegah foto dari kamera HP terbalik/miring
        img = ImageOps.exif_transpose(img)
        
        # 2. CONVERT TO RGB: Wajib membuang Alpha Channel (Transparansi) agar kompatibel dengan JPEG
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        # 3. SMART RESIZING: Penyesuaian dimensi resolusi maksimal
        # Algoritma ini memastikan file turun drastis tanpa terlihat pecah (pixelated)
        max_size = (4000, 4000) # Ringan (85%) - Hampir tanpa kompresi dimensi
        if kualitas_val <= 15:
            max_size = (800, 800)   # Super Ekstrem (Cocok untuk koneksi sinyal buruk)
        elif kualitas_val <= 30:
            max_size = (1280, 1280) # Ekstrem
        elif kualitas_val <= 60:
            max_size = (1920, 1920) # Sedang (Standar Email & Laporan Lapangan)
            
        # Terapkan resizer dengan metode LANCZOS (Anti-Aliasing terbaik di kelasnya)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 4. ZERO-DISK FOOTPRINT: Gunakan BytesIO agar SSD server tidak terbebani file sampah
        img_io = io.BytesIO()
        img.save(img_io, "JPEG", quality=kualitas_val, optimize=True)
        img_io.seek(0)
        
        safe_filename = secure_filename(file.filename)
        optimized_filename = f"BAAE_Optimized_{safe_filename.rsplit('.', 1)[0]}.jpg"
        
        return send_file(
            img_io, 
            as_attachment=True, 
            download_name=optimized_filename,
            mimetype='image/jpeg'
        )
        
    except Exception as e:
        print(traceback.format_exc()) # Cetak jejak error ke Docker logs untuk memudahkan debugging
        return jsonify({"status": "error", "message": f"Fatal Error pada Optimizer: {str(e)}"}), 500
        
    finally:
        # 5. PROTOKOL PEMBERSIHAN MEMORI: Wajib mengeksekusi ini agar RAM Server (Contabo) tidak bocor
        if img is not None:
            img.close()
