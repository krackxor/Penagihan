import os
import pandas as pd
from datetime import datetime
from dbfread import DBF
from models import db, MasterPelanggan, TransaksiTagihan, HistoryPembayaran
import json

class SmartImporter:
    @staticmethod
    def clean_nomen(nomen):
        """Memastikan Nomen selalu 8 digit angka (Membuang karakter alfabet)"""
        if not nomen: return None
        nomen_str = str(nomen).strip()
        # Ambil 8 digit pertama yang berupa angka
        clean = "".join(filter(str.isdigit, nomen_str))[:8]
        return clean

    @staticmethod
    def parse_periode(val, source_type):
        """Standardisasi Periode ke format YYYYMM"""
        try:
            if source_type == 'MC': # Format: 16/04/2026
                dt = datetime.strptime(val, '%d/%m/%Y')
                return dt.strftime('%Y%m')
            
            elif source_type == 'MB': # Format: 012026 (MMYYYY)
                mm = val[:2]
                yyyy = val[2:]
                return f"{yyyy}{mm}"
            
            elif source_type == 'DAILY': # Format: 01/08/2025
                dt = datetime.strptime(val, '%d/%m/%Y')
                return dt.strftime('%Y%m')
            
            elif source_type == 'ARDEBT': # Format: 200111 (YYYYMM)
                return str(val).strip()
            
            elif source_type == 'MAINBILL': # Format: 01-Apr-26
                dt = datetime.strptime(val, '%d-%b-%y')
                return dt.strftime('%Y%m')
        except:
            return None

    def import_cid(self, file_path):
        """Proses File CID (CUST1_PLG_TMR) - TXT Document"""
        df = pd.read_csv(file_path, sep=':', skipinitialspace=True, names=['key', 'value'], engine='python')
        # CID biasanya formatnya Key: Value per baris, kita perlu pivot atau handle per blok
        # Untuk demo ini, kita asumsikan CSV standar jika data banyak, 
        # namun jika formatnya seperti yang Anda kirim (Key: Value), kita pakai dict:
        data_dict = dict(zip(df['key'], df['value']))
        
        nomen = self.clean_nomen(data_dict.get('NOMEN'))
        if not nomen: return False

        pelanggan = MasterPelanggan.query.get(nomen)
        if not pelanggan:
            pelanggan = MasterPelanggan(nomen=nomen)
        
        pelanggan.nama = data_dict.get('NAMA')
        pelanggan.alamat = data_dict.get('ALAMAT')
        pelanggan.ab = data_dict.get('AB')
        pelanggan.type_cust1 = data_dict.get('TypeCust1')
        pelanggan.pcez = data_dict.get('PCEZ')
        pelanggan.tarif = data_dict.get('TARIFF')
        pelanggan.raw_cid_data = data_dict # Simpan semua header
        
        db.session.add(pelanggan)
        db.session.commit()
        return True

    def import_mc(self, file_path):
        """Proses File Master Cetak (MC) - DBF"""
        table = DBF(file_path, load=True)
        count = 0
        for record in table:
            nomen = self.clean_nomen(record.get('NOMEN'))
            periode = self.parse_periode(record.get('TGL_CATAT'), 'MC')
            
            if nomen and periode:
                tagihan = TransaksiTagihan(
                    nomen=nomen,
                    periode_tagihan=periode,
                    nominal_tagihan=record.get('NOMINAL', 0),
                    kubikasi=record.get('KUBIK', 0),
                    no_tagihan=record.get('NOTAGIHAN'),
                    sumber_data='MC',
                    all_headers=dict(record) # Simpan semua header
                )
                db.session.add(tagihan)
                count += 1
        
        db.session.commit()
        return count

    def import_pembayaran(self, file_path, type='MB'):
        """Proses MB (DBF) atau Daily Payment (TXT)"""
        if type == 'MB':
            table = DBF(file_path, load=True)
            records = [dict(r) for r in table]
        else:
            # Daily Payment TXT (Asumsi Pipe Separated atau Key:Value)
            # Logic disesuaikan dengan format TXT Anda
            df = pd.read_csv(file_path, sep=':', skipinitialspace=True, names=['key', 'value'], engine='python')
            records = [dict(zip(df['key'], df['value']))]

        for rec in records:
            nomen = self.clean_nomen(rec.get('NOMEN'))
            
            # Tentukan Periode Tagihan yang dibayar
            if type == 'MB':
                periode_bayar = self.parse_periode(str(rec.get('BULAN_REK')), 'MB')
                tgl_bayar = datetime.strptime(rec.get('TGL_BAYAR'), '%d/%m/%Y') if rec.get('TGL_BAYAR') else datetime.now()
            else:
                periode_bayar = self.parse_periode(rec.get('BILL_PERIOD'), 'DAILY')
                tgl_bayar = datetime.strptime(rec.get('PAY_DT'), '%d-%m-%Y') if rec.get('PAY_DT') else datetime.now()

            if nomen and periode_bayar:
                # 1. Simpan ke History
                hist = HistoryPembayaran(
                    nomen=nomen,
                    periode_tagihan=periode_bayar,
                    tgl_bayar=tgl_bayar,
                    nominal_bayar=rec.get('NOMINAL') or rec.get('PAY_AMT'),
                    sumber_file=type,
                    payment_details=rec
                )
                db.session.add(hist)

                # 2. SINERGI: Update status lunas di tabel tagihan
                tagihan = TransaksiTagihan.query.filter_by(
                    nomen=nomen, 
                    periode_tagihan=periode_bayar
                ).first()
                
                if tagihan:
                    tagihan.status_lunas = 1
                    tagihan.tgl_lunas = tgl_bayar

        db.session.commit()
        return True

    def import_ardebt(self, file_path):
        """Proses File Ardebt - TXT"""
        # Logic parse TXT Ardebt Anda
        # ... (mirip dengan CID tapi looping untuk banyak record)
        pass

    def import_mainbill(self, file_path):
        """Proses File Mainbill - TXT"""
        # Logic parse TXT Mainbill Anda
        # ...
        pass
