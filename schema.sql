-- 1. Tabel Master Pelanggan (Induk MC)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    nama TEXT,
    pcez TEXT,                   
    rayon TEXT,
    pc TEXT,
    ez TEXT,
    block TEXT,
    nominal REAL,                
    tipe TEXT DEFAULT 'MC',      
    no_hp TEXT,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Master Bayar (Pemisah Pelunasan MB)
-- ERROR "no such table" sering terjadi karena tabel ini belum ada
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    nama TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Collection Harian
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    pay_dt TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Rute Petugas (PENTING untuk file Rute RL JS)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY, 
    petugas TEXT NOT NULL
);

-- 5. Tabel Ardebt & Kunjungan
CREATE TABLE IF NOT EXISTS ardebt (nomen TEXT PRIMARY KEY, jumlah REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    nomen TEXT, 
    petugas_name TEXT, 
    keterangan TEXT, 
    foto_path TEXT, 
    latitude TEXT, 
    longitude TEXT, 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabel Log History
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_type TEXT,
    periode TEXT,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- INDEXING UNTUK KECEPATAN
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
