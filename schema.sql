-- Sunter Dashboard Pro - Database Schema (Smart Autopilot Edition)
-- Version: 3.6 (Final Stable - High Intelligence)
-- Updated: 2026-01-10 
-- Sinergi: Automasi Ardebt, High-Value Target Filtering, & Real-time Collection Sync

-- =========================================================================
-- 1. SISTEM AKSES & KEAMANAN (SMART AUTH)
-- =========================================================================

-- Tabel User: Standarisasi level akses untuk keamanan data personal nasabah.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,      -- ID Login petugas (Case Sensitive)
    password TEXT NOT NULL,              -- Hash password (BCrypt/PBKDF2)
    role TEXT NOT NULL,                  -- 'admin', 'petugas', 'guest'
    petugas_id TEXT,                     -- SINERGI: Harus SAMA dengan rute_petugas.petugas
    no_hp TEXT,                          -- WhatsApp petugas untuk notifikasi sistem
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 2. DATA MASTER & AUTOPILOT ENGINE
-- =========================================================================

-- Tabel Master Pelanggan (MC): Inti dari target penagihan bulanan.
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,           -- SMART CAST: Selalu simpan sebagai TEXT untuk cegah IDPEL ilmiah (3.5E+08)
    nomet TEXT,                    -- Nomor Meter pelanggan
    notagihan TEXT,                -- Kunci Pintu Ganda 1 (Link Utama ke MB & Collection)
    nama TEXT,                     -- Nama Pelanggan
    pcez TEXT,                     -- Kode Rute (Standard: XXX/XX)
    rayon TEXT,                    -- SMART AUTO: '34' atau '35' (Terisi otomatis saat upload)
    nominal REAL DEFAULT 0,        -- Rupiah Tagihan Bulan Berjalan
    volume REAL DEFAULT 0,         -- Kubikasi penggunaan air
    periode TEXT,                  -- SMART PERIOD: Format MM-YYYY (Contoh: '01-2026')
    is_prioritas INTEGER DEFAULT 0, -- AUTOPILOT: Set 1 otomatis jika nominal >= 300.000
    no_hp TEXT,                    -- SINERGI: Nomor HP Konsumen (untuk WA Blast)
    status_lunas INTEGER DEFAULT 0, -- SMART STATUS: 0=Belum, 1=Lunas
    tgl_lunas TEXT,                -- Sinkronisasi dari Master Bayar
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode) 
);

-- Tabel Mapping Rute (SINERGI WILAYAH): Menghubungkan rute dengan penanggung jawab.
CREATE TABLE IF NOT EXISTS rute_petugas (
    pcez TEXT PRIMARY KEY,         -- Kode Rute unik (Key Utama)
    petugas TEXT NOT NULL,         -- Nama Petugas (Link ke users.petugas_id)
    no_admin TEXT,                 -- SINERGI WA: Nomor WA Admin/Supervisor wilayah (Tembusan Laporan)
    target_rupiah REAL DEFAULT 0,  -- Akumulasi target per rute
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Master Bayar (MB): Data lunas resmi dari kantor/bank.
CREATE TABLE IF NOT EXISTS master_bayar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notagihan TEXT,
    nominal REAL DEFAULT 0,
    tgl_bayar TEXT,
    periode TEXT,                  -- Link sinkronisasi ke periode MC
    lks_bayar TEXT,                -- Lokasi Bayar (Bank/ATM/Loket)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notagihan, periode)
);

-- Tabel Collection Harian: Pencatatan real-time setoran (Solusi Fix OperationalError)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    notag TEXT,
    nominal REAL DEFAULT 0,
    pay_dt TEXT,                    -- Tanggal transaksi/setoran
    periode TEXT,                   -- Periode tagihan yang dibayar
    petugas_input TEXT,             -- Audit: Siapa yang menginput
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nomen, notag, periode)
);

-- Tabel Ardebt (Legacy/Manual): Penampung tunggakan berekor.
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    jumlah REAL DEFAULT 0,
    volume REAL DEFAULT 0,
    periode_bill TEXT,             -- Keterangan bulan-bulan yang menunggak
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 3. LOGGING AKTIVITAS & AUDIT TRAIL
-- =========================================================================

-- Tabel Kunjungan Petugas: Log aktivitas dan bukti fisik lapangan.
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,              -- Nama pelapor
    keterangan TEXT,                -- Status: (Janji Bayar, Sudah Bayar, Rumah Kosong, dll)
    no_hp_update TEXT,              -- Update No HP pelanggan terbaru
    catatan TEXT,                   -- Detail percakapan/kondisi meter
    janji_bayar_dt TEXT,            -- SMART REMINDER: Tanggal janji bayar
    mc_snapshot REAL,               -- SMART SNAPSHOT: Nominal tagihan SAAT dikunjungi
    ardebt_snapshot REAL,           -- SMART SNAPSHOT: Nominal tunggakan SAAT dikunjungi
    foto_path TEXT,                 -- Nama file foto (Watermarked)
    lat_long TEXT,                  -- GPS Coordinate
    periode TEXT,                   -- Periode pelaporan (MM-YYYY)
    status_audit TEXT DEFAULT 'OK',-- Untuk validasi Admin
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Upload History: Jejak audit pengunggahan file Excel (Solusi Fix 500 Error)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_type TEXT,                -- MC, MB, ARDEBT, RUTE
    periode TEXT,
    row_count INTEGER,
    status TEXT,                   -- SUCCESS / FAILED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. SMART TRIGGER (LOGIKA AUTOPILOT)
-- =========================================================================

-- TRIGGER 1: Autopilot Prioritas
-- Otomatis menandai nasabah sebagai 'Prioritas' jika tagihan >= 300rb saat insert.
CREATE TRIGGER IF NOT EXISTS trg_autopilot_priority
AFTER INSERT ON master_pelanggan
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET is_prioritas = 1 
    WHERE id = NEW.id AND NEW.nominal >= 300000;
END;

-- TRIGGER 2: Sinergi Lunas Otomatis
-- Ketika data MB (Bank) masuk, otomatis ubah status di tabel MC (Master Pelanggan).
CREATE TRIGGER IF NOT EXISTS trg_sinergi_lunas
AFTER INSERT ON master_bayar
FOR EACH ROW
BEGIN
    UPDATE master_pelanggan 
    SET status_lunas = 1, tgl_lunas = NEW.tgl_bayar
    WHERE nomen = NEW.nomen AND periode = NEW.periode;
END;

-- TRIGGER 3: Autopilot Lunas via Collection Harian
-- Ketika petugas input setoran di lapangan, otomatis tandai pelanggan sebagai lunas.
CREATE TRIGGER IF NOT EXISTS trg_autopilot_coll_lunas
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

-- Indexing krusial agar pencarian ribuan data tetap secepat kilat.
CREATE INDEX IF NOT EXISTS idx_mc_nomen_notag ON master_pelanggan(nomen, notagihan);
CREATE INDEX IF NOT EXISTS idx_mc_filter_smart ON master_pelanggan(periode, nominal, pcez);
CREATE INDEX IF NOT EXISTS idx_mc_status ON master_pelanggan(status_lunas, is_prioritas);
CREATE INDEX IF NOT EXISTS idx_rute_mapping ON rute_petugas(petugas, pcez);
CREATE INDEX IF NOT EXISTS idx_kunjungan_nomen ON kunjungan_petugas(nomen, periode);
CREATE INDEX IF NOT EXISTS idx_coll_periode ON collection_harian(periode, petugas_input);
