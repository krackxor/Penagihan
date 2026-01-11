-- =========================================================================
-- SUNTER DASHBOARD PRO - DATABASE SCHEMA (V3.9 SINERGI STRICT EDITION)
-- Updated: 2026-01-11 
-- Sinergi: Snapshot Persistence, Geo-Tracking, & Automated Admin Messaging
-- =========================================================================

-- =========================================================================
-- 1. SISTEM AKSES & KEAMANAN (SMART AUTH)
-- =========================================================================

-- Tabel User: Standarisasi level akses.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,      -- Username login petugas
    password TEXT NOT NULL,             -- Password terenkripsi
    role TEXT NOT NULL,                 -- 'admin', 'petugas', 'guest'
    petugas_id TEXT,                    -- ID Petugas (Nama aslinya) untuk filter data
    no_hp TEXT,                         -- WhatsApp petugas untuk notifikasi
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 2. DATA MASTER & AUTOPILOT ENGINE
-- =========================================================================

-- Tabel Master Pelanggan (MC): Inti data bulanan.
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,           -- ID Pelanggan (String untuk menjaga format nol di depan)
    nama TEXT,                     -- Diambil dari kolom NAMA_PEL
    alamat TEXT,                   -- Gabungan Sinergi alamat lengkap
    kd_pos TEXT,
    pcez TEXT,                     -- Kode Rute (Hasil Slicing ZONA_NOVAK)
    rayon TEXT, pc TEXT, ez TEXT, blok TEXT,
    notagihan TEXT,                -- Kunci Pintu Ganda 1
    nomet TEXT,                    -- Nomor Meter
    tarif TEXT,
    tgl_catat TEXT,
    stan_awal REAL DEFAULT 0,
    stan_akir REAL DEFAULT 0,
    kubik REAL DEFAULT 0,          -- Penggunaan air
    nominal REAL DEFAULT 0,        -- Rupiah tagihan
    cust_type TEXT,
    tipe TEXT DEFAULT 'MC',
    periode TEXT,                  -- Format MM-YYYY
    is_prioritas INTEGER DEFAULT 0, -- Target High-Value
    status_lunas INTEGER DEFAULT 0, -- 0=Belum, 1=Lunas
    tgl_lunas TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode) 
);

-- Tabel Mapping Rute (SINERGI WILAYAH)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,         -- Kode Rute
    petugas TEXT NOT NULL,         -- Penanggung jawab lapangan
    no_admin TEXT,                 -- [UPDATE V3.9]: No WA Admin Wilayah untuk laporan otomatis
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Master Bayar (MB): Data lunas resmi kantor.
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    bulan_rek TEXT,
    notagihan TEXT,
    tgl_bayar TEXT,
    nominal REAL DEFAULT 0,
    periode TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode)
);

-- Tabel Collection Harian: Pencatatan setoran petugas.
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notag TEXT,
    bill_period TEXT,
    bill_reason TEXT,
    nominal REAL DEFAULT 0,
    pay_dt TEXT,
    freeze_dttm TEXT,
    vol_collect REAL DEFAULT 0,
    periode TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notag, periode)
);

-- Tabel Ardebt: Tunggakan lama (Berekor).
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    periode_bill TEXT,
    jumlah REAL DEFAULT 0,
    volume REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 3. LOGGING AKTIVITAS & ULTIMATE SNAPSHOT
-- =========================================================================

-- Tabel Kunjungan Petugas: Dokumentasi visual permanen.
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    nama_snapshot TEXT,            -- [UPDATE V3.9]: Nama saat dikunjungi
    alamat_snapshot TEXT,          -- [UPDATE V3.9]: Alamat saat dikunjungi
    nomet TEXT,                    -- No Meter saat dikunjungi
    mc REAL DEFAULT 0,             -- Saldo Tagihan berjalan
    ardebt REAL DEFAULT 0,         -- Saldo Tunggakan berekor
    volume REAL DEFAULT 0,         -- Angka meter/kubikasi
    keterangan TEXT,               -- Hasil koordinasi (Janji Bayar, dll)
    catatan TEXT,                  -- Tambahan info petugas
    foto_path TEXT,                -- Link file foto
    latitude TEXT,                 -- [UPDATE V3.9]: Koordinat Lintang
    longitude TEXT,                -- [UPDATE V3.9]: Koordinat Bujur
    no_hp TEXT,                    -- Kontak konsumen
    periode TEXT,                  -- Bulan pelaporan
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Upload History: Audit trail Admin.
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,                -- MC, MB, ARDEBT, COLLECTION, RUTE
    periode TEXT,
    row_count INTEGER DEFAULT 0,   --
    status TEXT,                   -- SUCCESS / FAILED / ERROR
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. SMART TRIGGER (LOGIKA AUTOPILOT)
-- =========================================================================

-- TRIGGER 1: Autopilot Prioritas Tagihan Tinggi.
CREATE TRIGGER IF NOT EXISTS trg_autopilot_priority
AFTER INSERT ON master_pelanggan
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET is_prioritas = 1 
    WHERE id = NEW.id AND NEW.nominal >= 300000;
END;

-- TRIGGER 2: Sinergi Pelunasan otomatis via MB.
CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_mb
AFTER INSERT ON master_bayar
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.tgl_bayar
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

-- TRIGGER 3: Sinergi Pelunasan otomatis via Collection Petugas.
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

CREATE INDEX IF NOT EXISTS idx_mc_main ON master_pelanggan(nomen, pcez, periode);
CREATE INDEX IF NOT EXISTS idx_mc_status ON master_pelanggan(status_lunas, is_prioritas);
CREATE INDEX IF NOT EXISTS idx_mb_nomen ON master_bayar(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_coll_nomen ON collection_harian(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas(nomen, periode);
