-- 1. Tabel Master Pelanggan (Data Utama dari file MC)
-- Ditambahkan nomet (Nomor Meter) dan notagihan untuk validasi pintu ganda
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,                  -- ID Pelanggan
    nomet TEXT,                  -- Nomor Meter
    notagihan TEXT,              -- Nomor Tagihan (Pintu Ganda 1)
    nama TEXT,                   -- Nama Pelanggan
    pcez TEXT,                   -- Kode Rute
    rayon TEXT,                  -- Kode Rayon
    block TEXT,                  -- Kode Blok
    nominal REAL,                -- Nominal Tagihan
    tipe TEXT DEFAULT 'MC',      -- Kategori (MC)
    periode TEXT,                -- PERIODE DATA (Pintu Ganda 2 - Contoh: '11-2025')
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Mapping Rute & Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,       -- Kode PCEZ unik
    petugas TEXT,                -- Nama Petugas Lapangan
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Master Bayar (Pelanggan Lunas dari file MB - Status: UNDUE)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    notagihan TEXT,              -- Nomor Tagihan (Pintu Ganda 1)
    nominal REAL,
    tgl_bayar TEXT,
    periode TEXT,                -- PERIODE DATA (Pintu Ganda 2 - Diambil dari BULAN_REK)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Collection Harian (Data Pembayaran Real-time - Status: CURRENT)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    notagihan TEXT,              -- Nomor Tagihan (Pintu Ganda 1 - Di file adalah NOTAG)
    nominal REAL,
    pay_dt TEXT,                 
    periode TEXT,                -- PERIODE DATA (Pintu Ganda 2 - Diambil dari PAY_DT)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabel Ardebt (Data Tunggakan)
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    jumlah REAL,
    volume REAL,
    periode_bill TEXT,           
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabel Kunjungan Petugas (Log Laporan Lapangan)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    petugas_name TEXT,
    keterangan TEXT,             -- Status (Sudah Bayar, Janji Bayar, dll)
    no_hp TEXT,
    catatan TEXT,
    janji_bayar_dt TEXT,
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    periode TEXT,                -- Periode kunjungan dilakukan
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Indeks untuk Performa Kecepatan Tinggi (Indexing)
-- Mempercepat proses sinkronisasi, validasi pintu ganda, dan filter petugas
CREATE INDEX IF NOT EXISTS idx_nomen_pelanggan ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_notag_pelanggan ON master_pelanggan(notagihan);
CREATE INDEX IF NOT EXISTS idx_pcez_pelanggan ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_periode_pelanggan ON master_pelanggan(periode);
CREATE INDEX IF NOT EXISTS idx_notag_mb ON master_bayar(notagihan);
CREATE INDEX IF NOT EXISTS idx_notag_coll ON collection_harian(notagihan);
CREATE INDEX IF NOT EXISTS idx_nomen_kunjungan ON kunjungan_petugas(nomen);

-- TAMBAHAN INDEKS UNTUK OPTIMASI TAGIHAN BEREKOR (ARDEBT)
-- Mempercepat proses SUM(jumlah), COUNT periode, dan pencocokan rute petugas
CREATE INDEX IF NOT EXISTS idx_nomen_ardebt ON ardebt(nomen);
CREATE INDEX IF NOT EXISTS idx_periode_bill_ardebt ON ardebt(periode_bill);
