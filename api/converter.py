import os
import io
import shutil
import tempfile
import subprocess
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from pdf2docx import Converter

# Inisialisasi Blueprint untuk modul Converter
converter_bp = Blueprint('converter', __name__)

@converter_bp.route('/')
def converter_page():
    """Halaman Antarmuka Tool Konversi Dokumen"""
    return render_template('converter.html')

@converter_bp.route('/pdf-to-word', methods=['POST'])
def pdf_to_word():
    """Konversi file PDF ke Word (.docx) dengan Auto-Cleanup"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400
        
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"status": "error", "message": "Format harus .pdf!"}), 400
    
    # Buat folder sementara untuk proses konversi
    temp_dir = tempfile.mkdtemp()
    try:
        safe_filename = secure_filename(file.filename)
        pdf_path = os.path.join(temp_dir, safe_filename)
        docx_filename = safe_filename.rsplit('.', 1)[0] + "_Sinergi.docx"
        docx_path = os.path.join(temp_dir, docx_filename)
        
        file.save(pdf_path)
        
        # Eksekusi konversi
        cv = Converter(pdf_path)
        cv.convert(docx_path)
        cv.close()
        
        # Baca hasil ke memori agar folder bisa langsung dihapus
        return_data = io.BytesIO()
        with open(docx_path, 'rb') as f:
            return_data.write(f.read())
        return_data.seek(0)
        
        return send_file(
            return_data, 
            as_attachment=True, 
            download_name=docx_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal konversi PDF ke Word: {str(e)}"}), 500
    finally:
        # HAPUS SAMPAH: Bersihkan folder temporary secara total
        shutil.rmtree(temp_dir, ignore_errors=True)

@converter_bp.route('/word-to-pdf', methods=['POST'])
def word_to_pdf():
    """Konversi file Word (.docx / .doc) ke PDF menggunakan LibreOffice (Headless)"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400
        
    if not file.filename.lower().endswith(('.docx', '.doc')):
        return jsonify({"status": "error", "message": "Format harus .docx atau .doc!"}), 400
    
    temp_dir = tempfile.mkdtemp()
    try:
        safe_filename = secure_filename(file.filename)
        docx_path = os.path.join(temp_dir, safe_filename)
        file.save(docx_path)
        
        # Jalankan LibreOffice Headless
        subprocess.run([
            'libreoffice', '--headless', '--convert-to', 'pdf', docx_path, '--outdir', temp_dir
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        pdf_filename = safe_filename.rsplit('.', 1)[0] + ".pdf"
        pdf_path = os.path.join(temp_dir, pdf_filename)
        final_pdf_name = safe_filename.rsplit('.', 1)[0] + "_Sinergi.pdf"
        
        # Baca hasil ke memori
        return_data = io.BytesIO()
        with open(pdf_path, 'rb') as f:
            return_data.write(f.read())
        return_data.seek(0)
        
        return send_file(
            return_data, 
            as_attachment=True, 
            download_name=final_pdf_name,
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": "Gagal memproses dengan LibreOffice. Pastikan LibreOffice terinstall di Docker."}), 500
    finally:
        # HAPUS SAMPAH
        shutil.rmtree(temp_dir, ignore_errors=True)

@converter_bp.route('/image-to-pdf', methods=['POST'])
def image_to_pdf():
    """Konversi Gambar ke PDF murni di dalam RAM (Tanpa SSD)"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400
        
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return jsonify({"status": "error", "message": "Format harus gambar!"}), 400
    
    try:
        # Buka gambar dan perbaiki rotasi otomatis (EXIF)
        img = Image.open(file.stream)
        img = ImageOps.exif_transpose(img)
        
        # Wajib ke RGB untuk PDF
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        # Simpan ke stream RAM
        pdf_io = io.BytesIO()
        img.save(pdf_io, "PDF", resolution=100.0)
        pdf_io.seek(0)
        
        safe_filename = secure_filename(file.filename)
        pdf_filename = safe_filename.rsplit('.', 1)[0] + "_Sinergi.pdf"
        
        return send_file(
            pdf_io, 
            as_attachment=True, 
            download_name=pdf_filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal konversi gambar ke PDF: {str(e)}"}), 500
