import re
import polars as pl
from datetime import datetime

class DataCleaner:
    @staticmethod
    def clean_nomen_series(series: pl.Series) -> pl.Series:
        """
        Logika 'Smart Nomen': 
        1. Menghapus semua karakter non-angka (seperti 'K') [cite: 1234, 1247]
        2. Menghapus angka '0' di depan (mengubah 9-digit NOREK jadi 8-digit NOMEN) [cite: 1249, 1257]
        """
        return (
            series.cast(pl.Utf8)
            .str.replace_all(r"[^0-9]", "")  # Buang karakter non-angka
            .str.strip_chars_start("0")      # Buang nol di depan
        )

    @staticmethod
    def format_periode(val: str) -> str:
        """
        Logika 'Smart Periode':
        Mengonversi berbagai format (1/3/2026 atau 012026) menjadi YYYYMM (202601)[cite: 1409, 1417].
        """
        if not val:
            return "000000"
        
        val = str(val).strip()
        try:
            # Jika format MMYYYY (012026) -> Jadi YYYYMM (202601)
            if len(val) == 6 and val[2:].startswith("20"):
                return val[2:] + val[:2]
            
            # Jika format tanggal panjang (01/03/2026 00:00:00)
            date_part = val.split(" ")[0].replace("-", "/")
            parts = date_part.split("/")
            if len(parts) >= 3:
                y = parts[2]
                if len(y) == 2: y = "20" + y
                return f"{y}{parts[1].zfill(2)}"
        except:
            pass
        return "000000"

    @staticmethod
    def shift_period_plus_one(yyyymm: str) -> str:
        """Membantu MC memajukan periode baca ke periode tagihan[cite: 1235]."""
        if not yyyymm or len(yyyymm) != 6:
            return yyyymm
        try:
            y, m = int(yyyymm[:4]), int(yyyymm[4:])
            if m == 12:
                return f"{y+1}01"
            return f"{y}{m+1:02d}"
        except:
            return yyyymm
