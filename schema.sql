-- Sunter Dashboard Pro - Database Schema (Smart Autopilot Edition)
-- Updated: 2026-01-10 
-- Sinergi: Lapangan (Mobile), Admin Control Center (Web) & Logic 3-Level Access

-- ==========================================
-- 1. SISTEM AKSES & LOGIN (PENGATURAN ADMIN)
-- ==========================================

-- Tabel User: Standarisasi level akses untuk keamanan data.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,      -- ID Login petugas (Case Sensitive)
    password TEXT NOT NULL,             -- Hash password keamanan
    role TEXT NOT NULL,                 -- 'admin', 'petugas', 'guest'
    petugas_id TEXT,                    -- SMART LINK: Harus sesuai dengan rute_petugas.petugas
    no_hp TEXT,                         -- Nomor WA petugas (Untuk notifikasi internal)
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. DATA MASTER & OPERASIONAL (AUTOPILOT READY)
-- ==========================================

-- Tabel Master Pelanggan (MC): Inti dari target penagihan.
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,           -- Smart Cast: Disimpan sebagai TEXT untuk jaga Leading Zero
    nomet TEXT,                    -- Nomor Meter pelanggan
    notagihan TEXT,                -- Kunci Pintu Ganda 1 (Untuk Link ke MB/Collection)
    nama TEXT,                     -- Nama Pelanggan (Maks 100 Karakter)
    pcez TEXT,                     -- Kode Rute (Standard: XXX/XX)
    rayon TEXT,                    -- SMART FILTER: '34' atau '35' (Dideteksi otomatis saat upload)
    nominal REAL DEFAULT 0,        -- Rupiah Tagihan MC
    volume REAL DEFAULT 0,         -- Kubikasi penggunaan air
    periode TEXT,                  -- SMART PERIOD: Format MM-YYYY (Contoh: '01-2026')
    is_prioritas INTEGER DEFAULT 0, -- AUTOPILOT: 1 jika nominal >= 300.000
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode) 
);

-- Tabel Mapping Rute (SINERGI WILAYAH): Menentukan rute milik siapa.
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,         -- Kode Rute unik (e.g., 096/02)
    petugas TEXT NOT NULL,         -- Nama Petugas penanggung jawab
    no_admin TEXT,                 -- SINERGI WA: Nomor WA Supervisor/Admin wilayah tersebut
    target_rupiah REAL DEFAULT 0,  -- Target akumulasi per rute
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Master Bayar (MB): Data lunas resmi dari kantor.
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notagihan TEXT,
    nominal REAL DEFAULT 0,
    tgl_bayar TEXT,
    periode TEXT,                  -- Digunakan untuk cross-check dengan MC
    lks_bayar TEXT,                -- Lokasi bayar (Bank/Loket)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode)
);

-- Tabel Collection Harian: Data pembayaran real-time dari input harian.
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notag TEXT,
    nominal REAL DEFAULT 0,
    pay_dt TEXT,                   -- Tanggal bayar fisik
    periode TEXT,
    petugas_input TEXT,            -- Melacak siapa yang menginput collection
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notag, periode)
);

-- Tabel Ardebt (History Piutang): Penampung tunggakan berekor.
-- SMART LOGIC: Jika Anda ingin Autopilot, tabel ini akan diisi oleh sistem 
-- melalui query 'Belum Bayar' dari periode sebelumnya.
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    jumlah REAL DEFAULT 0,
    volume REAL DEFAULT 0,
    periode_bill TEXT,             -- Keterangan bulan menunggak
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 3. AKTIVITAS LAPANGAN & LOGGING
-- ==========================================

-- Tabel Kunjungan Petugas: Log aktivitas penagihan fisik.
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,             -- Siapa yang mendatangi
    keterangan TEXT,               -- (Janji Bayar, Sudah Bayar, Rumah Kosong, dll)
    no_hp_update TEXT,             -- Update nomor HP pelanggan jika berubah
    catatan TEXT,                  -- Catatan detail lapangan
    janji_bayar_dt TEXT,           -- Reminder otomatis untuk Dashboard Janji Bayar
    mc_snapshot REAL,              -- Mengunci nominal MC saat dikunjungi
    ardebt_snapshot REAL,          -- Mengunci nominal Ardebt saat dikunjungi
    foto_path TEXT,                -- Nama file foto bukti (Watermarked)
    lat_long TEXT,                 -- GPS Coordinate (Sinergi Maps)
    periode TEXT,                  -- Periode laporan MM-YYYY
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Riwayat Unggahan: Memantau aktivitas Admin Control Center.
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,                -- MC, MB, ARDEBT, RUTE
    periode TEXT,
    row_count INTEGER,
    status TEXT,                   -- SUCCESS / FAILED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 4. INDEXING (SMART PERFORMANCE)
-- ==========================================
-- Index dibuat untuk mempercepat pencarian Nomen (IDPEL) yang sering berulang.

CREATE INDEX IF NOT EXISTS idx_mc_nomen_notag ON master_pelanggan(nomen, notagihan);
CREATE INDEX IF NOT EXISTS idx_mc_periode ON master_pelanggan(periode);
CREATE INDEX IF NOT EXISTS idx_mc_nominal ON master_pelanggan(nominal); -- Untuk filter >= 300rb
CREATE INDEX IF NOT EXISTS idx_rute_petugas ON rute_petugas(petugas);
CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas(nomen);
CREATE INDEX IF NOT EXISTS idx_kunjungan_janji ON kunjungan_petugas(janji_bayar_dt);
CREATE INDEX IF NOT EXISTS idx_mb_notag ON master_bayar(notagihan);
CREATE INDEX IF NOT EXISTS idx_coll_notag ON collection_harian(notag);
