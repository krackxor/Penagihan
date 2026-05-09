# 1. Gunakan base image Python yang stabil dan ringan
FROM python:3.9-slim

# 2. Set environment variables agar Python tidak membuat file .pyc 
# dan log langsung muncul di terminal Docker (tidak tertahan)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set folder kerja di dalam kontainer
WORKDIR /app

# 4. Instal dependensi sistem (PENTING untuk OCR dan Pengolahan Gambar)
# - tesseract-ocr: Mesin pembaca teks dari foto
# - libgl1: Dibutuhkan untuk library pengolahan gambar
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 5. Copy file requirements dan instal library Python
# Kita copy requirements duluan agar Docker bisa melakukan caching (lebih cepat saat rebuild)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy seluruh kode project ke dalam kontainer
COPY . .

# 7. Pastikan folder data dan upload sudah ada di dalam kontainer
# Folder ini nantinya akan dihubungkan ke komputer Bos lewat docker-compose (Volumes)
RUN mkdir -p /app/instance /app/static/uploads/kunjungan /app/static/uploads/materi

# 8. Buka port 5000 (Port standar Flask)
EXPOSE 5000

# 9. Jalankan aplikasi
# Menggunakan host 0.0.0.0 agar aplikasi bisa diakses dari luar kontainer
CMD ["python", "app.py"]
