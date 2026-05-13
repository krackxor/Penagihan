from extensions import db

class MasterPelanggan(db.Model):
    __tablename__ = 'master_pelanggan'
    # Nomen 8-digit sebagai primary key [cite: 1282, 1334]
    nomen = db.Column(db.String(50), primary_key=True) 
    cc = db.Column(db.String(20)) # Unit 34 atau 35 [cite: 1320]
    
    # Kolom Petugas Lapangan [cite: 1721]
    petugas_rl = db.Column(db.String(100), index=True)      # Relationship Leader
    petugas_catat = db.Column(db.String(100), index=True)   # Petugas Catat Meter
    petugas_analisa = db.Column(db.String(100), index=True) # Petugas Analisa
    
    # Data tambahan dalam format JSON untuk fleksibilitas [cite: 921]
    raw_data = db.Column(db.JSON, default={})
