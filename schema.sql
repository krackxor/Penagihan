-- =========================================================================
-- SUNTER DASHBOARD PRO - DATABASE SCHEMA (V4.1 SINERGI & UNDUE LOGIC)
-- Updated: 2026-01-12
-- Sinergi: N+1 Period Logic, Anti-NULL Payment Guard, & Undue/Current Sync
-- =========================================================================

-- =========================================================================
-- 1. SISTEM AKSES & KEAMANAN
-- =========================================================================

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

-- =========================================================================
-- 2. DATA MASTER & MAPPING RUTE
-- =========================================================================

-- Master Pelanggan: Basis data utama target periode N+1
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,                -- ID Pelanggan (String / TEXT)
    nama TEXT,                          -- NAMA_PEL
    alamat TEXT,                        -- Alamat Lengkap
    kd_pos TEXT,
    pcez TEXT,                          -- Join Key ke rute_petugas
    rayon TEXT, pc TEXT, ez TEXT, blok TEXT,
    notagihan TEXT,                     -- Join Key ke MB/Collection
    nomet TEXT,                         -- No Meter (Alfanumerik)
    tarif TEXT,
    tgl_catat TEXT,                     -- TGL_CATAT 26/11 -> Periode 12
    stan_awal REAL DEFAULT 0,
    stan_akir REAL DEFAULT 0,
    kubik REAL DEFAULT 0,
    nominal REAL DEFAULT 0,             -- Nilai Tagihan Current
    cust_type TEXT,
    tipe TEXT DEFAULT 'MC',
    periode TEXT,                       -- Format MM-YYYY (Contoh: 12-2025)
    is_prioritas INTEGER DEFAULT 0,     -- Flag Tagihan >= 300rb
    status_lunas INTEGER DEFAULT 0,     -- 0=Belum, 1=Lunas
    tgl_lunas TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode) 
);

CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,              -- Kode Area (Join Key)
    petugas TEXT NOT NULL,              -- Nama Petugas
    no_admin TEXT,                      -- WA SPV/Admin Area
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 3. TRANSAKSI REALISASI (MB-UNDUE & COLL-CURRENT)
-- =========================================================================

-- Master Bayar: Pembayaran Kantor/Bank (UNDUE)
-- Dibayar Tgl 25/11 untuk Tagihan periode 12
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    bulan_rek TEXT,                     -- BULAN_REK 112025 dibayar 30/11 -> UNDUE
    notagihan TEXT,                     -- Bisa NULL di Excel
    tgl_bayar TEXT,
    nominal REAL DEFAULT 0,
    periode TEXT,                       -- MM-YYYY (Match ke Periode Target MC)
    kategori TEXT DEFAULT 'UNDUE',      -- Label Pembayaran Kantor
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode)              -- Mencegah double lunas jika notagihan NULL
);

-- Collection Harian: Penagihan Lapangan (CURRENT)
-- Dibayar Tgl 15/12 untuk Tagihan periode 12
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notag TEXT,                         -- Bisa NULL di Excel
    bill_period TEXT,                   -- Nov/2025 dibayar 31/12 -> CURRENT
    bill_reason TEXT,
    nominal REAL DEFAULT 0,
    pay_dt TEXT,
    freeze_dttm TEXT,
    vol_collect REAL DEFAULT 0,
    periode TEXT,                       -- MM-YYYY (Match ke Periode Target MC)
    kategori TEXT DEFAULT 'CURRENT',    -- Label Penagihan Lapangan
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode)              -- Mencegah double lunas jika notag NULL
);

-- Ardebt: Data Tunggakan Lama (Berekor) - Dipisahkan dari Current
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    periode_bill TEXT,                  -- Menyimpan lama tunggakan (misal: 43 bulan)
    jumlah REAL DEFAULT 0,
    volume REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode_bill)
);

-- =========================================================================
-- 4. MONITORING KUNJUNGAN & AUDIT TRAIL
-- =========================================================================

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
    file_type TEXT,                     -- MC, MB, ARDEBT, COLL
    periode TEXT,
    row_count INTEGER DEFAULT 0,   
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 5. TRIGGER & AUTOMATION (AUTOPILOT SINERGI)
-- =========================================================================

-- Prioritas: Flag pelanggan nominal >= 300rb
CREATE TRIGGER IF NOT EXISTS trg_autopilot_priority
AFTER INSERT ON master_pelanggan
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET is_prioritas = 1 
    WHERE id = NEW.id AND NEW.nominal >= 300000;
END;

-- Sinkronisasi Lunas UNDUE: Update status di Master saat MB masuk
-- Menggunakan Nomen & Periode (Mengatasi Notagihan NULL)
CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_mb
AFTER INSERT ON master_bayar
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.tgl_bayar
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

-- Sinkronisasi Lunas CURRENT: Update status di Master saat Collection masuk
-- Menggunakan Nomen & Periode (Mengatasi Notag NULL)
CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas_coll
AFTER INSERT ON collection_harian
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.pay_dt
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

-- =========================================================================
-- 6. INDEX OPTIMIZATION (ULTRA-FAST SEARCH)
-- =========================================================================

-- Index Nomen & Periode (Kunci Sinergi Utama)
CREATE INDEX IF NOT EXISTS idx_mc_nomen_per ON master_pelanggan(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_mb_nomen_per ON master_bayar(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_coll_nomen_per ON collection_harian(nomen, periode);

-- Filter Indexes
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez, status_lunas, periode);
CREATE INDEX IF NOT EXISTS idx_mc_high_val ON master_pelanggan(periode, nominal) WHERE nominal >= 300000;
CREATE INDEX IF NOT EXISTS idx_ardebt_nomen ON ardebt(nomen);
CREATE INDEX IF NOT EXISTS idx_kunjungan_fast_hide ON kunjungan_petugas(nomen, periode);
