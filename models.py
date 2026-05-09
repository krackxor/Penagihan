from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class MasterPelanggan(db.Model):
    """
    SINERGI 1: DATA INDUK PELANGGAN
    Sumber Utama: CID (CUST1_PLG_TMR)
    """
    __tablename__ = 'master_pelanggan'
    
    # Nomen 8 Digit sebagai Primary Key (Clean)
    nomen = db.Column(db.String(20), primary_key=True) 
    nama = db.Column(db.String(150))
    alamat = db.Column(db.Text)
    ab = db.Column(db.String(50), index=True)        # Area Bisnis (Sunter, Dewaruci, dll)
    type_cust1 = db.Column(db.String(50), index=True) # REGULAR / CORPORATE
    pcez = db.Column(db.String(20), index=True)
    rayon = db.Column(db.String(10))
    zona_novak = db.Column(db.String(50))
    tarif = db.Column(db.String(20))
    cycle = db.Column(db.String(10))
    status_aktif = db.Column(db.String(20))
    hp = db.Column(db.String(50))
    
    # Simpan Seluruh Header CID yang tersisa dalam format JSON
    raw_cid_data = db.Column(db.JSON) 
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship ke Tagihan
    tagihan = db.relationship('TransaksiTagihan', backref='pelanggan', lazy=True)


class TransaksiTagihan(db.Model):
    """
    SINERGI 2: DATA TAGIHAN & PIUTANG
    Sumber: MC (Master Cetak), Ardebt, Mainbill
    """
    __tablename__ = 'transaksi_tagihan'
    
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(20), db.ForeignKey('master_pelanggan.nomen'), nullable=False, index=True)
    
    # KUNCI SINERGI: Periode format YYYYMM (Contoh: 202604 untuk MC April)
    periode_tagihan = db.Column(db.String(6), nullable=False, index=True) 
    
    nominal_tagihan = db.Column(db.Float, default=0.0) # Field 'NOMINAL' di MC / 'BILL_AMT' di Ardebt
    kubikasi = db.Column(db.Float, default=0.0)        # Field 'KUBIK'
    no_tagihan = db.Column(db.String(50))              # Field 'NOTAGIHAN' / 'BILL_ID'
    
    # Status Pelunasan (0: Belum, 1: Lunas)
    # Di-update otomatis oleh Mesin Importer saat file MB/Daily Payment masuk
    status_lunas = db.Column(db.Integer, default=0, index=True) 
    tgl_lunas = db.Column(db.DateTime, nullable=True)
    
    sumber_data = db.Column(db.String(20))             # 'MC', 'ARDEBT', 'MAINBILL'
    
    # SIMPAN SEMUA HEADER: Untuk keperluan analisa lain di masa depan
    all_headers = db.Column(db.JSON) 
    
    created_at = db.Column(db.DateTime, default=datetime.now)


class HistoryPembayaran(db.Model):
    """
    SINERGI 3: DATA PEMBAYARAN (CASH IN)
    Sumber: MB (Master Bayar) & Daily Payment
    """
    __tablename__ = 'history_pembayaran'
    
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(20), index=True) # 8 Digit Clean
    
    # Periode tagihan yang dilunasi (YYYYMM)
    # Logika: Bayar di Mei untuk periode_tagihan April (202604)
    periode_tagihan = db.Column(db.String(6), nullable=False, index=True) 
    
    tgl_bayar = db.Column(db.DateTime, index=True) # Tanggal Bayar Real (PAY_DT / TGL_BAYAR)
    nominal_bayar = db.Column(db.Float)
    lokasi_bayar = db.Column(db.String(100))       # PAY_LOC / LKS_BAYAR
    bill_id = db.Column(db.String(50))             # NOTAGIHAN / BILL_ID
    
    sumber_file = db.Column(db.String(20))         # 'MB' atau 'DAILY'
    
    # Simpan Seluruh Header Pembayaran (BCA Mobile, NISP, dll)
    payment_details = db.Column(db.JSON) 
    created_at = db.Column(db.DateTime, default=datetime.now)


class AnalisaAuditor(db.Model):
    """
    SINERGI 4: HASIL KERJA AUDITOR
    Tempat menyimpan 'data analisa dll' yang Anda maksud.
    """
    __tablename__ = 'analisa_auditor'
    
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(20), index=True)
    periode_tagihan = db.Column(db.String(6), index=True)
    
    keterangan_analisa = db.Column(db.Text)        # Catatan Auditor
    hasil_kunjungan = db.Column(db.String(100))    # Janji Bayar, Rumah Kosong, dll
    foto_bukti = db.Column(db.String(255))         # Path ke folder static/uploads/kunjungan
    
    auditor_name = db.Column(db.String(100))
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Tambahan: Simpan koordinat saat audit dilakukan
    lat_audit = db.Column(db.String(50))
    long_audit = db.Column(db.String(50))
