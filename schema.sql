-- Tabel Master Pelanggan (Induk Target MC)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    nama TEXT,
    pcez TEXT,                   
    block TEXT,
    nominal REAL,                
    tipe TEXT DEFAULT 'MC',      
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Master Bayar & Collection (Pelunasan)
CREATE TABLE IF NOT EXISTS master_bayar (nomen TEXT PRIMARY KEY, nominal REAL);
CREATE TABLE IF NOT EXISTS collection_harian (nomen TEXT PRIMARY KEY, nominal REAL);

-- Tabel Rute Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (pcez TEXT PRIMARY KEY, petugas TEXT);

-- Tabel Kunjungan Petugas (Ditambah Kolom Janji Bayar)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    keterangan TEXT,             -- Sudah Bayar, Janji Bayar, RKS, dll
    janji_bayar_dt TEXT,         -- Kolom baru untuk tanggal janji bayar
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- INDEXING UNTUK KECEPATAN MAKSIMAL
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas(nomen);
