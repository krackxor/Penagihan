-- =========================================================================
-- SUNTER DASHBOARD PRO - DATABASE SCHEMA (V3.8 SINERGI STRICT EDITION)
-- Updated: 2026-01-10 
-- Sinergi: Automasi Ardebt, High-Value Target Filtering, & Real-time Collection Sync
-- =========================================================================

-- =========================================================================
-- 1. SISTEM AKSES & KEAMANAN (SMART AUTH)
-- =========================================================================

-- Tabel User: Standarisasi level akses. 
-- Link petugas_id harus sinkron dengan tabel rute_petugas.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,      -- Username login petugas
    password TEXT NOT NULL,              -- Password terenkripsi
    role TEXT NOT NULL,                  -- 'admin', 'petugas', 'guest'
    petugas_id TEXT,                     -- ID Petugas untuk filter data lapangan
    no_hp TEXT,                          -- WhatsApp petugas untuk notifikasi
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 2. DATA MASTER & AUTOPILOT ENGINE
-- =========================================================================

-- Tabel Master Pelanggan (MC): Inti dari target penagihan bulanan.
-- Dilengkapi dengan pemecahan komponen ZONA_NOVAK (PC, EZ, BLOK).
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,           -- ID Pelanggan (Disimpan sebagai TEXT untuk proteksi format)
    nama TEXT,                     -- Diambil dari kolom NAMA_PEL
    alamat TEXT,                   -- Gabungan Sinergi dari ALM1_PEL, ALM2_PEL, ALM3_PEL
    kd_pos TEXT,                   -- Kode Pos Pelanggan
    pcez TEXT,                     -- Kode Rute Standar (Hasil Slicing ZONA_NOVAK: PC/EZ)
    rayon TEXT,                    -- Hasil Slicing ZONA_NOVAK (Digit 1-2)
    pc TEXT,                       -- Hasil Slicing ZONA_NOVAK (Digit 3-5)
    ez TEXT,                       -- Hasil Slicing ZONA_NOVAK (Digit 6-7)
    blok TEXT,                     -- Hasil Slicing ZONA_NOVAK (Digit 8-9)
    notagihan TEXT,                -- Nomor Tagihan (Kunci Pintu Ganda 1)
    nomet TEXT,                    -- Nomor Meter pelanggan
    tarif TEXT,                    -- Golongan Tarif (Wajib MC)
    tgl_catat TEXT,                -- Tanggal pembacaan meter
    stan_awal REAL DEFAULT 0,      -- Angka meter awal
    stan_akir REAL DEFAULT 0,      -- Angka meter akhir
    kubik REAL DEFAULT 0,          -- Selisih stan (KUBIK)
    nominal REAL DEFAULT 0,        -- Total Rupiah (NOMINAL)
    cust_type TEXT,                -- Tipe Pelanggan
    tipe TEXT DEFAULT 'MC',        -- Kategori data (MC)
    periode TEXT,                  -- Format MM-YYYY
    is_prioritas INTEGER DEFAULT 0, -- Auto-set 1 jika nominal >= 300.000
    status_lunas INTEGER DEFAULT 0, -- 0=Belum, 1=Lunas
    tgl_lunas TEXT,                -- Tanggal pelunasan (Sync MB/Collection)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode) 
);

-- Tabel Mapping Rute (SINERGI WILAYAH): Menghubungkan rute dengan penanggung jawab.
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,         -- Kode Rute (Contoh: 096/02)
    petugas TEXT NOT NULL,         -- Nama Petugas Lapangan
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Master Bayar (MB): Data lunas resmi hasil sinkronisasi kantor.
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,           -- ID Pelanggan
    bulan_rek TEXT,                -- Bulan Rekening (Wajib MB)
    notagihan TEXT,                -- No Tagihan (Wajib MB)
    tgl_bayar TEXT,                -- Tanggal Bayar di Bank/Loket
    nominal REAL DEFAULT 0,        -- Nominal yang dibayar
    periode TEXT,                  -- Periode sistem saat sinkronisasi
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode)
);

-- Tabel Collection Harian: Pencatatan setoran harian (Lengkap sesuai permintaan).
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,           -- ID Pelanggan
    notag TEXT,                    -- No Tagihan (Wajib Collection)
    bill_period TEXT,              -- Periode Tagihan (Wajib Collection)
    bill_reason TEXT,              -- Alasan Penagihan (Wajib Collection)
    nominal REAL DEFAULT 0,        -- Nominal yang disetor
    pay_dt TEXT,                   -- Tanggal bayar petugas
    freeze_dttm TEXT,              -- Waktu pembekuan data (Wajib Collection)
    vol_collect REAL DEFAULT 0,    -- Volume yang tertagih (Wajib Collection)
    periode TEXT,                  -- Periode laporan harian
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notag, periode)
);

-- Tabel Ardebt: Penampung data tunggakan piutang lama (Berekor).
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,           -- ID Pelanggan
    periode_bill TEXT,             -- Keterangan bulan menunggak (Wajib Ardebt)
    jumlah REAL DEFAULT 0,         -- Total Rupiah Tunggakan
    volume REAL DEFAULT 0,         -- Total Kubik Tunggakan
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 3. LOGGING AKTIVITAS & AUDIT TRAIL
-- =========================================================================

-- Tabel Kunjungan Petugas: Dokumentasi visual dan status lapangan.
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,             -- Pelapor
    keterangan TEXT,               -- Status (Rumah Kosong, Janji Bayar, dll)
    foto_path TEXT,                -- Link file foto
    lat_long TEXT,                 -- Koordinat GPS
    periode TEXT,                  -- Bulan pelaporan
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Upload History: Audit trail pengunggahan Excel Admin.
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,                -- MC, MB, ARDEBT, COLLECTION, RUTE
    row_count INTEGER,
    status TEXT,                   -- SUCCESS / FAILED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. SMART TRIGGER (LOGIKA AUTOPILOT)
-- =========================================================================

-- TRIGGER 1: Autopilot Prioritas. Menandai High-Value Target secara otomatis.
CREATE TRIGGER IF NOT EXISTS trg_autopilot_priority
AFTER INSERT ON master_pelanggan
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET is_prioritas = 1 
    WHERE id = NEW.id AND NEW.nominal >= 300000;
END;

-- TRIGGER 2: Sinergi Pintu Ganda (MB). Update lunas otomatis via data kantor.
CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_mb
AFTER INSERT ON master_bayar
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.tgl_bayar
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

-- TRIGGER 3: Sinergi Pintu Ganda (Collection). Update lunas otomatis via setoran petugas.
CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_coll
AFTER INSERT ON collection_harian
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.pay_dt
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

-- =========================================================================
-- 5. OPTIMASI INDEX (SMART PERFORMANCE)
-- =========================================================================

-- Indeks krusial untuk mempercepat pencarian data di antara puluhan ribu baris.
CREATE INDEX IF NOT EXISTS idx_mc_main ON master_pelanggan(nomen, pcez, periode);
CREATE INDEX IF NOT EXISTS idx_mc_status ON master_pelanggan(status_lunas, is_prioritas);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_coll_nomen ON collection_harian(nomen, periode);
