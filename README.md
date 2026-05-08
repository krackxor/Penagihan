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
