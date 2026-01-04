-- 1. Tabel Master Pelanggan (Target Utama dari file MC)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,         
    nama TEXT,
    pcez TEXT,                   
    rayon TEXT,                   -- Kolom untuk menampung data 'PC' dari Excel
    block TEXT,
    nominal REAL,                
    tipe TEXT DEFAULT 'MC',      
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Master Bayar (Pelunasan dari file MB)
CREATE TABLE IF NOT EXISTS master_bayar (
    nomen TEXT PRIMARY KEY, 
    nominal REAL
);

-- 3. Tabel Collection Harian (Pelunasan dari file Collection)
CREATE TABLE IF NOT EXISTS collection_harian (
    nomen TEXT PRIMARY KEY, 
    notag TEXT, 
    nominal REAL
);

-- 4. Tabel Ardebt (Tunggakan dari file Ardebt)
CREATE TABLE IF NOT EXISTS ardebt (
    nomen TEXT PRIMARY KEY,
    jumlah REAL DEFAULT 0,
    volume INTEGER DEFAULT 0,
    periode_bill INTEGER DEFAULT 0
);

-- 5. Tabel Rute Petugas (Mapping PCEZ ke Petugas)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,
    petugas TEXT NOT NULL
);

-- 6. Tabel Kunjungan Petugas (Lengkap dengan Tanggal Janji)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    keterangan TEXT,
    janji_bayar_dt TEXT,         -- Untuk menyimpan tanggal janji bayar
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================================
-- INDEX UNTUK KECEPATAN (Menghilangkan Loading Lama)
-- ==========================================================
CREATE INDEX IF NOT EXISTS idx_mc_nomen ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_col_nomen ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas(nomen);
