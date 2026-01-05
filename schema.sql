-- 1. Tabel Master Pelanggan (Data Utama dari file MC)
-- Ditambahkan nomet (Nomor Meter) dan periode (Multi-Bulan)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,                 -- ID Pelanggan
    nomet TEXT,                 -- Nomor Meter (Tambahan Baru)
    nama TEXT,                  -- Nama Pelanggan
    pcez TEXT,                  -- Kode Rute
    rayon TEXT,                 -- Kode Rayon
    block TEXT,                 -- Kode Blok
    nominal REAL,               -- Nominal Tagihan
    tipe TEXT DEFAULT 'MC',     -- Kategori (MC, MB, dll)
    periode TEXT,               -- PERIODE DATA (Contoh: '06-2025' dari TGL_CATAT)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Mapping Rute & Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,      -- Kode PCEZ unik
    petugas TEXT,               -- Nama Petugas Lapangan yang ditugaskan
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Master Bayar (Pelanggan Lunas dari file MB)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    nominal REAL,
    tgl_bayar TEXT,
    periode TEXT,               -- PERIODE DATA (Contoh: '06-2025' dari TGL_BAYAR)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Collection Harian (Data Pembayaran Real-time)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    notag TEXT,
    nominal REAL,
    pay_dt TEXT,                -- Field asli dari file
    periode TEXT,               -- PERIODE DATA (Contoh: '07-2025' dari PAY_DT)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabel Ardebt (Data Tunggakan)
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,
    jumlah REAL,
    volume REAL,
    periode_bill TEXT,          -- Periode tunggakan (Sesuai Bill)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabel Kunjungan Petugas (Log Laporan Lapangan)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,                 -- ID Pelanggan terkait
    petugas_name TEXT,          -- Nama Petugas yang melapor
    keterangan TEXT,            -- Status (Sudah Bayar, Janji Bayar, RKS, dll)
    no_hp TEXT,                 -- Input No HP baru dari lapangan
    catatan TEXT,               -- Keterangan tambahan
    janji_bayar_dt TEXT,        -- Tanggal jika Janji Bayar
    foto_path TEXT,             -- Nama file foto yang tersimpan
    latitude TEXT,              -- Lokasi GPS
    longitude TEXT,             -- Lokasi GPS
    periode TEXT,               -- Periode kunjungan dilakukan (Contoh: '07-2025')
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Indeks untuk Performa Kecepatan Tinggi (Indexing)
CREATE INDEX IF NOT EXISTS idx_nomen_pelanggan ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_pcez_pelanggan ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_periode_pelanggan ON master_pelanggan(periode);
CREATE INDEX IF NOT EXISTS idx_nomen_kunjungan ON kunjungan_petugas(nomen);
CREATE INDEX IF NOT EXISTS idx_periode_mb ON master_bayar(periode);
CREATE INDEX IF NOT EXISTS idx_periode_coll ON collection_harian(periode);
