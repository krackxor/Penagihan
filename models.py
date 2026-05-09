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
    id = db.Column(db.Integer, primary_key=True) # Gunakan ID Auto-Increment
    pcez = db.Column(db.String(20))              # Contoh: 0920504
    nama_petugas = db.Column(db.String(100), nullable=False) # Contoh: Wahyu
    peran = db.Column(db.String(20))             # Isi: 'TAGIHAN', 'CATAT', atau 'ANOMALI'

class MasterPelanggan(db.Model):
    """
    Tabel Induk Pelanggan (Data dari CID).
    Menampung semua informasi wilayah: AB, Rayon, Kelurahan, sampai PCEZ.
    """
    __tablename__ = 'master_pelanggan'
    nomen = db.Column(db.String(8), primary_key=True)
    nama = db.Column(db.String(100))
    
    # Tingkatan Wilayah
    ab = db.Column(db.String(50), default='AB Sunter') # Default Sunter sesuai request
    rayon = db.Column(db.String(50))                  # Contoh: Rayon 01
    kelurahan = db.Column(db.String(50))              # Contoh: Sunter Jaya
    
    # PCEZ sekarang berdiri sendiri (tanpa ForeignKey kaku) karena 1 PCEZ ada banyak petugas
    pcez = db.Column(db.String(20))
    
    # Detail Tambahan (Biar pengembangan kedepan enak)
    alamat = db.Column(db.Text)
    tarif = db.Column(db.String(20))
    
    # Kontak & Lokasi
    hp = db.Column(db.String(20))
    wa = db.Column(db.String(20))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    def get_petugas(self, kategori):
        """
        Fungsi pintar untuk memanggil nama petugas sesuai urusannya.
        Kategori bisa diisi: 'TAGIHAN', 'CATAT', atau 'ANOMALI'.
        """
        p = MasterPetugas.query.filter_by(pcez=self.pcez, peran=kategori).first()
        return p.nama_petugas if p else "Belum Ada Petugas"

class TransaksiTagihan(db.Model):
    """
    Tabel Tagihan (Data dari MC & ARDEBT).
    Menyimpan semua angka rupiah yang belum dibayar.
    """
    __tablename__ = 'transaksi_tagihan'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'))
    nominal = db.Column(db.Float, nullable=False)
    periode = db.Column(db.String(6)) # Format: YYYYMM
    sumber = db.Column(db.String(10)) # 'MC' (Berjalan) atau 'ARDEBT' (Ekor)
    status_lunas = db.Column(db.Integer, default=0) # 0: Belum, 1: Lunas

class AnalisaAuditor(db.Model):
    """
    Tabel Laporan Lapangan.
    Merekam hasil kerja Wahyu dkk (Foto, Hasil Kunjungan, GPS).
    """
    __tablename__ = 'analisa_auditor'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'))
    hasil_kunjungan = db.Column(db.String(100)) # Janji Bayar, Kosong, dll
    foto_bukti = db.Column(db.String(255))
    tgl_janji_bayar = db.Column(db.Date)
    
    # GPS waktu petugas beneran di lokasi
    lat_audit = db.Column(db.Float)
    long_audit = db.Column(db.Float)
    
    # Catatan siapa yang lapor dan rute mana saat itu
    auditor_name = db.Column(db.String(100))
    pcez_saat_ini = db.Column(db.String(20))
    
    timestamp = db.Column(db.DateTime, default=datetime.now)

class DataSBRS(db.Model):
    """
    Tabel khusus untuk analisa pembacaan meter (SBRS).
    """
    __tablename__ = 'data_sbrs'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(8), db.ForeignKey('master_pelanggan.nomen'))
    bulan_ini = db.Column(db.Integer)  # Pemakaian m3 bulan ini
    bulan_lalu = db.Column(db.Integer) # Pemakaian m3 bulan lalu
    rata_rata = db.Column(db.Integer)  # Rata-rata 3 bulan terakhir
    stand_meter = db.Column(db.Integer)
    kategori_anomali = db.Column(db.String(50)) # Zero, Ekstrem, Turun
