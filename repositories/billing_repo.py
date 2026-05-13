from models.billing import TransaksiTagihan
from models.master import MasterPelanggan
from extensions import db
from sqlalchemy import func

class BillingRepository:
    @staticmethod
    def get_target_by_unit(periode):
        """
        Mengambil total target rupiah per unit (34/35) 
        berdasarkan join antara TransaksiTagihan dan MasterPelanggan.
        """
        return db.session.query(
            MasterPelanggan.cc,
            func.sum(TransaksiTagihan.total_tagihan).label('total_rp'),
            func.count(TransaksiTagihan.nomen).label('total_cust')
        ).join(MasterPelanggan, TransaksiTagihan.nomen == MasterPelanggan.nomen)\
         .filter(TransaksiTagihan.periode == periode)\
         .group_by(MasterPelanggan.cc).all()

    @staticmethod
    def get_mc_lookup_dict(periode):
        """
        Membuat kamus (dictionary) lookup nominal MC.
        Sangat penting agar realisasi selamanya mengacu pada Nominal MC.
        """
        query = db.session.query(TransaksiTagihan.nomen, TransaksiTagihan.total_tagihan)\
                  .filter(TransaksiTagihan.periode == periode).all()
        return {row.nomen: row.total_tagihan for row in query}

    @staticmethod
    def update_status_lunas_massal(nomen_list, periode):
        """Menandai lunas banyak pelanggan sekaligus di tabel MC."""
        db.session.query(TransaksiTagihan)\
            .filter(TransaksiTagihan.nomen.in_(nomen_list), TransaksiTagihan.periode == periode)\
            .update({TransaksiTagihan.status_lunas: 1}, synchronize_session=False)
        db.session.commit()
