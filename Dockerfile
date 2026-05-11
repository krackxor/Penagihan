# 1. Gunakan base image Python 3.11-slim (Stabil & Ringan)
FROM python:3.11-slim

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set folder kerja
WORKDIR /app

# 4. Instal dependensi sistem (Optimasi: --no-install-recommends & Clean Up)
# Digunakan untuk PostgreSQL, OpenCV, LibreOffice, dan OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libreoffice \
    tesseract-ocr \
    # Paket Bahasa OCR (Tambahkan sesuai kebutuhan utama saja biar tidak terlalu berat)
    tesseract-ocr-ind \
    tesseract-ocr-eng \
    tesseract-ocr-jpn \
    tesseract-ocr-kor \
    tesseract-ocr-chi-sim \
    tesseract-ocr-ara \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 5. Instal Library Python
# Copy requirements duluan agar caching layer Docker bekerja (rebuild secepat kilat)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy seluruh kode project
COPY . .

# 7. Pastikan folder data dan upload siap dengan izin akses yang benar
# Kita gunakan chmod 777 agar Flask tidak kena 'Permission Denied' saat simpan foto/db
RUN mkdir -p /app/instance \
    /app/static/uploads/kunjungan \
    /app/static/uploads/materi \
    && chmod -R 777 /app/instance \
    && chmod -R 777 /app/static/uploads

# 8. Buka port 5000
EXPOSE 5000

# 9. Jalankan aplikasi dengan Gunicorn
# Timeout 1800 (30 menit) cocok untuk proses OCR file PDF raksasa (120MB+)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--timeout", "1800", "--workers", "3"]
