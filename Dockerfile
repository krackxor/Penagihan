# 1. Gunakan base image Python yang stabil (Versi 3.11-slim lebih kencang)
FROM python:3.11-slim

# 2. Set environment variables
# PYTHONDONTWRITEBYTECODE: Mencegah file .pyc (sampah) memenuhi kontainer
# PYTHONUNBUFFERED: Agar log aplikasi langsung tampil di terminal Docker
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set folder kerja di dalam kontainer
WORKDIR /app

# 4. Instal dependensi sistem (PENTING untuk PostgreSQL, OCR, dan OpenCV)
# - build-essential & libpq-dev: Dibutuhkan untuk koneksi PostgreSQL
# - tesseract-ocr: Mesin pembaca angka meter (OCR)
# - libgl1 & libglib2.0-0: Library wajib untuk pengolahan foto/OpenCV
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 5. Instal Library Python
# Kita copy requirements duluan agar Docker bisa melakukan caching (rebuild jadi lebih cepat)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy seluruh kode project ke dalam kontainer
COPY . .

# 7. Pastikan folder data dan upload sudah tercipta secara otomatis
# Folder ini akan menjadi tempat singgah data raksasa (JSONB) dan foto lapangan
RUN mkdir -p /app/instance \
    /app/static/uploads/kunjungan \
    /app/static/uploads/materi

# 8. Buka port 5000 (Port standar Flask/Gunicorn)
EXPOSE 5000

# 9. Jalankan aplikasi
# Di Docker Compose kita menggunakan Gunicorn, 
# CMD ini sebagai cadangan jika Bos ingin menjalankan kontainer secara mandiri.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--timeout", "1800"]
