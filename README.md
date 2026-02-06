Menjalankan aplikasi **tanpa venv** berarti Anda akan menginstal semua library Python langsung ke sistem utama Ubuntu. Ini lebih praktis jika VPS tersebut memang hanya digunakan untuk satu aplikasi ini saja.

Berikut adalah panduan instalasi lengkap dari awal tanpa menggunakan venv, lengkap dengan kesimpulan dan tips maintenance:

---

### **Panduan Lengkap Setup Server Penagihan (Tanpa Venv)**

Memindahkan aplikasi dari VPS lama ke VPS baru memang membutuhkan ketelitian. Karena kamu sudah memiliki domain **areaservice.site**, prosesnya akan lebih cepat karena kita hanya perlu mengarahkan domain ke IP yang baru (**174.138.22.143**).

---

#### **Langkah 1: Persiapan Server Baru**

Masuk ke VPS baru melalui SSH dan update sistemnya.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip nginx git certbot python3-certbot-nginx sqlite3 -y

```

#### **Langkah 2: Pindahkan Kode Aplikasi**

Gunakan Git untuk menarik kode kamu kembali ke VPS baru.

```bash
cd ~
git clone https://github.com/username/penagihan.git Penagihan
cd Penagihan

```

#### **Langkah 3: Install Library Langsung ke Sistem**

Karena tidak menggunakan `venv`, kita instal library langsung menggunakan `pip`.

```bash
# Instal library pengolah gambar dan server produksi
pip install Pillow gunicorn
# Instal sisa library dari requirements
pip install -r requirements.txt

```

#### **Langkah 4: Inisialisasi Database**

Buat database SQLite kembali berdasarkan skema yang ada.

```bash
mkdir -p instance
sqlite3 instance/penagihan.db < schema.sql

```

#### **Langkah 5: Konfigurasi Gunicorn Service (Auto-Run)**

Agar aplikasi tidak mati saat terminal ditutup dan sanggup memproses file besar.

1. Buka file: `sudo nano /etc/systemd/system/penagihan.service`
2. Tempelkan kode ini:

```ini
[Unit]
Description=Gunicorn Penagihan
After=network.target

[Service]
User=root
WorkingDirectory=/root/Penagihan
# Jalankan gunicorn langsung dari sistem (tanpa path venv)
ExecStart=/usr/local/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 --timeout 600 --limit-request-line 0 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target

```

3. Aktifkan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable penagihan
sudo systemctl start penagihan

```

#### **Langkah 6: Konfigurasi Nginx (Pintu Masuk)**

Atur Nginx agar mendukung upload file besar dan sinkron dengan timeout Gunicorn.

1. Buka file: `sudo nano /etc/nginx/sites-available/penagihan`
2. Tempelkan kode ini:

```nginx
server {
    listen 80;
    server_name areaservice.site www.areaservice.site;

    client_max_body_size 64M; # Agar file 16MB tidak ditolak

    location / {
        proxy_pass http://127.0.0.1:5000;
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

3. Aktifkan:

```bash
sudo ln -s /etc/nginx/sites-available/penagihan /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

```

#### **Langkah 7: Update DNS & SSL**

1. Ganti IP di Dashboard Domain ke: **174.138.22.143**.
2. Jalankan Certbot untuk HTTPS:

```bash
sudo certbot --nginx -d areaservice.site -d www.areaservice.site

```

---

### **Tips Cepat: Cara Kill & Run (Maintenance)**

Jika kamu ingin mematikan atau menjalankan ulang secara manual setelah edit kode:

**1. Menggunakan Systemd (Rekomendasi)**

* **Kill:** `sudo systemctl stop penagihan`
* **Run:** `sudo systemctl start penagihan`
* **Restart (Update Kode):** `sudo systemctl restart penagihan`
* **Cek Log (Jika error):** `sudo journalctl -u penagihan -f`

**2. Menggunakan Cara Manual (Jika Gunicorn jalan di Background)**

* **Cari ID & Matikan:** `pkill gunicorn`
* **Cara Paksa (Jika pkill gagal):** 1. Cari PID: `ps aux | grep gunicorn`
2. Matikan ID-nya (misal 1234): `kill -9 1234`
* **Jalankan lagi:**
`gunicorn --bind 127.0.0.1:5000 --timeout 600 "app:create_app()"`

---

### **Kesimpulan**

1. **Tanpa Venv Lebih Simpel**: Kamu tidak perlu melakukan `source venv/bin/activate` setiap kali masuk ke server, namun pastikan tidak ada aplikasi Python lain yang versinya bentrok.
2. **Solusi File Besar**: Dengan konfigurasi **timeout 600** dan **client_max_body_size 64M**, file history 16MB kamu kini bisa ter-upload dengan aman tanpa terputus.
3. **Otomatisasi**: Berkat Systemd (Langkah 5), aplikasi akan otomatis nyala sendiri jika server reboot, sehingga web selalu bisa diakses oleh petugas.
4. **Monitoring**: Selalu gunakan perintah `journalctl` jika web menampilkan "Internal Server Error" untuk melihat letak kesalahannya.
