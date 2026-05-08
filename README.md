```markdown
# 💧 Area Service Integrated System (ASIS) v13.8

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey.svg)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple.svg)

**Area Service Integrated System** adalah platform web terpadu untuk operasional layanan pelanggan, manajemen penagihan, serta alat bantu administratif berbasis web. Sistem ini dirancang khusus untuk memproses data bervolume besar dan memudahkan pekerjaan tim teknis di lapangan maupun di kantor pelayanan.

---

## ✨ Fitur Utama

### 🌐 Akses Publik (Tanpa Login)
* **Cek Tagihan Real-Time:** Pencarian tagihan berdasarkan Nomor ID Pelanggan (Nomen).
* **Portal Informasi:** Tautan cepat untuk Pendaftaran Sambungan Baru dan Layanan Pengaduan Terpadu (WhatsApp, Call Center, Email).
* **Pembersih Format Mainbill:** Alat otomatis untuk menstandarkan format file TXT ke MS Access (Pemisah Semicolon, Pembersihan Desimal, UTF-8 BOM).
* **Penggabung File Ardebt:** Mesin *chunking* pemroses file bervolume besar (1GB+) di RAM lokal untuk menggabungkan banyak file menjadi satu dokumen dengan injeksi Header standar.
* **Konversi Dokumen:** Fasilitas alih media otomatis untuk merubah **PDF ke Word**, **Gambar ke PDF**, dan **Word ke PDF** (Didukung oleh LibreOffice Engine).

### 🔒 Akses Petugas & Administrator (Dashboard)
* **Monitoring Penagihan:** Lacak performa *collection*, histori pembayaran, dan histori kunjungan.
* **Peta Sebaran (GIS):** Visualisasi lokasi pelanggan dan penandaan anomali di lapangan.
* **Modul Investigasi:** Analitik khusus untuk Pelanggan Drop (>50% penurunan), Pelanggan Ekstrem (>100% lonjakan), dan Pelanggan Premium.
* **Analisa Pareto (Top 500):** Analisis 500 pelanggan dengan konsumsi/tunggakan tertinggi.
* **WA Gateway / Blast:** Sistem notifikasi penagihan massal via WhatsApp.

---

## 🛠️ Teknologi yang Digunakan

* **Backend:** Python (Flask, Werkzeug)
* **Database:** SQLite3
* **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5, SweetAlert2, Animate.css, FontAwesome 6
* **Data Processing:** Pandas, Numpy, PapaParse (JS), PyExcel
* **Document Engine:** PDF2Docx, Pillow, LibreOffice Headless
* **Deployment:** Ubuntu Linux, Nginx, Gunicorn, Systemd, Certbot (SSL)

---

## 🚀 Panduan Setup Server (Production - Ubuntu)

Panduan ini ditujukan untuk *deployment* pada *Dedicated VPS* menggunakan mode Global (Tanpa Venv). 

### 1. Persiapan Server & Instalasi Komponen
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip nginx git certbot python3-certbot-nginx sqlite3 libreoffice -y

```

### 2. Kloning Repository & Instalasi Library

```bash
cd ~
git clone [https://github.com/username-anda/penagihan.git](https://github.com/username-anda/penagihan.git) Penagihan
cd Penagihan

# Instal library secara global (untuk Ubuntu 23.04+)
pip install gunicorn --break-system-packages
pip install -r requirements.txt --break-system-packages

```

### 3. Inisialisasi Database

```bash
mkdir -p instance
sqlite3 instance/penagihan.db < schema.sql

```

### 4. Konfigurasi Gunicorn (Auto-Run Service)

Buat file service systemd:

```bash
sudo nano /etc/systemd/system/penagihan.service

```

Isi dengan konfigurasi berikut:

```ini
[Unit]
Description=Gunicorn Service untuk Area Service
After=network.target

[Service]
User=root
WorkingDirectory=/root/Penagihan
ExecStart=/usr/local/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 --timeout 600 --limit-request-line 0 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target

```

Aktifkan Service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable penagihan
sudo systemctl start penagihan

```

### 5. Konfigurasi Nginx (Reverse Proxy)

Buat blok server Nginx:

```bash
sudo nano /etc/nginx/sites-available/penagihan

```

Isi dengan:

```nginx
server {
    listen 80;
    server_name areaservice.site www.areaservice.site;

    client_max_body_size 64M;

    location / {
        proxy_pass [http://127.0.0.1:5000](http://127.0.0.1:5000);
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 600;
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
    }
}

```

Aktifkan Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/penagihan /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

```

### 6. Aktivasi SSL HTTPS

```bash
sudo certbot --nginx -d areaservice.site -d www.areaservice.site

```

---

## ⚙️ Operasional & Perawatan (Maintenance)

Perintah cepat untuk manajemen aplikasi di server:

* **Melihat Log Error:** `sudo journalctl -u penagihan -f`
* **Restart Aplikasi (Setelah update kode):** `sudo systemctl restart penagihan`
* **Mematikan Aplikasi:** `sudo systemctl stop penagihan`

---

© 2026 Area Service - Hak Cipta Dilindungi.

```

Tampilannya di GitHub nanti akan sangat rapi dengan dukungan tabel otomatis, *highlighting* warna kode (syntax), dan tombol *copy* langsung di terminalnya. Kalau ada logo PAM JAYA atau logo aplikasi yang mau diselipkan, tinggal taruh link gambarnya di bagian atas ya Mas!

```
