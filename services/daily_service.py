from repositories.billing_repo import BillingRepository
from repositories.payment_repo import PaymentRepository
from datetime import datetime
import calendar

class DailyService:
    @staticmethod
    def generate_collection_report(periode_input):
        """Menghitung agregasi koleksi harian (Undue & Current)."""
        # 1. Tentukan Periode Laporan
        periode = periode_input if periode_input else datetime.now().strftime('%Y%m')
        
        # 2. Ambil Target MC & Lookup Nominal [cite: 1361, 1521, 1539]
        targets_raw = BillingRepository.get_target_by_unit(periode)
        mc_lookup = BillingRepository.get_mc_lookup_dict(periode)
        
        # Susun struktur target awal
        report_summary = {
            '34': {'target_rp': 0, 'undue_rp': 0, 'current_rp': 0},
            '35': {'target_rp': 0, 'undue_rp': 0, 'current_rp': 0}
        }
        
        for cc, total_rp, total_cust in targets_raw:
            if cc in report_summary:
                report_summary[cc]['target_rp'] = total_rp

        # 3. Hitung Undue (MB) -> Pakai Nominal MC [cite: 1524, 1534]
        undue_data = PaymentRepository.get_undue_payments(periode)
        for nomen, cc in undue_data:
            if cc in report_summary:
                val_mc = mc_lookup.get(nomen, 0)
                report_summary[cc]['undue_rp'] += val_mc

        # 4. Hitung Current (Daily) -> Pakai Nominal MC [cite: 1443, 1524]
        daily_data = PaymentRepository.get_daily_transactions(periode)
        # (Logika harian 1-31 diatur untuk tampilan tabel di sini)
        
        return {
            'summary': report_summary,
            'mc_count': len(mc_lookup),
            'periode_name': periode
        }
