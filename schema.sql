-- 1. Tabel Master Pelanggan (Berdasarkan Data MC dan MB)
-- Menyimpan data induk, hasil pecahan ZONA_NOVAK, dan pembeda tipe file
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         -- Diambil dari field NOTAGIHAN pada file MC/MB
    nama TEXT,
    pcez TEXT,                   -- Rumus: PC + "/" + EZ (Contoh: 096/02)
    rayon TEXT,                  -- Rumus: Karakter 1-2 dari ZONA_NOVAK
    pc TEXT,                     -- Rumus: Karakter 3-5 dari ZONA_NOVAK (index 2-5)
    ez TEXT,                     -- Rumus: Karakter 6-7 dari ZONA_NOVAK (index 5-7)
    block TEXT,                  -- Rumus: Karakter 8-9 dari ZONA_NOVAK (index 7-9)
    nominal REAL,                -- Tagihan dari file MC atau MB
    tipe TEXT,                   -- 'MC' untuk Master Catat atau 'MB' untuk Master Bayar
    no_hp TEXT,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Collection Harian (Berdasarkan Data Daily Collection)
-- Digunakan untuk memfilter siapa yang sudah bayar melalui aplikasi daily
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         -- Diambil dari field NOTAG pada file Daily
    notag TEXT,
    pay_dt TEXT,                 -- Tanggal bayar asli dari file
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Ardebt (Berdasarkan Data Tunggakan/Ekor)
CREATE TABLE IF NOT EXISTS ardebt (
    nomen TEXT PRIMARY KEY,
    jumlah REAL DEFAULT 0,       -- Total nominal tunggakan berekor
    volume INTEGER DEFAULT 0,
    periode_bill INTEGER DEFAULT 0, -- Jumlah lembar/bulan menunggak
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Rute Petugas (Berdasarkan Mapping Rute RL JS.xlsx)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,       -- Key pemetaan (Contoh: 096/02)
    petugas TEXT NOT NULL        -- Nama petugas (Contoh: PIAN, TEGUH)
);

-- 5. Tabel Kunjungan Petugas (Laporan Lapangan)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    keterangan TEXT,             -- Hasil kunjungan (Janji Bayar, Sudah Bayar, Rumah Kosong)
    foto_path TEXT,              -- Nama file foto yang diunggah
    latitude TEXT,
    longitude TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabel Upload History (Log Aktivitas)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_type TEXT,              -- MC, MB, COLLECTION, ARDEBT, RUTE
    periode TEXT,                -- Contoh: 01/2026
    status TEXT,                 -- Berhasil / Gagal
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indeks untuk mempercepat pencarian (Optimasi Performa)
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_tipe ON master_pelanggan(tipe); -- Indeks baru untuk filter MC/MB
CREATE INDEX IF NOT EXISTS idx_col_nomen ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_tgl ON kunjungan_petugas(created_at);
