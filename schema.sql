-- Tabel Master Pelanggan (Induk MC)
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

-- Tabel Master Bayar (Pemisah Pelunasan MB)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    nama TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Collection Harian
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    pay_dt TEXT,
    nominal REAL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Kunjungan Petugas
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

-- Tabel Rute & Ardebt
CREATE TABLE IF NOT EXISTS rute_petugas (pcez TEXT PRIMARY KEY, petugas TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ardebt (nomen TEXT PRIMARY KEY, jumlah REAL DEFAULT 0);

-- ==========================================================
-- INDEX UNTUK KECEPATAN TINGGI (SOLUSI LOADING LAMA)
-- ==========================================================
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_col_nomen ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen_tgl ON kunjungan_petugas(nomen, created_at);
