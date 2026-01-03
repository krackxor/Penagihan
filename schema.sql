-- Tabel Master Pelanggan (Data Induk MC)
CREATE TABLE IF NOT EXISTS master_pelanggan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    nama TEXT,
    pcez TEXT,
    no_hp TEXT,
    nominal REAL DEFAULT 0,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Ardebt (Data Tunggakan)
CREATE TABLE IF NOT EXISTS ardebt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    jumlah REAL DEFAULT 0,
    periode_bill TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Collection Harian (Data Pelanggan yang Sudah Bayar)
CREATE TABLE IF NOT EXISTS collection_harian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    periode_bulan INTEGER,
    periode_tahun INTEGER,
    pay_dt DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Kunjungan Petugas (Laporan Lapangan)
CREATE TABLE IF NOT EXISTS kunjungan_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomen TEXT NOT NULL,
    petugas_name TEXT,
    keterangan TEXT,
    tgl_janji_bayar DATE,
    foto_path TEXT,
    latitude TEXT,
    longitude TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabel Rute Petugas (Mapping Petugas ke Wilayah/PCEZ)
CREATE TABLE IF NOT EXISTS rute_petugas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    petugas TEXT NOT NULL,
    pcez TEXT NOT NULL
);

-- Tabel Riwayat Upload (Log Aktivitas)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_type TEXT,
    periode TEXT,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
