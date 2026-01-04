-- 1. Tabel Master Pelanggan (Data dari file MC)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT UNIQUE,          -- Nomen Pelanggan (Kunci Utama)
    nama TEXT,                  -- Nama Pelanggan
    pcez TEXT,                  -- Kode Rute (Contoh: 096/02)
    rayon TEXT,                 -- Kode Rayon (Dari Kolom PC)
    block TEXT,                 -- Kode Blok
    nominal REAL,               -- Nominal Tagihan
    tipe TEXT DEFAULT 'MC',     -- Tipe data (MC, MB, dll)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Mapping Rute & Petugas (Mapping Manual / Upload Rute)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,      -- Kode PCEZ (Unik)
    petugas TEXT,               -- Nama Petugas Lapangan
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Master Bayar (Pelanggan yang sudah lunas dari file MB)
CREATE TABLE IF NOT EXISTS master_bayar (
    nomen TEXT PRIMARY KEY,
    nominal REAL,
    tgl_bayar TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Collection Harian (Data pembayaran harian)
CREATE TABLE IF NOT EXISTS collection_harian (
    nomen TEXT PRIMARY KEY,
    notag TEXT,
    nominal REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabel Ardebt (Data tunggakan pelanggan)
CREATE TABLE IF NOT EXISTS ardebt (
    nomen TEXT PRIMARY KEY,
    jumlah REAL,
    volume REAL,
    periode_bill TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabel Kunjungan Petugas (LOG KERJA & LAPORAN REAL-TIME)
-- Tabel ini menyimpan semua input dari form Belum Bayar
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT,                 -- Nomen Pelanggan
    petugas_name TEXT,          -- Nama Petugas yang melaporkan
    keterangan TEXT,            -- Status (Janji Bayar, RKS, Segera Bayar, dll)
    no_hp TEXT,                 -- Nomor HP Pelanggan yang diinput petugas
    catatan TEXT,               -- Catatan tambahan lapangan
    janji_bayar_dt TEXT,        -- Tanggal janji bayar (jika ada)
    foto_path TEXT,             -- Nama file foto hasil watermark
    latitude TEXT,              -- Koordinat GPS (jika diaktifkan)
    longitude TEXT,             -- Koordinat GPS (jika diaktifkan)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- INDEXING: Agar pencarian data super cepat (FAST PERFORMANCE)
CREATE INDEX IF NOT EXISTS idx_nomen_pelanggan ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_pcez_pelanggan ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_nomen_kunjungan ON kunjungan_petugas(nomen);
