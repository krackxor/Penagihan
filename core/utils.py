import re
import polars as pl
from datetime import datetime

class DataCleaner:
    @staticmethod
    def clean_nomen_series(series: pl.Series) -> pl.Series:
        """
        Logika 'Smart Nomen': 
        Menghapus karakter 'K', membuang angka '0' di depan, 
        dan memastikan hasil akhirnya adalah angka inti 8-digit[cite: 1305, 1319].
        """
        return (
            series.cast(pl.Utf8)
            .str.replace_all(r"[^0-9]", "")  # Membuang huruf 'K' atau karakter non-angka lainnya [cite: 1309, 1324]
            .str.strip_chars_start("0")      # Menangani sinkronisasi 8 vs 9 digit (membuang nol di depan) [cite: 1311, 1320]
        )

    @staticmethod
    def format_periode(val: str) -> str:
        """
        Logika 'Smart Periode':
        Mengonversi berbagai format periode mentah (seperti 1/3/2026 atau 012026) 
        menjadi format standar database YYYYMM (contoh: 202603)[cite: 2006, 2357].
        """
        if not val:
            return "000000"
        
        val = str(val).strip()
        try:
            # Jika format MMYYYY (misal dari MB: 012026) -> Jadi YYYYMM (202601) [cite: 2006, 2245]
            if len(val) == 6 and val[2:].startswith("20"):
                return val[2:] + val[:2]
            
            # Jika format tanggal panjang (misal dari Daily: 04-04-2026 atau 01/03/2026 00:00:00) [cite: 2005, 2311]
            date_part = val.split(" ")[0].replace("-", "/")
            parts = date_part.split("/")
            if len(parts) >= 3:
                y = parts[2]
                if len(y) == 2: y = "20" + y # Menangani tahun 26 menjadi 2026
                return f"{y}{parts[1].zfill(2)}"
        except:
            pass
        return "000000"

    @staticmethod
    def shift_period_plus_one(yyyymm: str) -> str:
        """
        Membantu Master Cetak (MC) memajukan periode baca ke periode tagihan.
        Contoh: 202603 (Maret) menjadi 202604 (April)[cite: 2007, 2244].
        """
        if not yyyymm or len(yyyymm) != 6:
            return yyyymm
        try:
            y, m = int(yyyymm[:4]), int(yyyymm[4:])
            if m == 12:
                return f"{y+1}01"
            return f"{y}{m+1:02d}"
        except:
            return yyyymm
