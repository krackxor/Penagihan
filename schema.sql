-- Sunter Dashboard Pro - Database Schema
-- Updated: 2026-01-09 (Full Synergy: Field Activity, Admin Control Center & 3-Level Login)

-- 

-- ==========================================
-- 1. SISTEM AKSES & LOGIN (PENGATURAN ADMIN)
-- ==========================================

-- Tabel User untuk Manajemen Akses 3 Level
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,      -- ID Login (contoh: 'pian_sunter')
    password TEXT NOT NULL,             -- Hashed Password
    role TEXT NOT NULL,                 -- 'admin', 'petugas', 'publik'
    petugas_id TEXT,                    -- SINERGI: Kunci Nama yang harus SAMA dengan rute_petugas.petugas
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. DATA MASTER & OPERASIONAL (EXISTING)
-- ==========================================

-- Tabel Master Pelanggan (Data Utama dari file MC)
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

-- Tabel Mapping Rute & Petugas (SINERGI: Kunci utama untuk Filter Petugas)
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,        -- Kode PCEZ unik
    petugas TEXT NOT NULL,        -- Nama Petugas Lapangan (Sesuai kolom petugas_id di tabel users)
    no_admin TEXT,                -- NOMOR WA ADMIN/SUPERVISOR (Target Laporan Internal)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Master Bayar (Pelanggan Lunas dari file MB)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notagihan TEXT,
    nominal REAL DEFAULT 0,
    tgl_bayar TEXT,
    periode TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode)
);

-- Tabel Collection Harian (Real-time Status)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notag TEXT,
    nominal REAL DEFAULT 0,
    pay_dt TEXT,
    periode TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notag, periode)
);

-- Tabel Ardebt (Data Tunggakan Berekor)
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    jumlah REAL DEFAULT 0,
    volume REAL DEFAULT 0,
    periode_bill TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Kunjungan Petugas (Log Lapangan & Janji Bayar)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,            -- Nama petugas yang melakukan kunjungan
    keterangan TEXT,
    no_hp TEXT,
    catatan TEXT,
    janji_bayar_dt TEXT,
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    periode TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Riwayat Unggahan (Log Admin Control Center)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,               -- MC, MB, Collection, Ardebt, Rute
    periode TEXT,
    row_count INTEGER,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 3. INDEXING (OPTIMASI PERFORMA)
-- ==========================================

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_petugas_id ON users(petugas_id);
CREATE INDEX IF NOT EXISTS idx_nomen_pelanggan ON master_pelanggan(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_mb ON master_bayar(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_coll ON collection_harian(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_ardebt ON ardebt(nomen);
CREATE INDEX IF NOT EXISTS idx_nomen_kunjungan ON kunjungan_petugas(nomen);
CREATE INDEX IF NOT EXISTS idx_rayon_pelanggan ON master_pelanggan(rayon);
CREATE INDEX IF NOT EXISTS idx_periode_pelanggan ON master_pelanggan(periode);
CREATE INDEX IF NOT EXISTS idx_paydt_coll ON collection_harian(pay_dt);
CREATE INDEX IF NOT EXISTS idx_notag_pelanggan ON master_pelanggan(notagihan);
CREATE INDEX IF NOT EXISTS idx_notag_mb ON master_bayar(notagihan);
CREATE INDEX IF NOT EXISTS idx_notag_coll ON collection_harian(notag);
CREATE INDEX IF NOT EXISTS idx_janji_bayar_dt ON kunjungan_petugas(janji_bayar_dt);
CREATE INDEX IF NOT EXISTS idx_pcez_pelanggan ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_periode ON kunjungan_petugas(periode);
CREATE INDEX IF NOT EXISTS idx_kunjungan_tanggal ON kunjungan_petugas(created_at);
