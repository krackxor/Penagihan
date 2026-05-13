from extensions import db

class DataMB(db.Model):
    """Mencatat pelunasan tepat waktu (Undue) [cite: 1368, 1445]"""
    __tablename__ = 'data_mb'
    id = db.Column(db.Integer, primary_key=True)
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), index=True)
    nominal = db.Column(db.Float)

class DataDaily(db.Model):
    """Mencatat koleksi harian piutang (Current) [cite: 1365, 1445]"""
    __tablename__ = 'data_daily'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.String(50), unique=True) # Kunci unik transaksi [cite: 1294]
    nomen = db.Column(db.String(50), index=True)
    periode = db.Column(db.String(10), index=True)
    pay_dt = db.Column(db.String(50)) # Tanggal Bayar [cite: 1327]
    pay_amt = db.Column(db.Float) # Nominal asli bayar (hanya arsip) [cite: 1482]
