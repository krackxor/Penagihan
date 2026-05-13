FROM python:3.11-slim

# Install library sistem
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Buat user non-root demi keamanan [cite: 2250]
RUN useradd -m appuser
WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua kode
COPY . .

# Berikan hak akses folder storage
RUN mkdir -p storage/tmp storage/archive logs && chown -R appuser:appuser /app

USER appuser
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--timeout", "1800"]
