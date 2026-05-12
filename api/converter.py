import os
import io
import shutil
import tempfile
import subprocess
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from pdf2docx import Converter

# Inisialisasi Blueprint
converter_bp = Blueprint('converter', __name__)

@converter_bp.route('/')
def converter_page():
    """Halaman Antarmuka Tool Konversi Dokumen"""
    return render_template('converter.html')

@converter_bp.route('/pdf-to-word', methods=['POST'])
def pdf_to_word():
    """Konversi file PDF ke Word (.docx) dengan Protokol Pembersihan Instan"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({"status": "error", "message": "Harap unggah file berformat .pdf!"}), 400
    
    # Gunakan folder sementara yang aman
    temp_dir = tempfile.mkdtemp()
    try:
        safe_name = secure_filename(file.filename)
        pdf_path = os.path.join(temp_dir, safe_name)
        docx_name = safe_name.rsplit('.', 1)[0] + "_Sinergi.docx"
        docx_path = os.path.join(temp_dir, docx_name)
        
        file.save(pdf_path)
        
        # Eksekusi Mesin Konversi
        cv = Converter(pdf_path)
        cv.convert(docx_path, start=0, multi_processing=True)
        cv.close()
        
        # Stream file langsung ke memori (BytesIO)
        return_data = io.BytesIO()
        with open(docx_path, 'rb') as f:
            return_data.write(f.read())
        return_data.seek(0)
        
        return send_file(
            return_data, 
            as_attachment=True, 
            download_name=docx_name,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Kegagalan Konversi PDF: {str(e)}"}), 500
    finally:
        # PENGHANCUR SAMPAH: Hapus seluruh folder temp
        shutil.rmtree(temp_dir, ignore_errors=True)

@converter_bp.route('/word-to-pdf', methods=['POST'])
def word_to_pdf():
    """Konversi file Word ke PDF menggunakan Headless LibreOffice"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
        
    file = request.files['file']
    if not file.filename.lower().endswith(('.docx', '.doc')):
        return jsonify({"status": "error", "message": "Format harus .docx atau .doc!"}), 400
    
    temp_dir = tempfile.mkdtemp()
    try:
        safe_name = secure_filename(file.filename)
        docx_path = os.path.join(temp_dir, safe_name)
        file.save(docx_path)
        
        # Jalankan LibreOffice Headless (Pastikan apt-get install libreoffice sudah ada di Dockerfile)
        # Kami menggunakan '--nodefault' dan '--nofirststartwizard' agar lebih ringan
        subprocess.run([
            'libreoffice', '--headless', '--invisible', '--nodefault', 
            '--convert-to', 'pdf', docx_path, '--outdir', temp_dir
        ], check=True, timeout=60) # Timeout 60 detik untuk file besar
        
        pdf_name = safe_name.rsplit('.', 1)[0] + ".pdf"
        pdf_path = os.path.join(temp_dir, pdf_name)
        
        return_data = io.BytesIO()
        with open(pdf_path, 'rb') as f:
            return_data.write(f.read())
        return_data.seek(0)
        
        return send_file(
            return_data, 
            as_attachment=True, 
            download_name=f"{safe_name.rsplit('.', 1)[0]}_Sinergi.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": "Gagal memproses Word ke PDF. Pastikan LibreOffice terpasang di sistem."}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@converter_bp.route('/image-to-pdf', methods=['POST'])
def image_to_pdf():
    """Konversi Gambar ke PDF murni di dalam RAM (Zero-Disk Usage)"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
        
    file = request.files['file']
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return jsonify({"status": "error", "message": "Format file tidak didukung!"}), 400
    
    try:
        # Load gambar ke Pillow langsung dari stream Flask
        img = Image.open(file.stream)
        
        # Koreksi Orientasi Otomatis (Cegah gambar miring dari HP)
        img = ImageOps.exif_transpose(img)
        
        # Konversi ke RGB (PENTING: PDF tidak mendukung mode RGBA/Transparency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        pdf_io = io.BytesIO()
        # Simpan sebagai PDF ke RAM dengan kualitas optimal
        img.save(pdf_io, "PDF", resolution=100.0, save_all=True)
        pdf_io.seek(0)
        
        safe_name = secure_filename(file.filename)
        return send_file(
            pdf_io, 
            as_attachment=True, 
            download_name=f"{safe_name.rsplit('.', 1)[0]}_Sinergi.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal konversi gambar: {str(e)}"}), 500
