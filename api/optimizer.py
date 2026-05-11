import os
import tempfile
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image

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
        img = Image.open(file.stream)
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        temp_dir = tempfile.mkdtemp()
        safe_filename = secure_filename(file.filename)
        optimized_filename = safe_filename.rsplit('.', 1)[0] + "_Optimized.jpg"
        optimized_path = os.path.join(temp_dir, optimized_filename)
        
        # Eksekusi kompresi
        img.save(optimized_path, "JPEG", quality=kualitas_val, optimize=True)
        
        return send_file(
            optimized_path, 
            as_attachment=True, 
            download_name=optimized_filename,
            mimetype='image/jpeg'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengompresi gambar: {str(e)}"}), 500
