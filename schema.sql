-- =========================================================================
-- SUNTER DASHBOARD PRO - DATABASE SCHEMA (V4.2 SMART SYNC)
-- Updated: 2026-01-12
-- Perbaikan: Sinkronisasi RUTE, Dukungan CSV, & Optimasi Join PCEZ
-- =========================================================================

-- 1. SISTEM AKSES & KEAMANAN
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,      -- Login petugas
    password TEXT NOT NULL,             -- Hash password
    role TEXT NOT NULL,                 -- admin, petugas, guest
    petugas_id TEXT,                    -- Nama Petugas untuk Filter
    no_hp TEXT,                         -- Kontak WhatsApp
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. DATA MASTER & MAPPING RUTE
-- Master Pelanggan: Basis data utama target periode N+1
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,                -- ID Pelanggan
    nama TEXT,                          -- NAMA_PEL
    alamat TEXT,                        -- Alamat Lengkap
    kd_pos TEXT,
    pcez TEXT,                          -- Join Key ke rute_petugas (Format: XXX/XX)
    rayon TEXT, pc TEXT, ez TEXT, blok TEXT,
    notagihan TEXT,                     -- Join Key ke MB/Collection
    nomet TEXT,                         -- No Meter
    tarif TEXT,
    tgl_catat TEXT,                     
    stan_awal REAL DEFAULT 0,
    stan_akir REAL DEFAULT 0,
    kubik REAL DEFAULT 0,               -- Alias: Volume di API
    nominal REAL DEFAULT 0,             -- Nilai Tagihan Current
    cust_type TEXT,
    tipe TEXT DEFAULT 'MC',
    periode TEXT,                       -- Format MM-YYYY
    is_prioritas INTEGER DEFAULT 0,     -- Flag Tagihan >= 300rb
    status_lunas INTEGER DEFAULT 0,     -- 0=Belum, 1=Lunas
    tgl_lunas TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode)              -- Proteksi duplikasi per periode
);

-- Rute Petugas: Pemetaan administratif PCEZ ke Nama Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,              -- Kode Area (Join Key)
    petugas TEXT NOT NULL,              -- Nama Petugas dari file 'Rute RL JS'
    no_admin TEXT,                      -- WA SPV/Admin Area
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. TRANSAKSI REALISASI (MB-UNDUE & COLL-CURRENT)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    bulan_rek TEXT,
    notagihan TEXT,
    tgl_bayar TEXT,
    nominal REAL DEFAULT 0,
    periode TEXT,                       -- MM-YYYY
    kategori TEXT DEFAULT 'UNDUE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode)              -- Mencegah double lunas
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
    periode TEXT,                       -- MM-YYYY
    kategori TEXT DEFAULT 'CURRENT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode)
);

-- Ardebt: Data Tunggakan Lama (Berekor)
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    periode_bill TEXT,
    jumlah REAL DEFAULT 0,
    volume REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode_bill)
);

-- 4. MONITORING KUNJUNGAN & AUDIT TRAIL
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    nama_snapshot TEXT,
    alamat_snapshot TEXT,
    nomet TEXT,
    mc REAL DEFAULT 0,
    ardebt REAL DEFAULT 0,
    volume REAL DEFAULT 0,
    keterangan TEXT,
    catatan TEXT,
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    no_hp TEXT,
    periode TEXT,                       -- MM-YYYY
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,                     -- MC, MB, ARDEBT, COLL, RUTE
    periode TEXT,
    row_count INTEGER DEFAULT 0,   
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. TRIGGER & AUTOMATION (AUTOPILOT SINERGI)
-- Prioritas: Flag pelanggan nominal >= 300rb
CREATE TRIGGER IF NOT EXISTS trg_autopilot_priority
AFTER INSERT ON master_pelanggan
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET is_prioritas = 1 
    WHERE id = NEW.id AND NEW.nominal >= 300000;
END;

-- Sinkronisasi Lunas Otomatis (MB & COLL)
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

-- 6. INDEX OPTIMIZATION (ULTRA-FAST JOIN)
CREATE INDEX IF NOT EXISTS idx_mc_nomen_per ON master_pelanggan(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_mc_pcez_sync ON master_pelanggan(pcez, periode); -- Mempercepat Join Rute
CREATE INDEX IF NOT EXISTS idx_mb_nomen_per ON master_bayar(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_coll_nomen_per ON collection_harian(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_ardebt_nomen ON ardebt(nomen);
