-- 1. Tabel Master Pelanggan (Hanya sebagai Induk Data MC)
-- Menyimpan data target penagihan utama
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         -- Diambil dari field NOTAGIHAN pada file MC
    nama TEXT,
    pcez TEXT,                   -- Rumus: PC + "/" + EZ
    rayon TEXT,
    pc TEXT,
    ez TEXT,
    block TEXT,
    nominal REAL,                -- Tagihan asli dari file MC
    tipe TEXT DEFAULT 'MC',      -- Default label sebagai induk target
    no_hp TEXT,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Master Bayar (Pemisahan Baru untuk Pelunasan MB)
-- Digunakan khusus untuk menampung data pelunasan dari file MB
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         -- Diambil dari field NOTAGIHAN pada file MB
    nama TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Collection Harian (Berdasarkan Data Daily Collection)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         -- Diambil dari field NOTAG pada file Daily
    notag TEXT,
    pay_dt TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Ardebt (Berdasarkan Data Tunggakan/Ekor)
CREATE TABLE IF NOT EXISTS ardebt (
    nomen TEXT PRIMARY KEY,
    jumlah REAL DEFAULT 0,
    volume INTEGER DEFAULT 0,
    periode_bill INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabel Rute Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,
    petugas TEXT NOT NULL
);

-- 6. Tabel Kunjungan Petugas (Laporan Lapangan)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    keterangan TEXT,
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tabel Upload History (Log Aktivitas)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_type TEXT,
    periode TEXT,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indeks untuk mengoptimalkan pengecekan Lunas (Kecocokan Nomen)
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_col_nomen ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_tgl ON kunjungan_petugas(created_at);
