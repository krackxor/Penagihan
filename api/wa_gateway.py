"""
WA Gateway Module - Sunter Dashboard Pro
Sinergi & Smart Update:
1. Auto-Format: Mengubah 0812... menjadi 62812... secara otomatis (Autopilot).
2. URL Encoder: Menangani karakter khusus agar pesan tidak rusak saat dibuka.
"""

import urllib.parse

def generate_wa_link(no_hp, pesan):
    # Membersihkan nomor HP dari karakter sampah
    clean_no = "".join(filter(str.isdigit, str(no_hp)))
    
    # Autopilot: Konversi otomatis nomor lokal ke format internasional
    if clean_no.startswith('0'):
        clean_no = '62' + clean_no[1:]
    elif clean_no.startswith('8'):
        clean_no = '62' + clean_no
        
    # Sinergi: Encode pesan agar aman untuk URL browser
    encoded_msg = urllib.parse.quote(pesan)
    
    return f"https://api.whatsapp.com/send?phone={clean_no}&text={encoded_msg}"
