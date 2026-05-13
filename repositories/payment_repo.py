from models.payment import DataMB, DataDaily
from models.master import MasterPelanggan
from extensions import db

class PaymentRepository:
    @staticmethod
    def get_undue_payments(periode):
        """Mengambil data realisasi pembayaran tepat waktu (Undue) dari MB."""
        return db.session.query(DataMB.nomen, MasterPelanggan.cc)\
                 .join(MasterPelanggan, DataMB.nomen == MasterPelanggan.nomen)\
                 .filter(DataMB.periode == periode).all()

    @staticmethod
    def get_daily_transactions(periode):
        """Mengambil rincian transaksi harian (Current) dari tabel Daily."""
        return db.session.query(
            DataDaily.nomen, 
            DataDaily.pay_dt, 
            MasterPelanggan.cc
        ).join(MasterPelanggan, DataDaily.nomen == MasterPelanggan.nomen)\
         .filter(DataDaily.periode == periode).all()
