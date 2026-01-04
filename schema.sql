-- ==========================================================
-- SCHEMA DATABASE PENAGIHAN SUNTER PRO
-- Logic: master_pelanggan (MC) as Parent, master_bayar as Payment Reference
-- ==========================================================

-- 1. Tabel Master Pelanggan (Khusus INDUK MC / Master Catat)
-- Hanya berisi data target penagihan.
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         -- Diambil dari field NOTAGIHAN pada file MC
    nama TEXT,
    pcez TEXT,                   -- Hasil pecah ZONA_NOVAK (PC/EZ)
    rayon TEXT,
    pc TEXT,
    ez TEXT,
    block TEXT,
    nominal REAL,                -- Nilai tagihan asli dari MC
    tipe TEXT DEFAULT 'MC',      -- Label permanen sebagai MC
    no_hp TEXT,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Master Bayar (Khusus DATA MB / Pelunasan Master)
-- Data di sini digunakan untuk mematikan (lunas) target di master_pelanggan.
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         -- Diambil dari field NOTAGIHAN pada file MB
    nama TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Collection Harian (Data Daily Collection)
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

-- 4. Tabel Ardebt (Data Tunggakan / Ekor)
CREATE TABLE IF NOT EXISTS ardebt (
    nomen TEXT PRIMARY KEY,
    jumlah REAL DEFAULT 0,
    volume INTEGER DEFAULT 0,
    periode_bill INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabel Rute Petugas (Mapping PCEZ ke Nama Petugas)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,       -- Format: 096/02
    petugas TEXT NOT NULL        -- Nama Petugas
);

-- 6. Tabel Kunjungan Petugas (Log Aktivitas Lapangan)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    keterangan TEXT,             -- Sudah Bayar, Janji Bayar, RKS, dll
    foto_path TEXT,              -- Nama file foto di folder uploads/kunjungan
    latitude TEXT,
    longitude TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tabel Upload History (Log Aktivitas Admin)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_type TEXT,              -- MC, MB, COLLECTION, ARDEBT, RUTE
    periode TEXT,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================================
-- OPTIMASI INDEX (Mempercepat Dashboard & Filter Lunas)
-- ==========================================================
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_col_nomen ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas(nomen);
CREATE INDEX IF NOT EXISTS idx_kunjungan_tgl ON kunjungan_petugas(created_at);
