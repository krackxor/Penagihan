from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

# Inisialisasi database
db = SQLAlchemy()

# ==========================================================
# 0. DATABASE PETUGAS
# ==========================================================
class MasterPetugas(db.Model):
    """Tabel Petugas: Satu PCEZ bisa punya banyak peran (Tagihan/SBRS)."""
    __tablename__ = 'master_petugas'
    id = db.Column(db.Integer, primary_key=True)
    pcez = db.Column(db.String(20), index=True)
    nama_petugas = db.Column(db.String(100), nullable=False)
    peran = db.Column(db.String(20), index=True) # TAGIHAN, PENCATATAN, SBRS

# ==========================================================
# 1. DATABASE MASTER PELANGGAN (CID)
# ==========================================================
class MasterPelanggan(db.Model):
    """Tabel Induk Pelanggan: Data permanen dari CID (Jalur Cepat 28 Kolom + JSONB)."""
    __tablename__ = 'master_pelanggan'
    
    nomen = db.Column(db.String(50), primary_key=True) 
    
    norek = db.Column(db.String(50))
    nama = db.Column(db.String(150))
    status = db.Column(db.String(50))
    tipeplggn = db.Column(db.String(50))
    custclass = db.Column(db.String(100))
    tarif = db.Column(db.String(20))
    
    alamat = db.Column(db.Text)
    kodepos = db.Column(db.String(10))
    kelurahan = db.Column(db.String(100), index=True)
    kecamatan = db.Column(db.String(100))
    kota = db.Column(db.String(100))
    
    ab = db.Column(db.String(50), default='AB Sunter', index=True)
    regional = db.Column(db.String(50))
    cc = db.Column(db.String(20))
    kode_pa_pc = db.Column(db.String(20))
    zona_novak = db.Column(db.String(50))
    pcez = db.Column(db.String(20), index=True)
    rayon = db.Column(db.String(50), index=True)
    cycle = db.Column(db.String(20))
    
    merk = db.Column(db.String(50))
    serial = db.Column(db.String(100))
    
    hp = db.Column(db.String(50))
    tlp = db.Column(db.String(50))
    wa = db.Column(db.String(50))
    email = db.Column(db.String(100))
    fax = db.Column(db.String(50))
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))
    
    raw_data = db.Column(JSONB) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================================
# 2. DATABASE TRANSAKSI TAGIHAN (MC)
# ==========================================================
class TransaksiTagihan(db.Model):
    """Tabel Tagihan MC: Menampung rincian tagihan beserta alamat penagihan."""
    __tablename__ = 'transaksi_tagihan'
    id = db.Column(db.Integer, primary_key=True)
    # FIX V18: Dibuat Soft-Link agar tidak ikut terhapus saat CID di-truncate
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), index=True) 
    
    alm1_pel = db.Column(db.Text)
    zona_novak = db.Column(db.String(50))
    notagihan = db.Column(db.String(50))
    total_tagihan = db.Column(db.Float, nullable=False, default=0) 
    
    sumber = db.Column(db.String(10), index=True, default='MC') 
    status_lunas = db.Column(db.Integer, default=0, index=True) 
    
    raw_data = db.Column(JSONB)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_tagihan_nomen_periode'),
    )

# ==========================================================
# 3. DATABASE PEMBAYARAN BULANAN (MB)
# ==========================================================
class DataMB(db.Model):
    """Tabel Master Bayar: Rekap pembayaran bulanan pelanggan."""
    __tablename__ = 'data_mb'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), index=True) 
    
    bulan_rek = db.Column(db.String(20)) 
    tgl_bayar = db.Column(db.String(50))
    nominal = db.Column(db.Float, default=0)
    denda = db.Column(db.Float, default=0)
    lks_bayar = db.Column(db.String(100))
    notagihan = db.Column(db.String(50))
    
    raw_data = db.Column(JSONB)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_mb_nomen_periode'),
    )

