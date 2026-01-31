-- =========================================================================
-- SUNTER DASHBOARD PRO - DATABASE SCHEMA (V5.4 STABILITY PATCH)
-- Updated: 2026-02-01
-- Fokus: Perbaikan Sinkronisasi Lunas (Fix Unit Lunas 0) & Integrity Protection
-- =========================================================================

-- 1. SISTEM AKSES & KEAMANAN
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,      
    password TEXT NOT NULL,             
    role TEXT NOT NULL,                 -- admin, petugas, guest
    petugas_id TEXT,                    
    no_hp TEXT,                         
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. DATA MASTER & MAPPING RUTE
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,                
    nama TEXT,                          
    alamat TEXT,                        
    kd_pos TEXT,
    pcez TEXT,                          -- Join Key ke rute_petugas
    rayon TEXT, pc TEXT, ez TEXT, blok TEXT,
    notagihan TEXT,                     
    nomet TEXT,                         
    tarif TEXT,
    tgl_catat TEXT,                     
    stan_awal REAL DEFAULT 0,
    stan_akir REAL DEFAULT 0,
    kubik REAL DEFAULT 0,               
    nominal REAL DEFAULT 0,             
    cust_type TEXT,
    tipe TEXT DEFAULT 'MC',             -- Pembeda data target (MC)
    periode TEXT,                       -- Format MM-YYYY
    no_hp TEXT,                         -- Tambahan untuk WA Blast Sync
    is_prioritas INTEGER DEFAULT 0,     
    status_lunas INTEGER DEFAULT 0,     -- 0=Belum, 1=Lunas
    tgl_lunas TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode)              
);

-- Rute Petugas
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,              
    petugas TEXT NOT NULL,              
    no_admin TEXT,                      -- Nomor WhatsApp Supervisor
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. TRANSAKSI REALISASI (MB-UNDUE & COLL-CURRENT)
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    bulan_rek TEXT,                     -- Format MMYYYY
    notagihan TEXT,
    tgl_bayar TEXT,
    nominal REAL DEFAULT 0,
    periode TEXT,                       -- MM-YYYY
    kategori TEXT DEFAULT 'UNDUE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, periode, bulan_rek)            
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
    UNIQUE(nomen, periode, notag)
);

-- Ardebt
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
    periode TEXT,                       
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    action TEXT,
    module TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,                     
    periode TEXT,
    row_count INTEGER DEFAULT 0,   
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. TRIGGER & AUTOMATION

-- A. Prioritas
CREATE TRIGGER IF NOT EXISTS trg_autopilot_priority
AFTER INSERT ON master_pelanggan
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET is_prioritas = 1 
    WHERE id = NEW.id AND NEW.nominal >= 300000;
END;

-- B. SINKRONISASI LUNAS OTOMATIS (FIX: FLEXIBLE MATCHING)
DROP TRIGGER IF EXISTS trg_sinergi_lunas_mb;
DROP TRIGGER IF EXISTS trg_sinergi_lunas_coll;

-- Fix: Trigger MB (Master Bayar)
CREATE TRIGGER trg_sinergi_lunas_mb
AFTER INSERT ON master_bayar
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, 
        tgl_lunas = NEW.tgl_bayar
    WHERE nomen = NEW.nomen 
    AND status_lunas = 0;
END;

-- Fix: Trigger Collection (Laporan Lapangan)
CREATE TRIGGER trg_sinergi_lunas_coll
AFTER INSERT ON collection_harian
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, 
        tgl_lunas = NEW.pay_dt
    WHERE nomen = NEW.nomen 
    AND status_lunas = 0;
END;

-- C. Reversal Status
CREATE TRIGGER IF NOT EXISTS trg_reversal_lunas_mb
AFTER DELETE ON master_bayar
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 0, tgl_lunas = NULL
    WHERE nomen = OLD.nomen;
END;

-- 6. INDEX OPTIMIZATION
CREATE INDEX IF NOT EXISTS idx_mc_nomen_per ON master_pelanggan(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_mc_pcez ON master_pelanggan(pcez);
CREATE INDEX IF NOT EXISTS idx_mb_sync ON master_bayar(nomen, periode, kategori);
CREATE INDEX IF NOT EXISTS idx_mb_brek ON master_bayar(bulan_rek);
CREATE INDEX IF NOT EXISTS idx_coll_sync ON collection_harian(nomen, periode, kategori);
CREATE INDEX IF NOT EXISTS idx_kj_nomen_per ON kunjungan_petugas(nomen, periode);
