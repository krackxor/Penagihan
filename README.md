Siap, Mas Khoirul! Saya sudah memperbarui **`README.md`** Anda ke versi **v13.9**.

Pembaruan ini mencakup penambahan fitur **OCR (Ekstrak Teks Gambar Multi-Bahasa)** ke dalam daftar fitur utama, teknologi yang digunakan, serta langkah instalasi mesin Tesseract di bagian setup server agar siapa pun yang membaca (atau Mas sendiri di kemudian hari) tidak melewatkan langkah krusial tersebut.

Silakan salin dan tempel kode di bawah ini ke GitHub Anda:

```markdown
# 💧 Area Service Integrated System (ASIS) v13.9

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey.svg)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple.svg)

**Area Service Integrated System** adalah platform web terpadu untuk operasional layanan pelanggan, manajemen penagihan, serta alat bantu administratif berbasis web. Sistem ini dirancang khusus untuk memproses data bervolume besar dan memudahkan pekerjaan tim teknis di lapangan maupun di kantor pelayanan.

---

## ✨ Fitur Utama

### 🌐 Akses Publik (Tanpa Login)
* **Cek Tagihan Real-Time:** Pencarian tagihan berdasarkan Nomor ID Pelanggan (Nomen).
* **Portal Informasi:** Tautan cepat untuk Pendaftaran Sambungan Baru dan Layanan Pengaduan Terpadu.
* **Pembersih Format Mainbill:** Alat otomatis untuk menstandarkan format file TXT ke MS Access.
* **Penggabung File Ardebt:** Mesin *chunking* pemroses file bervolume besar (1GB+) untuk penggabungan file TXT secara efisien.
* **Konversi Dokumen:** Fasilitas alih media otomatis (**PDF ke Word**, **Gambar ke PDF**, dan **Word ke PDF** via LibreOffice Engine).
* **Ekstrak Teks Gambar (OCR):** Pemindai teks multi-bahasa dari foto dokumen/struk (Tesseract OCR Engine).

### 🔒 Akses Petugas & Administrator (Dashboard)
* **Monitoring Penagihan:** Lacak performa *collection*, histori pembayaran, dan histori kunjungan.
* **Peta Sebaran (GIS):** Visualisasi lokasi pelanggan dan penandaan anomali di lapangan.
* **Modul Investigasi:** Analitik khusus untuk Pelanggan Drop (>50%), Pelanggan Ekstrem (>100%), dan Pelanggan Premium.
* **Analisa Pareto (Top 500):** Analisis 500 pelanggan dengan konsumsi/tunggakan tertinggi.
* **WA Gateway / Blast:** Sistem notifikasi penagihan massal via WhatsApp.

---

## 🛠️ Teknologi yang Digunakan

* **Backend:** Python (Flask, Werkzeug)
* **Database:** SQLite3
* **Frontend:** HTML5, CSS3, JavaScript (Bootstrap 5, SweetAlert2, Animate.css)
* **Data Processing:** Pandas, Numpy, PapaParse (JS), PyExcel
* **Document & OCR Engine:** PDF2Docx, Pillow, LibreOffice Headless, Tesseract OCR
* **Deployment:** Ubuntu Linux, Nginx, Gunicorn, Systemd, Certbot (SSL)

---

## 🚀 Panduan Setup Server (Production - Ubuntu)

### 1. Persiapan Server & Instalasi Komponen Dasar
Update sistem dan instal aplikasi pendukung utama.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip nginx git certbot python3-certbot-nginx sqlite3 -y

# Instal Engine Konversi & OCR (PENTING)
sudo apt install libreoffice tesseract-ocr tesseract-ocr-all -y

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

Buat file service: `sudo nano /etc/systemd/system/penagihan.service`

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

```bash
sudo systemctl daemon-reload && sudo systemctl enable penagihan && sudo systemctl start penagihan

```

### 5. Konfigurasi Nginx (Reverse Proxy)

Buat blok server: `sudo nano /etc/nginx/sites-available/penagihan`

```nginx
server {
    listen 80;
    server_name areaservice.site www.areaservice.site;
    client_max_body_size 64M;

    location / {
        proxy_pass [http://127.0.0.1:5000](http://127.0.0.1:5000);
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 600;
    }
}

```

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

* **Melihat Log Real-time:** `sudo journalctl -u penagihan -f`
* **Update Kode (Restart):** `sudo systemctl restart penagihan`
* **Cek Status Service:** `sudo systemctl status penagihan`

---

© 2026 Area Service - Hak Cipta Dilindungi.

```

Versi ini sudah sangat lengkap, Mas. Semua komponen "mesin" (LibreOffice dan Tesseract) sudah masuk di urutan instalasi paling awal agar fitur-fitur canggih yang Mas minta tadi langsung menyala begitu server aktif!

```
