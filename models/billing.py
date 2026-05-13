from extensions import db

class TransaksiTagihan(db.Model):
    __tablename__ = 'transaksi_tagihan'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), index=True) # Format YYYYMM [cite: 1326]
    total_tagihan = db.Column(db.Float, default=0.0) # Target MC [cite: 1547]
    status_lunas = db.Column(db.Integer, default=0) # 0: Belum, 1: Lunas [cite: 1470]
    raw_data = db.Column(db.JSON, default={})
    
    # Mencegah duplikasi data untuk pelanggan yang sama di periode yang sama [cite: 923]
    __table_args__ = (db.UniqueConstraint('nomen', 'periode', name='_nomen_periode_uc'),)
