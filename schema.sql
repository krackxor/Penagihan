-- 1. Tabel Master Pelanggan
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT UNIQUE,
    nama TEXT,
    pcez TEXT,
    rayon TEXT,
    block TEXT,
    nominal REAL,
    tipe TEXT DEFAULT 'MC',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Mapping Rute & Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,
    petugas TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Master Bayar (Lunas)
CREATE TABLE IF NOT EXISTS master_bayar (
    nomen TEXT PRIMARY KEY,
    nominal REAL,
    tgl_bayar TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Kunjungan Petugas (Laporan Lapangan)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    petugas_name TEXT,
    keterangan TEXT,
    no_hp TEXT,
    catatan TEXT,
    janji_bayar_dt TEXT,
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexing untuk Performa Tinggi
CREATE INDEX IF NOT EXISTS idx_nomen_pelanggan ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_pcez_pelanggan ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_nomen_kunjungan ON kunjungan_petugas(nomen);
