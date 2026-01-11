-- =========================================================================
-- SUNTER DASHBOARD PRO - DATABASE SCHEMA (V3.9.1 HIGH-PERFORMANCE EDITION)
-- Updated: 2026-01-11 
-- Sinergi: Snapshot Persistence, Geo-Tracking, & Ultra-Fast Indexing
-- =========================================================================

-- =========================================================================
-- 1. SISTEM AKSES & KEAMANAN (SMART AUTH)
-- =========================================================================

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

CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,         -- Kode Rute
    petugas TEXT NOT NULL,         -- Penanggung jawab lapangan
    no_admin TEXT,                 -- No WA Admin Wilayah untuk laporan otomatis
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    nama_snapshot TEXT,            -- Nama saat dikunjungi
    alamat_snapshot TEXT,          -- Alamat saat dikunjungi
    nomet TEXT,                    -- No Meter saat dikunjungi
    mc REAL DEFAULT 0,             -- Saldo Tagihan berjalan
    ardebt REAL DEFAULT 0,         -- Saldo Tunggakan berekor
    volume REAL DEFAULT 0,         -- Angka meter/kubikasi
    keterangan TEXT,               -- Hasil koordinasi (Janji Bayar, dll)
    catatan TEXT,                  -- Tambahan info petugas
    foto_path TEXT,                -- Link file foto
    latitude TEXT,                 -- Koordinat Lintang
    longitude TEXT,                -- Koordinat Bujur
    no_hp TEXT,                    -- Kontak konsumen
    periode TEXT,                  -- Bulan pelaporan
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,                -- MC, MB, ARDEBT, COLLECTION, RUTE
    periode TEXT,
    row_count INTEGER DEFAULT 0,   
    status TEXT,                   -- SUCCESS / FAILED / ERROR
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. SMART TRIGGER (LOGIKA AUTOPILOT)
-- =========================================================================

CREATE TRIGGER IF NOT EXISTS trg_autopilot_priority
AFTER INSERT ON master_pelanggan
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET is_prioritas = 1 
    WHERE id = NEW.id AND NEW.nominal >= 300000;
END;

CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_mb
AFTER INSERT ON master_bayar
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.tgl_bayar
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_coll
AFTER INSERT ON collection_harian
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.pay_dt
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

-- =========================================================================
-- 5. OPTIMASI INDEX (HIGH-PERFORMANCE LOOKUP) - DIPERBARUI
-- =========================================================================

-- Indeks Utama untuk Query Monitoring Dashboard (Mempercepat Join Lintas Tabel)
CREATE INDEX IF NOT EXISTS idx_mc_lookup ON master_pelanggan(periode, nomen, notagihan);
CREATE INDEX IF NOT EXISTS idx_mb_lookup ON master_bayar(periode, nomen, notagihan);
CREATE INDEX IF NOT EXISTS idx_coll_lookup ON collection_harian(periode, nomen, notag);

-- Indeks untuk Filter Wilayah dan Status (Mempercepat Pusat Kendali)
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez, status_lunas);
CREATE INDEX IF NOT EXISTS idx_mc_prioritas ON master_pelanggan(is_prioritas, kubik);

-- Indeks untuk Audit Sejarah
CREATE INDEX IF NOT EXISTS idx_kunjungan_audit ON kunjungan_petugas(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_upload_history_sort ON upload_history(created_at DESC);
