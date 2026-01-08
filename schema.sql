-- Sunter Dashboard Pro - Database Schema
-- Updated: 2026-01-08 (Full Synergy for Collection Monitoring & Field Activity)

-- 1. Tabel Master Pelanggan (Data Utama dari file MC)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,          -- ID Pelanggan
    nomet TEXT,                   -- Nomor Meter
    notagihan TEXT,               -- Nomor Tagihan (Pintu Ganda 1)
    nama TEXT,                    -- Nama Pelanggan
    pcez TEXT,                    -- Kode Rute (Standard: XXX/XX)
    rayon TEXT,                   -- Kode Rayon (PENTING: '34' atau '35' untuk Monitoring)
    block TEXT,                   -- Kode Blok
    nominal REAL DEFAULT 0,       -- Nominal Tagihan
    volume REAL DEFAULT 0,        -- Volume Air / Kubik
    tipe TEXT DEFAULT 'MC',       -- Kategori (MC)
    periode TEXT,                 -- PERIODE DATA (Contoh: '01-2026')
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode) 
);

-- 2. Tabel Mapping Rute & Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,        -- Kode PCEZ unik sebagai primary key
    petugas TEXT NOT NULL,        -- Nama Petugas Lapangan
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Master Bayar (Pelanggan Lunas dari file MB - Status: UNDUE)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notagihan TEXT,               -- Link ke master_pelanggan.notagihan
    nominal REAL DEFAULT 0,
    tgl_bayar TEXT,
    periode TEXT,                 -- PERIODE DATA (N+1)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode)
);

-- 4. Tabel Collection Harian (Data Pembayaran Real-time - Status: CURRENT)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notag TEXT,                   -- Link ke master_pelanggan.notagihan
    nominal REAL DEFAULT 0,
    pay_dt TEXT,                  -- Tanggal pembayaran (YYYY-MM-DD)
    periode TEXT,                 -- Format MM-YYYY
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notag, periode)
);

-- 5. Tabel Ardebt (Data Tunggakan Berekor)
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,          -- Link ke master_pelanggan.nomen
    jumlah REAL DEFAULT 0,        -- Total biaya tunggakan
    volume REAL DEFAULT 0,        -- Total pemakaian air
    periode_bill TEXT,            -- Periode tunggakan (Raw)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabel Kunjungan Petugas (Log Laporan Lapangan & Janji Bayar)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    keterangan TEXT,              -- Status (Sudah Bayar, Janji Bayar, RKS, dll)
    no_hp TEXT,
    catatan TEXT,
    janji_bayar_dt TEXT,          -- Tanggal yang dijanjikan pelanggan untuk membayar
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    periode TEXT,                 -- Periode bulan berjalan saat kunjungan
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tabel Riwayat Unggahan (Log Admin)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,               -- MC, MB, Collection, Ardebt, Rute
    periode TEXT,
    row_count INTEGER,
    status TEXT,                  -- Success / Error
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Indeks untuk Performa Kecepatan Tinggi (Indexing)

-- Indeks pada NOMEN untuk Join antar tabel yang cepat
CREATE INDEX IF NOT EXISTS idx_nomen_pelanggan ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_mb ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_coll ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_ardebt ON ardebt(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_kunjungan ON kunjungan_petugas(nomen);

-- Indeks pada RAYON & PERIODE (Krusial untuk Monitoring Collection Harian)
CREATE INDEX IF NOT EXISTS idx_rayon_pelanggan ON master_pelanggan(rayon);
CREATE INDEX IF NOT EXISTS idx_periode_pelanggan ON master_pelanggan(periode);
CREATE INDEX IF NOT EXISTS idx_paydt_coll ON collection_harian(pay_dt);

-- Indeks pada NOTAGIHAN / NOTAG (Validasi Pintu Ganda)
CREATE INDEX IF NOT EXISTS idx_notag_pelanggan ON master_pelanggan(notagihan);
CREATE INDEX IF NOT EXISTS idx_notag_mb ON master_bayar(notagihan);
CREATE INDEX IF NOT EXISTS idx_notag_coll ON collection_harian(notag);

-- Indeks untuk Fitur Pengingat Janji Bayar
CREATE INDEX IF NOT EXISTS idx_janji_bayar_dt ON kunjungan_petugas(janji_bayar_dt);

-- Indeks Tambahan untuk Filter Dashboard & Kunjungan
CREATE INDEX IF NOT EXISTS idx_pcez_pelanggan ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_periode ON kunjungan_petugas(periode);
CREATE INDEX IF NOT EXISTS idx_kunjungan_tanggal ON kunjungan_petugas(created_at);
