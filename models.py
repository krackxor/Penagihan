from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Inisialisasi database
db = SQLAlchemy()

class MasterPetugas(db.Model):
    """
    Tabel Petugas Berdasarkan Peran.
    Satu PCEZ bisa punya 3 baris (Penagihan, Pencatatan, SBRS).
    """
    __tablename__ = 'master_petugas'
    id = db.Column(db.Integer, primary_key=True)
    pcez = db.Column(db.String(20), index=True)              # Ditambah Index
    nama_petugas = db.Column(db.String(100), nullable=False)
    peran = db.Column(db.String(20), index=True)             # Ditambah Index untuk filter peran

class MasterPelanggan(db.Model):
    """
    Tabel Induk Pelanggan (Data dari CID).
    Menampung semua informasi wilayah.
    """
    __tablename__ = 'master_pelanggan'
    # Nomen sebagai Primary Key otomatis sudah ter-index
    nomen = db.Column(db.String(8), primary_key=True)
    nama = db.Column(db.String(100))
    
    ab = db.Column(db.String(50), default='AB Sunter', index=True) 
    rayon = db.Column(db.String(50), index=True)
    kelurahan = db.Column(db.String(50), index=True)
    
    # PCEZ diberi index karena sering digunakan untuk mencari siapa petugasnya
    pcez = db.Column(db.String(20), index=True)
    
    alamat = db.Column(db.Text)
    tarif = db.Column(db.String(20))
    
    # Kontak & Lokasi
    hp = db.Column(db.String(20))
    wa = db.Column(db.String(20))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    def get_petugas(self, kategori):
        """Fungsi pintar untuk memanggil nama petugas sesuai urusannya."""
        p = MasterPetugas.query.filter_by(pcez=self.pcez, peran=kategori).first()
        return p.nama_petugas if p else "Belum Ada Petugas"

class TransaksiTagihan(db.Model):
    """
    Tabel Tagihan (Data dari MC & ARDEBT).
    """
    __tablename__ = 'transaksi_tagihan'
    id = db.Column(db.Integer, primary_key=True)
    # ForeignKey harus diberi index agar Join antar tabel jadi kencang
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    nominal = db.Column(db.Float, nullable=False)
    periode = db.Column(db.String(6), index=True) # Index untuk filter bulan/tahun
    sumber = db.Column(db.String(10), index=True) # Index untuk filter MC/ARDEBT
    status_lunas = db.Column(db.Integer, default=0, index=True)

class AnalisaAuditor(db.Model):
    """
    Tabel Laporan Lapangan hasil kerja petugas.
    """
    __tablename__ = 'analisa_auditor'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    hasil_kunjungan = db.Column(db.String(100), index=True)
    foto_bukti = db.Column(db.String(255))
    tgl_janji_bayar = db.Column(db.Date)
    
    lat_audit = db.Column(db.Float)
    long_audit = db.Column(db.Float)
    
    auditor_name = db.Column(db.String(100), index=True)
    pcez_saat_ini = db.Column(db.String(20), index=True)
    
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)

class DataSBRS(db.Model):
    """
    Tabel khusus analisa pembacaan meter (Anomali SBRS).
    """
    __tablename__ = 'data_sbrs'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'), index=True)
    bulan_ini = db.Column(db.Integer)
    bulan_lalu = db.Column(db.Integer)
    rata_rata = db.Column(db.Integer)
    stand_meter = db.Column(db.Integer)
    # Index kategori agar Summary Dashboard (Zero/Ekstrem) tampil instan
    kategori_anomali = db.Column(db.String(50), index=True)
