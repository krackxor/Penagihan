-- 1. Tabel Master Pelanggan (Induk Target dari file MC)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    nama TEXT,
    pcez TEXT,                   
    rayon TEXT,
    block TEXT,
    nominal REAL,                
    tipe TEXT DEFAULT 'MC',      
    no_hp TEXT,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Master Bayar (Pelunasan dari file MB)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Collection Harian (Pelunasan dari file Daily Collection)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    notag TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Ardebt (Tunggakan dari file Ardebt)
CREATE TABLE IF NOT EXISTS ardebt (
    nomen TEXT PRIMARY KEY,
    jumlah REAL DEFAULT 0,
    volume INTEGER DEFAULT 0,
    periode_bill INTEGER DEFAULT 0
);

-- 5. Tabel Rute Petugas (Mapping dari file Rute RL JS)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,
    petugas TEXT NOT NULL
);

-- 6. Tabel Kunjungan & History (Tetap Sama)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (id INTEGER PRIMARY KEY AUTOINCREMENT, nomen TEXT, petugas_name TEXT, keterangan TEXT, foto_path TEXT, latitude TEXT, longitude TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS upload_history (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, file_type TEXT, periode TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

-- ==========================================================
-- INDEX UNTUK KECEPATAN INSTAN (SOLUSI LOADING LAMA)
-- ==========================================================
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_col_nomen ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
