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
