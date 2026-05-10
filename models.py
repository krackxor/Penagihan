from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB # Penting untuk kontainer 50+ Header

# Inisialisasi database
db = SQLAlchemy()

class MasterPetugas(db.Model):
    """Tabel Petugas: Satu PCEZ bisa punya banyak peran (Tagihan/SBRS)."""
    __tablename__ = 'master_petugas'
    id = db.Column(db.Integer, primary_key=True)
    pcez = db.Column(db.String(20), index=True)
    nama_petugas = db.Column(db.String(100), nullable=False)
    peran = db.Column(db.String(20), index=True) # TAGIHAN, PENCATATAN, SBRS

class MasterPelanggan(db.Model):
    """Tabel Induk Pelanggan: Data permanen dari CID (Dilengkapi JSONB untuk 50 Header)."""
    __tablename__ = 'master_pelanggan'
    nomen = db.Column(db.String(8), primary_key=True) # PK otomatis Index
    nama = db.Column(db.String(150))
    ab = db.Column(db.String(50), default='AB Sunter', index=True)
    rayon = db.Column(db.String(50), index=True)
    kelurahan = db.Column(db.String(100), index=True)
    pcez = db.Column(db.String(20), index=True)
    alamat = db.Column(db.Text)
    tarif = db.Column(db.String(20))
    hp = db.Column(db.String(20))
    wa = db.Column(db.String(20))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # KUNCI SINERGI V18: Brankas penyimpan 50+ Kolom CID
    raw_data = db.Column(JSONB) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TransaksiTagihan(db.Model):
    """Tabel Tagihan: Menampung jutaan baris data MC & ARDEBT (Sumber Top 500)."""
    __tablename__ = 'transaksi_tagihan'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    nominal = db.Column(db.Float, nullable=False)
    periode = db.Column(db.String(10), index=True) # YYYYMM
    sumber = db.Column(db.String(10), index=True) # MC / MB / ARDEBT
    status_lunas = db.Column(db.Integer, default=0, index=True) # 0=Belum, 1=Lunas
    tgl_bayar = db.Column(db.String(50))
    
    # KUNCI SINERGI V18: Brankas penyimpan puluhan Kolom MC
    raw_data = db.Column(JSONB)

    __table_args__ = (
        # Gembok unik ini WAJIB ada agar Upsert MC tidak Crash
        UniqueConstraint('nomen', 'periode', name='uix_tagihan_nomen_periode'),
    )

class DataSBRS(db.Model):
    """
    Tabel Analisa SBRS: Mendukung Denormalisasi Turbo & Zero Data Loss.
    """
    __tablename__ = 'data_sbrs'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    periode = db.Column(db.String(10), nullable=False, index=True) # YYYYMM
    
    # --- KOLOM TURBO ---
    nama = db.Column(db.String(150))
    alamat = db.Column(db.Text)
    pcez = db.Column(db.String(20), index=True)
    rayon = db.Column(db.String(20))
    tarif = db.Column(db.String(20))
    ab = db.Column(db.String(50), default='AB Sunter', index=True)
    kelurahan = db.Column(db.String(100), index=True)
    
    # --- KONTAINER DATA ASLI ---
    raw_data = db.Column(JSONB) 
    
    # --- DATA KONSUMSI ---
    stand_meter = db.Column(db.Float, default=0)
    bulan_ini = db.Column(db.Float, default=0)
    rata_rata = db.Column(db.Float, default=15)
    kategori_anomali = db.Column(db.String(50), index=True)
    
    # --- FITUR AUDIT LAPANGAN ---
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

class DataMB(db.Model):
    """Tabel Master Bayar: Penyapu bersih halaman Top 500 Tunggakan."""
    __tablename__ = 'data_mb'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    periode = db.Column(db.String(10), index=True)
    tgl_bayar = db.Column(db.String(50))
    nominal = db.Column(db.Float)
    denda = db.Column(db.Float)
    lks_bayar = db.Column(db.String(100))
    
    raw_data = db.Column(JSONB)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_mb_nomen_periode'),
    )

class DataArrdebt(db.Model):
    """Tabel Tunggakan: Menyimpan data tunggakan (Arrears Debt) historis PAM JAYA."""
    __tablename__ = 'data_arrdebt'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    periode = db.Column(db.String(10), index=True)
    nominal = db.Column(db.Float)
    
    raw_data = db.Column(JSONB)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_arrdebt_nomen_periode'),
    )

class DataMainbill(db.Model):
    """Tabel MainBill: Data Final Matang dari SBRS sebelum jadi MC."""
    __tablename__ = 'data_mainbill'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    periode = db.Column(db.String(10), index=True)
    total_tagihan = db.Column(db.Float)
    konsumsi = db.Column(db.Float)
    
    raw_data = db.Column(JSONB)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('nomen', 'periode', name='uix_mainbill_nomen_periode'),
    )

class AnalisaAuditor(db.Model):
    """Tabel Riwayat Kunjungan Petugas Lapangan."""
    __tablename__ = 'analisa_auditor'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    hasil_kunjungan = db.Column(db.String(100), index=True)
    foto_bukti = db.Column(db.String(255))
    tgl_janji_bayar = db.Column(db.Date)
    lat_audit = db.Column(db.Float)
    long_audit = db.Column(db.Float)
    auditor_name = db.Column(db.String(100), index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