# ==========================================================
# 4. DATABASE TRANSAKSI HARIAN (DAILY)
# ==========================================================
class DataDaily(db.Model):
    """Tabel Koleksi Harian: Rekam jejak transaksi Water & Non-Water per hari."""
    __tablename__ = 'data_daily'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), nullable=False, index=True)
    periode = db.Column(db.String(10), index=True) # Tambahan: Memudahkan filter by periode
    
    pay_dt = db.Column(db.String(50))
    bill_period = db.Column(db.String(50))
    pay_amt = db.Column(db.Float, default=0)
    pay_status_flg = db.Column(db.String(20))
    bill_type = db.Column(db.String(50))
    typecust1 = db.Column(db.String(50))
    pay_loc = db.Column(db.String(100))
    bill_id = db.Column(db.String(50))
    ab = db.Column(db.String(50))
    status = db.Column(db.String(50))
    
    raw_data = db.Column(JSONB)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'bill_id', name='uix_daily_nomen_bill'),
    )

# ==========================================================
# 5. DATABASE MAINBILL (RINCIAN METER)
# ==========================================================
class DataMainbill(db.Model):
    """Tabel MainBill: Semua rincian teknis pembacaan meter masuk Jalur Cepat."""
    __tablename__ = 'data_mainbill'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), index=True) 
    
    jenis_pelanggan = db.Column(db.String(100))
    cc = db.Column(db.String(20))
    pcezbk = db.Column(db.String(20))
    tarif = db.Column(db.String(20))
    bill_cycle = db.Column(db.String(20))
    read_method = db.Column(db.String(50))
    konsumsi = db.Column(db.Float, default=0)
    tagihan_air = db.Column(db.Float, default=0)
    start_read = db.Column(db.String(50))
    start_read_stan = db.Column(db.String(50))
    end_read = db.Column(db.String(50))
    hari_baca = db.Column(db.String(20))
    
    raw_data = db.Column(JSONB)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_mainbill_nomen_periode'),
    )

# ==========================================================
# 6. DATABASE SPOT BILL (SBRS)
# ==========================================================
class DataSBRS(db.Model):
    """Tabel Analisa SBRS: Mendukung Denormalisasi Turbo & Zero Data Loss."""
    __tablename__ = 'data_sbrs'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), nullable=False, index=True) 
    
    nama = db.Column(db.String(150))
    alamat = db.Column(db.Text)
    pcez = db.Column(db.String(20), index=True)
    rayon = db.Column(db.String(20))
    tarif = db.Column(db.String(20))
    ab = db.Column(db.String(50), default='AB Sunter', index=True)
    kelurahan = db.Column(db.String(100), index=True)
    
    raw_data = db.Column(JSONB) 
    
    stand_meter = db.Column(db.Float, default=0)
    bulan_ini = db.Column(db.Float, default=0)
    rata_rata = db.Column(db.Float, default=15)
    kategori_anomali = db.Column(db.String(50), index=True)
    
    status_audit = db.Column(db.Integer, default=0, index=True)
    tgl_audit = db.Column(db.DateTime)
    catatan_lapangan = db.Column(db.Text)
    foto_meter_path = db.Column(db.String(255))
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_sbrs_nomen_periode'),
    )

# ==========================================================
# 7. DATABASE ARREARS DEBT (TUNGGAKAN)
# ==========================================================
class DataArrdebt(db.Model):
    """Tabel Tunggakan: Menyimpan data tunggakan (Arrears Debt) historis."""
    __tablename__ = 'data_arrdebt'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), index=True)
    nominal = db.Column(db.Float)
    
    raw_data = db.Column(JSONB)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_arrdebt_nomen_periode'),
    )

# ==========================================================
# 8. DATABASE AUDITOR (LAPANGAN)
# ==========================================================
class AnalisaAuditor(db.Model):
    """Tabel Riwayat Kunjungan Petugas Lapangan."""
    __tablename__ = 'analisa_auditor'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), index=True)
    hasil_kunjungan = db.Column(db.String(100), index=True)
    foto_bukti = db.Column(db.String(255))
    tgl_janji_bayar = db.Column(db.Date)
    lat_audit = db.Column(db.Float)
    long_audit = db.Column(db.Float)
    auditor_name = db.Column(db.String(100), index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
