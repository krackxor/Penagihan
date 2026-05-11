import os
import tempfile
import subprocess
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image
from pdf2docx import Converter

converter_bp = Blueprint('converter', __name__)

@converter_bp.route('/')
def converter_page():
    return render_template('converter.html')

@converter_bp.route('/pdf-to-word', methods=['POST'])
def pdf_to_word():
    if 'file' not in request.files: return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400
    if not file.filename.lower().endswith('.pdf'): return jsonify({"status": "error", "message": "Format harus .pdf!"}), 400
    
    temp_dir = tempfile.mkdtemp()
    safe_filename = secure_filename(file.filename)
    pdf_path = os.path.join(temp_dir, safe_filename)
    docx_filename = safe_filename.rsplit('.', 1)[0] + "_Sinergi.docx"
    docx_path = os.path.join(temp_dir, docx_filename)
    
    try:
        file.save(pdf_path)
        cv = Converter(pdf_path)
        cv.convert(docx_path)
        cv.close()
        return send_file(docx_path, as_attachment=True, download_name=docx_filename, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal konversi PDF ke Word: {str(e)}"}), 500

@converter_bp.route('/word-to-pdf', methods=['POST'])
def word_to_pdf():
    if 'file' not in request.files: return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400
    if not file.filename.lower().endswith(('.docx', '.doc')): return jsonify({"status": "error", "message": "Format harus .docx atau .doc!"}), 400
    
    temp_dir = tempfile.mkdtemp()
    safe_filename = secure_filename(file.filename)
    docx_path = os.path.join(temp_dir, safe_filename)
    file.save(docx_path)
    
    try:
        subprocess.run(['libreoffice', '--headless', '--convert-to', 'pdf', docx_path, '--outdir', temp_dir], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pdf_filename = safe_filename.rsplit('.', 1)[0] + ".pdf"
        pdf_path = os.path.join(temp_dir, pdf_filename)
        final_pdf_filename = safe_filename.rsplit('.', 1)[0] + "_Sinergi.pdf"
        return send_file(pdf_path, as_attachment=True, download_name=final_pdf_filename, mimetype='application/pdf')
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "message": f"Gagal memproses dengan LibreOffice"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Terjadi kesalahan sistem: {str(e)}"}), 500

@converter_bp.route('/image-to-pdf', methods=['POST'])
def image_to_pdf():
    if 'file' not in request.files: return jsonify({"status": "error", "message": "File tidak ditemukan"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')): return jsonify({"status": "error", "message": "Format harus .jpg, .jpeg, atau .png!"}), 400
    
    try:
        img = Image.open(file.stream)
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        temp_dir = tempfile.mkdtemp()
        safe_filename = secure_filename(file.filename)
        pdf_filename = safe_filename.rsplit('.', 1)[0] + "_Sinergi.pdf"
        pdf_path = os.path.join(temp_dir, pdf_filename)
        img.save(pdf_path, "PDF", resolution=100.0)
        return send_file(pdf_path, as_attachment=True, download_name=pdf_filename, mimetype='application/pdf')
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal konversi gambar ke PDF: {str(e)}"}), 500
