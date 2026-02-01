Memindahkan aplikasi dari VPS lama ke VPS baru memang membutuhkan ketelitian agar tidak ada langkah yang terlewat. Karena kamu sudah memiliki domain **areaservice.site**, prosesnya akan lebih cepat karena kita hanya perlu mengarahkan domain ke IP yang baru.

Berikut adalah panduan lengkap setup dari nol untuk aplikasi **Penagihan** kamu:

---

### Langkah 1: Persiapan Server Baru

Masuk ke VPS baru melalui SSH dan update sistemnya.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv nginx git certbot python3-certbot-nginx -y

```

### Langkah 2: Pindahkan Kode Aplikasi

Gunakan Git untuk menarik kode kamu kembali ke VPS baru.

```bash
cd ~
git clone https://github.com/username/penagihan.git Penagihan
cd Penagihan

```

### Langkah 3: Setup Virtual Environment & Install Library

Sangat disarankan menggunakan `venv` agar library tidak bentrok dengan sistem.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

```

### Langkah 4: Inisialisasi Database

Berdasarkan file `schema.sql` yang kamu unggah, kamu perlu membuat database SQLite-nya kembali.

```bash
sqlite3 instance/penagihan.db < schema.sql

```

*(Pastikan folder `instance` sudah ada, jika belum: `mkdir instance`)*.

### Langkah 5: Konfigurasi Nginx (Pintu Masuk)

Buat file konfigurasi baru untuk domain kamu.

```bash
sudo nano /etc/nginx/sites-available/penagihan

```

**Tempelkan kode ini:**

```nginx
server {
    listen 80;
    server_name areaservice.site www.areaservice.site;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

```

**Aktifkan:**

```bash
sudo ln -s /etc/nginx/sites-available/penagihan /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

```

### Langkah 6: Update DNS & SSL

1. **Ganti IP di Dashboard Domain**: Ubah **A Record** domain `areaservice.site` ke **Alamat IP VPS Baru** kamu.
2. **Tunggu sejenak**, lalu jalankan Certbot untuk HTTPS:
```bash
sudo certbot --nginx -d areaservice.site -d www.areaservice.site

```



### Langkah 7: Buat Service agar Aplikasi Jalan Terus (Auto-Run)

Agar aplikasi tidak mati saat kamu keluar dari terminal:

```bash
sudo nano /etc/systemd/system/penagihan.service

```

**Isi dengan:**

```ini
[Unit]
Description=Gunicorn Penagihan
After=network.target

[Service]
User=root
WorkingDirectory=/root/Penagihan
Environment="PATH=/root/Penagihan/venv/bin"
ExecStart=/root/Penagihan/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 --reload "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target

```

**Jalankan:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable penagihan
sudo systemctl start penagihan

```

---

### Tips Cepat: Cara Kill & Run

Jika kamu ingin mematikan dan menjalankan ulang secara manual setelah edit kode:

* **Kill**: `sudo systemctl stop penagihan`
* **Run**: `sudo systemctl start penagihan`
* **Cek Log (Jika error)**: `sudo journalctl -u penagihan -f`

Apakah kamu sudah mendapatkan **Alamat IP** dari VPS baru kamu untuk diupdate di dashboard domain?

Untuk mematikan (kill) dan menjalankan ulang (restart) Gunicorn secara manual, ada dua cara tergantung bagaimana kamu menjalankannya sebelumnya.

### 1. Jika Gunicorn jalan di terminal (kelihatan log-nya)

Cukup tekan tombol ini di keyboard kamu:

* **`Ctrl + C`** (ini akan menghentikan proses Gunicorn).
* Lalu jalankan lagi perintahnya:
```bash
gunicorn --bind 127.0.0.1:5000 --reload "app:create_app()"

```



---

### 2. Jika Gunicorn jalan di background (tidak kelihatan)

Kalau kamu sudah menutup terminal tapi aplikasinya masih jalan, kamu harus mencari "ID" prosesnya lalu mematikannya:

1. **Cari ID Proses (PID):**
```bash
pkill gunicorn

```


*Perintah `pkill` akan langsung mematikan semua proses yang bernama gunicorn.*
2. **Atau cara manual (jika pkill tidak mempan):**
```bash
ps aux | grep gunicorn

```


Lihat angka di kolom kedua (misal: `1234`), lalu ketik:
```bash
kill -9 1234

```


3. **Jalankan lagi:**
```bash
gunicorn --bind 127.0.0.1:5000 --reload "app:create_app()"

```



---

### Tips: Cara Paling Cepat (Satu Baris)

Kamu bisa menggabungkan perintahnya agar setiap kali kamu ketik ini, dia otomatis mati lalu nyala lagi:

```bash
pkill gunicorn; gunicorn --bind 127.0.0.1:5000 --reload "app:create_app()"

```

**Saran Tambahan:**
Karena kamu menggunakan flag `--reload`, sebenarnya kamu **tidak perlu** mematikan dan menjalankan ulang secara manual setiap kali mengedit kode. Gunicorn akan otomatis mendeteksi perubahan file dan me-restart dirinya sendiri. Kamu hanya perlu melakukan *kill & run* jika kamu mengubah konfigurasi server atau ada error yang membuat prosesnya "hang".

Apakah ada error tertentu yang muncul sehingga kamu harus melakukan restart manual?
