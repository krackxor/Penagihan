Tentu, mari kita buat panduan ini menjadi **lebih terstruktur, rapi, dan lengkap**.

Panduan ini sudah saya sesuaikan agar mencakup solusi untuk masalah **upload file besar (16MB)** yang sebelumnya gagal karena *timeout* atau limitasi Nginx.

Berikut adalah **"Master Guide: Migrasi & Setup Server Penagihan"**.

---

### 📋 Tahap 1: Persiapan Lingkungan Server (VPS)

Lakukan ini segera setelah login ke VPS baru via SSH.

**1. Update & Install Paket Wajib**

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv nginx git certbot python3-certbot-nginx sqlite3 -y

```

---

### 📥 Tahap 2: Instalasi Kode Aplikasi

**1. Clone Repository**
Pastikan Anda berada di direktori `root` atau `home`.

```bash
cd ~
git clone https://github.com/username/penagihan.git Penagihan
cd Penagihan

```

**2. Setup Virtual Environment (Venv)**
Ini wajib agar library Python terisolasi dan tidak merusak sistem.

```bash
python3 -m venv venv
source venv/bin/activate

```

**3. Install Library & Gunicorn**

```bash
pip install -r requirements.txt
pip install gunicorn

```

**4. Inisialisasi Database**
Kita buat folder database dan isi struktur tabelnya.

```bash
mkdir -p instance
sqlite3 instance/penagihan.db < schema.sql

```

*(Cek apakah file terbentuk dengan `ls instance/`)*.

---

### ⚙️ Tahap 3: Konfigurasi Service Aplikasi (Systemd)

Kita tidak akan menjalankan Gunicorn secara manual. Kita akan menjadikannya **Service** agar otomatis menyala jika server restart, dan kita akan menyematkan konfigurasi **Anti-Timeout** di sini.

**1. Buat File Service**

```bash
sudo nano /etc/systemd/system/penagihan.service

```

**2. Isi Konfigurasi (Copy-Paste Semua)**
*Perhatikan bagian `ExecStart`, kita sudah menambahkan timeout 600 detik (10 menit) untuk menangani upload file besar.*

```ini
[Unit]
Description=Gunicorn Instance untuk Aplikasi Penagihan
After=network.target

[Service]
# User root (atau ganti sesuai user VPS kamu, misal: ubuntu)
User=root
Group=www-data

# Lokasi Folder Aplikasi
WorkingDirectory=/root/Penagihan

# Lokasi Environment Python
Environment="PATH=/root/Penagihan/venv/bin"

# Perintah Eksekusi (PENTING: Timeout 600s & Workers 3)
ExecStart=/root/Penagihan/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 --timeout 600 --limit-request-line 0 "app:create_app()"

[Install]
WantedBy=multi-user.target

```

**3. Aktifkan Service**

```bash
sudo systemctl start penagihan
sudo systemctl enable penagihan

```

---

### 🌐 Tahap 4: Konfigurasi Nginx (Gateway)

Kita harus mengatur Nginx agar menerima file besar (hingga 64MB) dan tidak memutus koneksi saat Gunicorn sedang memproses data.

**1. Buat File Konfigurasi Nginx**

```bash
sudo nano /etc/nginx/sites-available/penagihan

```

**2. Isi Konfigurasi (Copy-Paste Semua)**

```nginx
server {
    listen 80;
    server_name areaservice.site www.areaservice.site;

    # PENTING: Izinkan upload file hingga 64MB
    client_max_body_size 64M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # PENTING: Timeout Nginx disamakan dengan Gunicorn (10 menit)
        proxy_read_timeout 600;
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
    }
}

```

**3. Aktifkan Konfigurasi**

```bash
sudo ln -s /etc/nginx/sites-available/penagihan /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Hapus config default jika ada
sudo nginx -t                             # Cek apakah ada error syntax
sudo systemctl restart nginx

```

---

### 🔒 Tahap 5: Update DNS & SSL (HTTPS)

1. **Update DNS:** Buka panel domain Anda, ubah **A Record** domain `areaservice.site` ke IP VPS Baru.
2. **Install SSL:**
```bash
sudo certbot --nginx -d areaservice.site -d www.areaservice.site

```


*(Ikuti instruksi di layar, pilih Redirect HTTP to HTTPS jika ditanya).*

---

### 🛠️ Cheat Sheet: Perawatan & Monitoring

Simpan daftar perintah ini untuk kebutuhan maintenance sehari-hari:

**1. Aplikasi Error / Habis Update Kode?**
Setiap kali Anda mengubah kode Python (`app.py`, dll), Anda harus merestart service Gunicorn:

```bash
sudo systemctl restart penagihan

```

**2. Mengubah Konfigurasi Nginx?**

```bash
sudo systemctl restart nginx

```

**3. Cek Log Error (Jika ada masalah)**
Gunakan ini untuk melihat kenapa aplikasi error (misal 500 Internal Server Error):

```bash
sudo journalctl -u penagihan -f

```

**4. Cek Log Akses Nginx**

```bash
sudo tail -f /var/log/nginx/error.log

```

Sekarang server Anda sudah siap, aman, dan sanggup menangani upload data besar. Selamat mencoba!
