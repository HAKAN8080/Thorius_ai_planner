"""
SANAL PLANNER - Agentic Tool Calling v2
CSV tabanlı küp verisi ile çalışan akıllı agent
"""

import pandas as pd
import numpy as np
import json
from typing import Optional, List, Dict
import anthropic
import os
import glob
import sys
import io

# Windows cp1254 encoding emoji desteklemiyor - stdout'u UTF-8'e çevir
if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# Sevkiyat motoru artık INLINE - ayrı modül yok
SEVKIYAT_MOTORU_AVAILABLE = True  # Her zaman True çünkü inline
print("✅ Sevkiyat hesaplama INLINE modda çalışıyor")

# =============================================================================
# VERİ YÜKLEYİCİ
# =============================================================================

class KupVeri:
    """CSV ve Excel tabanlı küp verisi yönetimi"""
    
    def __init__(self, veri_klasoru: str):
        """
        veri_klasoru: CSV ve Excel dosyalarının bulunduğu klasör
        """
        self.veri_klasoru = veri_klasoru
        self._yukle()
        self._hazirla()
    
    def _yukle(self):
        """Tüm veri dosyalarını yükle"""
        
        # =====================================================================
        # 1. ANLIK STOK SATIŞ (CSV - parçalı dosyalar)
        # =====================================================================
        stok_satis_files = glob.glob(os.path.join(self.veri_klasoru, "anlik_stok_satis*.csv"))
        if stok_satis_files:
            dfs = []
            for f in stok_satis_files:
                try:
                    df = pd.read_csv(f, encoding='utf-8', sep=None, engine='python')
                except:
                    try:
                        df = pd.read_csv(f, encoding='latin-1', sep=None, engine='python')
                    except:
                        df = pd.read_csv(f, encoding='utf-8', sep=';')
                dfs.append(df)
            self.stok_satis = pd.concat(dfs, ignore_index=True)
        else:
            self.stok_satis = pd.DataFrame()
        
        
        # =====================================================================
        # 2. MASTER TABLOLAR (CSV)
        # =====================================================================
        urun_path = os.path.join(self.veri_klasoru, "urun_master.csv")
        if os.path.exists(urun_path):
            try:
                self.urun_master = pd.read_csv(urun_path, encoding='utf-8', sep=None, engine='python')
            except:
                self.urun_master = pd.read_csv(urun_path, encoding='latin-1', sep=None, engine='python')
        else:
            self.urun_master = pd.DataFrame()
        
        magaza_path = os.path.join(self.veri_klasoru, "magaza_master.csv")
        if os.path.exists(magaza_path):
            try:
                self.magaza_master = pd.read_csv(magaza_path, encoding='utf-8', sep=None, engine='python')
            except:
                self.magaza_master = pd.read_csv(magaza_path, encoding='latin-1', sep=None, engine='python')
        else:
            self.magaza_master = pd.DataFrame()
        
        depo_path = os.path.join(self.veri_klasoru, "depo_stok.csv")
        if os.path.exists(depo_path):
            try:
                self.depo_stok = pd.read_csv(depo_path, encoding='utf-8', sep=None, engine='python')
            except:
                self.depo_stok = pd.read_csv(depo_path, encoding='latin-1', sep=None, engine='python')
        else:
            self.depo_stok = pd.DataFrame()
        
        kpi_path = os.path.join(self.veri_klasoru, "kpi.csv")
        if os.path.exists(kpi_path):
            try:
                self.kpi = pd.read_csv(kpi_path, encoding='utf-8', sep=None, engine='python')
            except:
                self.kpi = pd.read_csv(kpi_path, encoding='latin-1', sep=None, engine='python')
        else:
            self.kpi = pd.DataFrame()
        
        # =====================================================================
        # 3. TRADING RAPORU (Excel) - trading.xlsx veya *CUBE* dosyası
        # =====================================================================
        self.trading = pd.DataFrame()
        self.trading_detay = pd.DataFrame()
        self.online_offline = pd.DataFrame()

        # Dosya bul: önce trading.xlsx, sonra *CUBE* pattern
        trading_path = os.path.join(self.veri_klasoru, "trading.xlsx")
        if not os.path.exists(trading_path):
            cube_files = glob.glob(os.path.join(self.veri_klasoru, "*CUBE*.xlsx")) + \
                         glob.glob(os.path.join(self.veri_klasoru, "*cube*.xlsx")) + \
                         glob.glob(os.path.join(self.veri_klasoru, "*Cube*.xlsx"))
            if cube_files:
                trading_path = cube_files[0]
                print(f"   📂 CUBE dosyası bulundu: {os.path.basename(trading_path)}")
            else:
                trading_path = None

        if trading_path and os.path.exists(trading_path):
            try:
                xl = pd.ExcelFile(trading_path)
                sheet_names = xl.sheet_names
                print(f"   📋 Trading sheet'leri: {sheet_names}")

                # --- Ana trading verisi (Trading > Trading Sunum > mtd > ilk sheet) ---
                # Trading sheet Grand Total ve ...Total satirlari icerir
                trading_sheet = None
                for candidate in ['Trading', 'Trading Sunum', 'mtd']:
                    if candidate in sheet_names:
                        trading_sheet = candidate
                        break
                if trading_sheet is None:
                    trading_sheet = sheet_names[0]

                self.trading = self._excel_oto_header(xl, trading_sheet)
                print(f"   ✅ Trading yüklendi ({trading_sheet}): {len(self.trading)} satır, kolonlar: {list(self.trading.columns)[:8]}")

                # --- Trading detay (Trading Sunum sheet - CategoryLeader/TribeLeader bilgisi) ---
                if 'Trading Sunum' in sheet_names and trading_sheet != 'Trading Sunum':
                    self.trading_detay = self._excel_oto_header(xl, 'Trading Sunum')
                    print(f"   ✅ Trading Sunum yüklendi: {len(self.trading_detay)} satır")

                # --- Online vs Offline ---
                for candidate in ['offline vs online', 'Offline vs Online', 'offline_online']:
                    if candidate in sheet_names:
                        self.online_offline = self._excel_oto_header(xl, candidate)
                        print(f"   ✅ Online/Offline yüklendi ({candidate}): {len(self.online_offline)} satır")
                        break

            except Exception as e:
                print(f"   ⚠️ Trading dosyası okunamadı: {e}")
                self.trading = pd.DataFrame()
        
        # =====================================================================
        # 4. SC TABLOSU (Excel - birden fazla sayfa)
        # =====================================================================
        sc_files = glob.glob(os.path.join(self.veri_klasoru, "*SC*.xlsx")) + \
                   glob.glob(os.path.join(self.veri_klasoru, "*sc*.xlsx")) + \
                   glob.glob(os.path.join(self.veri_klasoru, "*Tablosu*.xlsx"))
        
        self.sc_sayfalari = {}
        if sc_files:
            sc_path = sc_files[0]  # İlk bulunan SC dosyası
            try:
                xl = pd.ExcelFile(sc_path)
                for sheet_name in xl.sheet_names:
                    try:
                        self.sc_sayfalari[sheet_name] = pd.read_excel(xl, sheet_name=sheet_name)
                    except:
                        pass
            except Exception as e:
                print(f"SC dosyası okunamadı: {e}")
        
        # =====================================================================
        # 5. COVER DİAGRAM (Excel) - Mağaza×AltGrup cover analizi
        # =====================================================================
        cover_files = []
        
        # Tüm xlsx dosyalarını tara
        for f in os.listdir(self.veri_klasoru):
            if not f.endswith('.xlsx') and not f.endswith('.xls'):
                continue
            f_lower = f.lower()
            # Cover içeren dosyalar
            if 'cover' in f_lower:
                full_path = os.path.join(self.veri_klasoru, f)
                cover_files.append(full_path)
                print(f"   📂 Cover dosyası bulundu: {f}")
        
        self.cover_diagram = pd.DataFrame()
        if cover_files:
            try:
                print(f"   📖 Cover okunuyor: {cover_files[0]}")
                self.cover_diagram = pd.read_excel(cover_files[0], sheet_name=0)
                print(f"   ✅ Cover Diagram yüklendi: {len(self.cover_diagram)} satır, {len(self.cover_diagram.columns)} kolon")
            except Exception as e:
                print(f"   ⚠️ Cover Diagram okunamadı: {e}")
        else:
            print(f"   ⚠️ Cover dosyası bulunamadı")
        
        # =====================================================================
        # 6. KAPASİTE-PERFORMANS (Excel) - Mağaza doluluk analizi
        # =====================================================================
        kapasite_files = []
        
        # Tüm xlsx dosyalarını tara
        for f in os.listdir(self.veri_klasoru):
            if not f.endswith('.xlsx') and not f.endswith('.xls'):
                continue
            f_lower = f.lower()
            # Kapasite veya Periyod içeren dosyalar
            if 'kapasite' in f_lower or 'periyod' in f_lower or 'zet' in f_lower:
                full_path = os.path.join(self.veri_klasoru, f)
                kapasite_files.append(full_path)
                print(f"   📂 Kapasite dosyası bulundu: {f}")
        
        self.kapasite = pd.DataFrame()
        if kapasite_files:
            try:
                kap_path = kapasite_files[0]
                print(f"   📖 Kapasite okunuyor: {kap_path}")
                kap_xl = pd.ExcelFile(kap_path)
                kap_sheets = kap_xl.sheet_names
                print(f"   📋 Kapasite sheet'leri: {kap_sheets}")

                # Öncelik: son1hafta > son 1 hafta > ilk sheet
                kap_sheet = None
                for candidate in kap_sheets:
                    c_lower = candidate.lower().replace(' ', '')
                    if 'son1hafta' in c_lower or 'son1 hafta' in c_lower:
                        kap_sheet = candidate
                        break
                if kap_sheet is None:
                    kap_sheet = kap_sheets[0]

                # Header satırını otomatik bul: StoreName, Store Capacity, Fiili Doluluk gibi keyword'ler
                KAP_KEYWORDS = [
                    'storename', 'store capacity', 'fiili doluluk', 'store cover',
                    'eop ty store stock', 'avg store stock', 'sales unit',
                    'store stock unit', 'karlı', 'karli', 'capacity dm3',
                ]
                raw = pd.read_excel(kap_xl, sheet_name=kap_sheet, header=None, nrows=15)
                kap_header_row = None
                best = 0
                for idx, row in raw.iterrows():
                    row_text = ' '.join(str(v).lower() for v in row.values if pd.notna(v))
                    matches = sum(1 for kw in KAP_KEYWORDS if kw in row_text)
                    if matches > best and matches >= 2:
                        best = matches
                        kap_header_row = idx

                if kap_header_row is not None:
                    print(f"   📍 Kapasite header satırı: {kap_header_row} ({best} eşleşme)")
                    self.kapasite = pd.read_excel(kap_xl, sheet_name=kap_sheet, header=kap_header_row)
                else:
                    self.kapasite = pd.read_excel(kap_xl, sheet_name=kap_sheet, header=0)

                # Kolon temizliği
                self.kapasite.columns = [str(c).strip() if pd.notna(c) else f'col_{i}' for i, c in enumerate(self.kapasite.columns)]
                self.kapasite = self.kapasite.loc[:, ~self.kapasite.columns.str.startswith('Unnamed')]
                # Tamamen boş satırları kaldır
                self.kapasite = self.kapasite.dropna(how='all')

                print(f"   ✅ Kapasite yüklendi ({kap_sheet}): {len(self.kapasite)} satır, {len(self.kapasite.columns)} kolon")
                print(f"   📋 Kolonlar: {list(self.kapasite.columns)[:10]}...")
            except Exception as e:
                print(f"   ⚠️ Kapasite okunamadı: {e}")
        else:
            print(f"   ⚠️ Kapasite dosyası bulunamadı")
        
        # =====================================================================
        # 7. SİPARİŞ TAKİP (Excel) - Satınalma ve sipariş durumu
        # =====================================================================
        siparis_files = []

        print(f"\n   🔍 SİPARİŞ DOSYASI ARANIYOR...")
        all_xlsx = [f for f in os.listdir(self.veri_klasoru) if f.endswith('.xlsx') or f.endswith('.xls')]
        print(f"   📄 Klasördeki Excel dosyaları ({len(all_xlsx)} adet):")

        # Türkçe karakter normalize fonksiyonu
        def normalize_turkish(text):
            replacements = {
                'ş': 's', 'Ş': 's', 'ı': 'i', 'İ': 'i',
                'ğ': 'g', 'Ğ': 'g', 'ü': 'u', 'Ü': 'u',
                'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c'
            }
            for tr, en in replacements.items():
                text = text.replace(tr, en)
            return text.lower()

        for f in all_xlsx:
            print(f"      - {f}")
            f_lower = f.lower()
            f_normalized = normalize_turkish(f)

            # GENIŞ PATTERN: siparis, takip, satin, yerle, order, purchase
            # Hem orijinal hem normalize edilmiş versiyonda ara
            is_siparis = (
                'siparis' in f_lower or
                'sipariş' in f_lower or
                'siparis' in f_normalized or
                'takip' in f_lower or
                'takip' in f_normalized or
                'satin' in f_lower or
                'satın' in f_lower or
                'satin' in f_normalized or
                'yerle' in f_lower or
                'order' in f_lower or
                'purchase' in f_lower or
                'po_' in f_lower or
                'po ' in f_lower or
                f_lower == 'siparis.xlsx' or
                f_lower.startswith('siparis') or
                f_normalized.startswith('siparis')
            )

            if is_siparis:
                full_path = os.path.join(self.veri_klasoru, f)
                siparis_files.append(full_path)
                print(f"   ✅ Sipariş dosyası BULUNDU: {f}")

        self.siparis_takip = pd.DataFrame()
        if siparis_files:
            for sip_file in siparis_files:
                try:
                    print(f"   📖 Sipariş okunuyor: {sip_file}")
                    # Önce sheet isimlerini kontrol et
                    import openpyxl
                    wb = openpyxl.load_workbook(sip_file, read_only=True)
                    sheet_names = wb.sheetnames
                    print(f"   📋 Sheet'ler: {sheet_names}")
                    wb.close()

                    # İlk sheet'i oku
                    self.siparis_takip = pd.read_excel(sip_file, sheet_name=0)
                    print(f"   ✅ Sipariş Takip yüklendi: {len(self.siparis_takip)} satır, {len(self.siparis_takip.columns)} kolon")
                    print(f"   📋 Kolonlar: {list(self.siparis_takip.columns)[:8]}")
                    break  # İlk başarılı okumada dur
                except Exception as e:
                    print(f"   ⚠️ Sipariş Takip okunamadı ({sip_file}): {e}")
                    import traceback
                    traceback.print_exc()
        else:
            print(f"   ⚠️ Sipariş dosyası bulunamadı - Aranan pattern'lar:")
            print(f"      siparis, sipariş, takip, satın, yerle, order, purchase, po_")
        
        # =====================================================================
        # LOG
        # =====================================================================
        print(f"✅ Veri yüklendi:")
        print(f"   - Stok/Satış: {len(self.stok_satis):,} satır")
        print(f"   - Ürün Master: {len(self.urun_master):,} ürün")
        print(f"   - Mağaza Master: {len(self.magaza_master):,} mağaza")
        print(f"   - Depo Stok: {len(self.depo_stok):,} satır")
        print(f"   - KPI: {len(self.kpi):,} satır")
        print(f"   - Trading: {len(self.trading):,} satır")
        print(f"   - Trading Detay: {len(self.trading_detay):,} satır")
        print(f"   - Online/Offline: {len(self.online_offline):,} satır")
        print(f"   - SC Sayfaları: {list(self.sc_sayfalari.keys())}")
        print(f"   - Cover Diagram: {len(self.cover_diagram):,} satır")
        print(f"   - Kapasite: {len(self.kapasite):,} satır")
        print(f"   - Sipariş Takip: {len(self.siparis_takip):,} satır")
    
    def _excel_oto_header(self, xl, sheet_name):
        """Excel sheet'inde otomatik header satırı bul ve yükle.

        Anahtar kelimeler içeren satırı header olarak kullanır.
        Birleştirilmiş hücreli Excel dosyalarında da çalışır.
        """
        HEADER_KEYWORDS = [
            'ana grup', 'alt grup', 'maingroupdesc', 'subgroupdesc',
            'main group', 'sub group', 'categoryleader', 'tribeleader',
            'mevcut ana grup', 'mevcut ara grup',
            # Tam kolon isimleri (CUBE Trading sheet)
            'ty sales unit', 'ty sales value', 'ty gross profit',
            'lfl sales unit tyvsly', 'lfl sales value tyvsly',
            'achieved ty sales budget', 'ty store cover unit',
            'ty unit sales price', 'maingroupdesc',
        ]

        # Önce header=None ile oku (ilk 30 satır yeterli tarama için)
        try:
            raw = pd.read_excel(xl, sheet_name=sheet_name, header=None, nrows=30)
        except:
            return pd.DataFrame()

        header_row = None
        best_match = 0
        for idx, row in raw.iterrows():
            row_text = ' '.join(str(v).lower() for v in row.values if pd.notna(v))
            matches = sum(1 for kw in HEADER_KEYWORDS if kw in row_text)
            if matches > best_match and matches >= 2:
                best_match = matches
                header_row = idx

        if header_row is not None:
            print(f"      Header satırı: {header_row} ({best_match} eşleşme)")
            df = pd.read_excel(xl, sheet_name=sheet_name, header=header_row)
        else:
            # Fallback: header=0 ile oku
            df = pd.read_excel(xl, sheet_name=sheet_name, header=0)

        # NaN kolon isimlerini temizle
        df.columns = [str(c).strip() if pd.notna(c) else f'col_{i}' for i, c in enumerate(df.columns)]
        # Unnamed kolonları temizle
        df = df.loc[:, ~df.columns.str.startswith('Unnamed')]

        return df

    def _hazirla(self):
        """Veriyi zenginleştir ve hesaplamalar yap"""
        
        if len(self.stok_satis) == 0:
            return
        
        # BOM karakterini temizle ve kolon isimlerini normalize et
        def temizle_kolonlar(df):
            df.columns = df.columns.str.replace('\ufeff', '').str.lower().str.strip()
            return df
        
        self.stok_satis = temizle_kolonlar(self.stok_satis)
        if len(self.urun_master) > 0:
            self.urun_master = temizle_kolonlar(self.urun_master)
        if len(self.magaza_master) > 0:
            self.magaza_master = temizle_kolonlar(self.magaza_master)
        if len(self.depo_stok) > 0:
            self.depo_stok = temizle_kolonlar(self.depo_stok)
        if len(self.kpi) > 0:
            self.kpi = temizle_kolonlar(self.kpi)
        
        print(f"\n🔍 JOIN ÖNCESİ KONTROL:")
        print(f"   Stok/Satış kolonları: {list(self.stok_satis.columns)}")
        print(f"   Ürün Master kolonları: {list(self.urun_master.columns) if len(self.urun_master) > 0 else 'BOŞ'}")
        print(f"   Mağaza Master kolonları: {list(self.magaza_master.columns) if len(self.magaza_master) > 0 else 'BOŞ'}")
        
        # Ürün master ile join
        if len(self.urun_master) > 0 and 'urun_kod' in self.stok_satis.columns and 'urun_kod' in self.urun_master.columns:
            # Veri tiplerini eşitle (integer olarak tut, sonra string yap)
            self.stok_satis['urun_kod'] = pd.to_numeric(self.stok_satis['urun_kod'], errors='coerce').fillna(0).astype(int).astype(str)
            self.urun_master['urun_kod'] = pd.to_numeric(self.urun_master['urun_kod'], errors='coerce').fillna(0).astype(int).astype(str)
            
            urun_kolonlar = ['urun_kod']
            for kol in ['kategori_kod', 'umg', 'mg', 'marka_kod', 'nitelik', 'durum']:
                if kol in self.urun_master.columns:
                    urun_kolonlar.append(kol)
            
            print(f"   Ürün join kolonları: {urun_kolonlar}")
            print(f"   Stok urun_kod örnek: {self.stok_satis['urun_kod'].head(3).tolist()}")
            print(f"   Master urun_kod örnek: {self.urun_master['urun_kod'].head(3).tolist()}")
            
            if len(urun_kolonlar) > 1:
                before_len = len(self.stok_satis)
                self.stok_satis = self.stok_satis.merge(
                    self.urun_master[urun_kolonlar],
                    on='urun_kod',
                    how='left'
                )
                print(f"   ✅ Ürün join: {before_len} → {len(self.stok_satis)} satır")
                
                # Join sonrası kontrol
                if 'kategori_kod' in self.stok_satis.columns:
                    non_null = self.stok_satis['kategori_kod'].notna().sum()
                    print(f"   kategori_kod dolu: {non_null:,} / {len(self.stok_satis):,}")
        
        # Mağaza master ile join
        if len(self.magaza_master) > 0 and 'magaza_kod' in self.stok_satis.columns and 'magaza_kod' in self.magaza_master.columns:
            # Veri tiplerini eşitle
            self.stok_satis['magaza_kod'] = pd.to_numeric(self.stok_satis['magaza_kod'], errors='coerce').fillna(0).astype(int).astype(str)
            self.magaza_master['magaza_kod'] = pd.to_numeric(self.magaza_master['magaza_kod'], errors='coerce').fillna(0).astype(int).astype(str)
            
            mag_kolonlar = ['magaza_kod']
            for kol in ['il', 'bolge', 'tip', 'depo_kod']:
                if kol in self.magaza_master.columns:
                    mag_kolonlar.append(kol)
            
            print(f"   Mağaza join kolonları: {mag_kolonlar}")
            print(f"   Stok magaza_kod örnek: {self.stok_satis['magaza_kod'].head(3).tolist()}")
            print(f"   Master magaza_kod örnek: {self.magaza_master['magaza_kod'].head(3).tolist()}")
            
            if len(mag_kolonlar) > 1:
                before_len = len(self.stok_satis)
                self.stok_satis = self.stok_satis.merge(
                    self.magaza_master[mag_kolonlar],
                    on='magaza_kod',
                    how='left'
                )
                print(f"   ✅ Mağaza join: {before_len} → {len(self.stok_satis)} satır")
                
                # Join sonrası kontrol
                if 'bolge' in self.stok_satis.columns:
                    non_null = self.stok_satis['bolge'].notna().sum()
                    print(f"   bolge dolu: {non_null:,} / {len(self.stok_satis):,}")
        
        # KPI ile join (mg bazlı)
        if len(self.kpi) > 0 and 'mg' in self.stok_satis.columns:
            kpi_df = self.kpi.copy()
            if 'mg_id' in kpi_df.columns:
                kpi_df = kpi_df.rename(columns={'mg_id': 'mg'})
            
            if 'mg' in kpi_df.columns:
                # Veri tiplerini eşitle
                self.stok_satis['mg'] = pd.to_numeric(self.stok_satis['mg'], errors='coerce').fillna(0).astype(int).astype(str)
                kpi_df['mg'] = pd.to_numeric(kpi_df['mg'], errors='coerce').fillna(0).astype(int).astype(str)
                
                self.stok_satis = self.stok_satis.merge(
                    kpi_df,
                    on='mg',
                    how='left'
                )
                print(f"   ✅ KPI join tamamlandı")
        
        # Kar hesapla (kolonlar varsa)
        if 'ciro' in self.stok_satis.columns and 'smm' in self.stok_satis.columns:
            self.stok_satis['kar'] = self.stok_satis['ciro'] - self.stok_satis['smm']
        else:
            self.stok_satis['kar'] = 0
            self.stok_satis['ciro'] = self.stok_satis.get('ciro', 0)
        
        # Kar marjı
        if 'ciro' in self.stok_satis.columns:
            self.stok_satis['kar_marji'] = np.where(
                self.stok_satis['ciro'] > 0,
                self.stok_satis['kar'] / self.stok_satis['ciro'],
                0
            )
        else:
            self.stok_satis['kar_marji'] = 0
        
        # Haftalık satış (satis kolonunu kullan)
        if 'satis' in self.stok_satis.columns:
            self.stok_satis['haftalik_satis'] = self.stok_satis['satis']
        else:
            self.stok_satis['haftalik_satis'] = 0
        
        # Cover hesapla
        if 'stok' in self.stok_satis.columns:
            self.stok_satis['cover'] = np.where(
                self.stok_satis['haftalik_satis'] > 0,
                self.stok_satis['stok'] / self.stok_satis['haftalik_satis'],
                np.where(self.stok_satis['stok'] > 0, 999, 0)
            )
        else:
            self.stok_satis['cover'] = 0
            self.stok_satis['stok'] = 0
        
        # Stok durumu değerlendirme
        self.stok_satis['stok_durum'] = 'NORMAL'
        
        # min_deger ve max_deger kolonları yoksa varsayılan değer kullan
        if 'min_deger' not in self.stok_satis.columns:
            self.stok_satis['min_deger'] = 3
        if 'max_deger' not in self.stok_satis.columns:
            self.stok_satis['max_deger'] = 20
        if 'forward_cover' not in self.stok_satis.columns:
            self.stok_satis['forward_cover'] = 4
        
        # Min altı = SEVKİYAT GEREKLİ
        mask_min = self.stok_satis['stok'] < self.stok_satis['min_deger'].fillna(3)
        self.stok_satis.loc[mask_min, 'stok_durum'] = 'SEVK_GEREKLI'
        
        # Max üstü = FAZLA STOK
        mask_max = self.stok_satis['stok'] > self.stok_satis['max_deger'].fillna(20)
        self.stok_satis.loc[mask_max, 'stok_durum'] = 'FAZLA_STOK'
        
        # Cover hedefin üstünde = YAVAS
        mask_cover = self.stok_satis['cover'] > self.stok_satis['forward_cover'].fillna(4) * 3
        self.stok_satis.loc[mask_cover & (self.stok_satis['stok_durum'] == 'NORMAL'), 'stok_durum'] = 'YAVAS'
        
        # Detaylı debug bilgisi
        print(f"\n📊 VERİ DURUMU:")
        print(f"   - Toplam kayıt: {len(self.stok_satis):,}")
        print(f"   - Kolonlar: {list(self.stok_satis.columns)}")
        
        # Kritik kolonları kontrol et
        for kol in ['magaza_kod', 'urun_kod', 'kategori_kod', 'mg', 'bolge']:
            if kol in self.stok_satis.columns:
                non_null = self.stok_satis[kol].notna().sum()
                unique_vals = self.stok_satis[kol].dropna().unique()[:5]
                print(f"   ✅ {kol}: {non_null:,} dolu, örnek değerler: {list(unique_vals)}")
            else:
                print(f"   ❌ {kol}: KOLON YOK")


# =============================================================================
# ARAÇ FONKSİYONLARI
# =============================================================================

"""
TRADING ANALİZ FONKSİYONU - GÜNCELLENMIŞ VERSİYON
CEO Talepleri:
1. TY LFL Sales Value LC < %5 olan grupları gösterme
2. "Delist" kelimesi geçen grupları gösterme
3. Sezon dışı grupları gösterme (Plaj Havlusu, Ev Giysisi vb.)
"""

def trading_analiz(kup: KupVeri, ana_grup: str = None, ara_grup: str = None) -> str:
    """
    Trading raporu analizi - 3 Seviyeli Hiyerarşi
    
    Hiyerarşi Kolonları:
    - Mevcut Ana Grup: RENKLİ KOZMETİK, CİLT BAKIM, SAÇ BAKIM, PARFÜM...
    - Mevcut Ara Grup: GÖZ ÜRÜNLERİ, YÜZ ÜRÜNLERİ, ŞAMPUAN...
    - Alt Grup: MASKARA, FAR, FONDOTEN... (en detay seviye)
    
    FİLTRELEME KURALLARI (CEO Talebi):
    - TY LFL Sales Value LC < %5 olan gruplar → HARİÇ
    - "Delist" kelimesi geçen gruplar → HARİÇ
    - Sezon dışı gruplar → HARİÇ (Plaj Havlusu, Ev Giysisi vb.)
    
    Kullanım:
    - trading_analiz() → Şirket özeti + Ana Gruplar
    - trading_analiz(ana_grup="RENKLİ KOZMETİK") → Ara Grup detayı
    - trading_analiz(ana_grup="RENKLİ KOZMETİK", ara_grup="GÖZ ÜRÜNLERİ") → Alt Grup detayı
    """
    
    if len(kup.trading) == 0:
        return "❌ Trading raporu yüklenmemiş."
    
    # =====================================================================
    # FİLTRELEME KURALLARI - CEO TALEBİ
    # =====================================================================
    SEZON_DISI_GRUPLAR = [
        'PLAJ', 'HAVLU', 'EV GİYSİ', 'EV GİYİM', 'PLAJ HAVLUSU',
        'YAZ HAVLU', 'DENİZ', 'TATIL', 'MAYO', 'BİKİNİ',
        'BEACH', 'TOWEL', 'HOME WEAR'
    ]
    
    sonuc = []
    df = kup.trading.copy()
    
    # Kolon isimlerini normalize et
    df.columns = [str(c).strip() for c in df.columns]
    kolonlar = list(df.columns)
    print(f"Trading kolonları: {kolonlar[:10]}")
    
    # Hiyerarşi kolonlarını bul (hem eski hem CUBE formatı)
    col_ana_grup = None
    col_ara_grup = None
    col_alt_grup = None

    for kol in df.columns:
        kol_lower = str(kol).lower().strip()
        # Ana Grup: 'Mevcut Ana Grup', 'Ana Grup', 'MainGroupDesc'
        if col_ana_grup is None and (
            'ana grup' in kol_lower or 'ana_grup' in kol_lower or
            kol_lower == 'maingroupdesc' or kol_lower == 'main group desc' or
            kol_lower == 'main group'
        ):
            col_ana_grup = kol
        # Ara Grup: 'Mevcut Ara Grup' (3 seviyeli formatta)
        elif col_ara_grup is None and ('ara grup' in kol_lower or 'ara_grup' in kol_lower):
            col_ara_grup = kol
        # Alt Grup: 'Alt Grup', 'SubGroupDesc'
        elif col_alt_grup is None and (
            'alt grup' in kol_lower or 'alt_grup' in kol_lower or
            kol_lower == 'subgroupdesc' or kol_lower == 'sub group desc' or
            kol_lower == 'sub group'
        ):
            col_alt_grup = kol

    # CUBE formatında 2 seviyeli hiyerarşi: Ana Grup + Alt Grup (ara grup yok)
    # Bu durumda alt grubu ara grup gibi kullan
    is_two_level = col_ana_grup is not None and col_ara_grup is None and col_alt_grup is not None
    if is_two_level:
        col_ara_grup = col_alt_grup
        col_alt_grup = None
        print(f"   ℹ️ 2 seviyeli hiyerarşi tespit edildi: ana={col_ana_grup}, ara(alt)={col_ara_grup}")

    print(f"Hiyerarşi kolonları: ana={col_ana_grup}, ara={col_ara_grup}, alt={col_alt_grup}")
    
    # Kolon mapping fonksiyonu - birden fazla keyword seti dener
    def find_col(keywords, exclude=[], alt_keywords_list=None):
        """Kolon ara. alt_keywords_list: alternatif keyword setleri listesi."""
        all_sets = [keywords]
        if alt_keywords_list:
            all_sets.extend(alt_keywords_list)
        for kw_set in all_sets:
            for kol in df.columns:
                kol_lower = str(kol).lower()
                if all(k in kol_lower for k in kw_set) and not any(e in kol_lower for e in exclude):
                    return kol
        return None

    # ==================================================================
    # KRİTİK KOLONLARI BUL (eski format + CUBE Trading formatı)
    # CUBE Trading kolonları:
    #   Achieved TY Sales Budget Unit / Value TRY / Profit Value TRY
    #   TY/LY Store Cover Unit, TY/LY Gross Marjin LC%
    #   LFL Store Stock Unit TYvsLY%, LFL Sales Unit TYvsLY%
    #   LFL Sales Value TYvsLY LC%, LFL Sales Profit TYvsLY LC%
    #   Sales Value TyTWvsTyLW TRY%, TY/LY Unit Sales Price LC
    # ==================================================================

    # Bütçe gerçekleşme
    col_ciro_achieved = find_col(
        ['achieved', 'sales', 'budget', 'value'], ['profit', 'unit']
    )
    col_adet_achieved = find_col(
        ['achieved', 'sales', 'budget', 'unit'], ['value', 'profit']
    )
    col_kar_achieved = find_col(
        ['achieved', 'sales', 'budget', 'profit'], ['unit']
    )

    # Cover
    col_ty_cover = find_col(
        ['ty', 'store', 'cover', 'unit'], ['ly', 'lfl'],
        alt_keywords_list=[['ty', 'store', 'cover']]
    )
    col_ly_cover = find_col(
        ['ly', 'store', 'cover', 'unit'], ['lfl'],
        alt_keywords_list=[['ly', 'store', 'cover']]
    )

    # Marj
    col_ty_marj = find_col(
        ['ty', 'gross', 'marj'], ['ly', 'lfl'],
        alt_keywords_list=[['ty', 'gross', 'margin']]
    )
    col_ly_marj = find_col(
        ['ly', 'gross', 'marj'], ['ty'],
        alt_keywords_list=[['ly', 'lfl', 'gross', 'margin']]
    )

    # LFL değişimler
    col_lfl_ciro = find_col(
        ['lfl', 'sales', 'value', 'tyvsly'], ['unit', 'profit']
    )
    col_lfl_adet = find_col(
        ['lfl', 'sales', 'unit', 'tyvsly'], ['value', 'cost', 'price']
    )
    col_lfl_stok = find_col(
        ['lfl', 'store', 'stock', 'unit', 'tyvsly'], [],
        alt_keywords_list=[['lfl', 'stock', 'unit', 'tyvsly']]
    )
    col_lfl_kar = find_col(
        ['lfl', 'sales', 'profit', 'tyvsly'], ['unit'],
        alt_keywords_list=[['lfl', 'profit', 'tyvsly']]
    )
    col_fiyat_artis = find_col(
        ['lfl', 'unit', 'sales', 'price', 'tyvsly'], ['cost', 'stock']
    )

    # Haftalık değişim (TyTW vs TyLW)
    col_haftalik_ciro = find_col(
        ['sales', 'value', 'tytw', 'tylw'], [],
        alt_keywords_list=[['sales', 'value', 'twvslw']]
    )

    # Birim fiyat
    col_ty_birim_fiyat = find_col(
        ['ty', 'unit', 'sales', 'price', 'lc'], ['lfl', 'ly', 'tyvsly', 'cost', 'twvslw', 'tytw']
    )
    col_ly_birim_fiyat = find_col(
        ['ly', 'lfl', 'unit', 'sales', 'price', 'lc'], ['tyvsly', 'cost', 'twvslw', 'tytw'],
        alt_keywords_list=[['ly', 'unit', 'sales', 'price']]
    )

    # TY/LY Satış tutarları (pay hesabı için)
    col_ty_ciro = find_col(
        ['ty', 'sales', 'value', 'lc'], ['lfl', 'ly', 'tyvsly', 'budget', 'twvslw', 'tytw'],
        alt_keywords_list=[['ty', 'sales', 'value']]
    )
    col_ty_kar = find_col(
        ['ty', 'gross', 'profit', 'lc'], ['ly', 'lfl', 'tyvsly'],
        alt_keywords_list=[['ty', 'gross', 'profit']]
    )
    col_ty_adet = find_col(
        ['ty', 'sales', 'unit'], ['lfl', 'ly', 'tyvsly', 'price', 'budget'],
    )
    col_ty_stok = find_col(
        ['ty', 'avg', 'store', 'stock', 'unit'], ['ly', 'lfl', 'tyvsly', 'cost'],
    )

    # PAY KOLONLARI (eski format uyumluluğu)
    col_adet_pay = find_col(['ty', 'lfl', 'sales', 'unit'], ['tyvsly', 'price', 'cost', 'budget'])
    col_stok_pay = find_col(['ty', 'avg', 'store', 'stock', 'cost', 'lc'], ['tyvsly'])
    col_ciro_pay = find_col(['ty', 'lfl', 'sales', 'value', 'lc'], ['tyvsly'],
        alt_keywords_list=[['ty', 'lfl', 'sales', 'value']]
    )
    col_kar_pay = find_col(['ty', 'lfl', 'gross', 'profit', 'lc'], ['tyvsly'],
        alt_keywords_list=[['ty', 'lfl', 'gross', 'profit']]
    )

    print(f"   Bulunan kolonlar: ciro_achieved={col_ciro_achieved}, adet_achieved={col_adet_achieved}, kar_achieved={col_kar_achieved}")
    print(f"   ty_cover={col_ty_cover}, ly_cover={col_ly_cover}")
    print(f"   ty_marj={col_ty_marj}, ly_marj={col_ly_marj}")
    print(f"   lfl_ciro={col_lfl_ciro}, lfl_adet={col_lfl_adet}, lfl_stok={col_lfl_stok}, lfl_kar={col_lfl_kar}")
    print(f"   haftalik_ciro={col_haftalik_ciro}, ty_birim_fiyat={col_ty_birim_fiyat}, ly_birim_fiyat={col_ly_birim_fiyat}")
    print(f"   ty_ciro={col_ty_ciro}, ty_adet={col_ty_adet}, ty_stok={col_ty_stok}")
    
    # Parse fonksiyonu
    def parse_val(val):
        if pd.isna(val):
            return 0
        if isinstance(val, str):
            val = val.replace('%', '').replace(',', '.').replace(' ', '').strip()
            try:
                return float(val)
            except:
                return 0
        try:
            return float(val)
        except:
            return 0
    
    def parse_pct(val):
        """Yüzde değeri parse et - ondalık ise 100 ile çarp"""
        v = parse_val(val)
        if -2 < v < 2 and v != 0:
            return v * 100
        return v
    
    # =====================================================================
    # FİLTRELEME FONKSİYONU - CEO TALEBİ
    # =====================================================================
    def grup_filtrelensin_mi(row_data: dict) -> tuple:
        """
        Grup filtrelenmeli mi kontrol et
        Returns: (filtrelensin_mi: bool, sebep: str)
        """
        ana = row_data.get('ana_grup', '').upper()
        ara = row_data.get('ara_grup', '').upper()
        alt = row_data.get('alt_grup', '').upper()
        lfl_ciro = row_data.get('lfl_ciro', 0)
        
        # 1. Kapsam dışı grup kontrolü
        if 'DELIST' in ana or 'DELIST' in ara or 'DELIST' in alt:
            return (True, f"Kapsam disi: {ana or ara or alt}")
        
        # 2. SEZON DIŞI kontrolü
        for sezon in SEZON_DISI_GRUPLAR:
            if sezon in ana or sezon in ara or sezon in alt:
                return (True, f"Sezon dışı grup: {ana or ara or alt}")
        
        # 3. LFL < %5 kontrolü
        if lfl_ciro < 5 and lfl_ciro > -999:  # -999 = veri yok demek
            return (True, f"LFL < %5: {lfl_ciro:.1f}%")
        
        return (False, "")
    
    # Satır verilerini çıkar
    def extract_row(row):
        # NaN değerleri boş string'e çevir
        def clean_str(val):
            if pd.isna(val) or str(val).lower() == 'nan':
                return ''
            return str(val).strip()

        result = {
            'ana_grup': clean_str(row.get(col_ana_grup, '')) if col_ana_grup else '',
            'ara_grup': clean_str(row.get(col_ara_grup, '')) if col_ara_grup else '',
            'alt_grup': clean_str(row.get(col_alt_grup, '')) if col_alt_grup else '',
            'ciro_achieved': parse_pct(row.get(col_ciro_achieved, 0)),
            'adet_achieved': parse_pct(row.get(col_adet_achieved, 0)),
            'kar_achieved': parse_pct(row.get(col_kar_achieved, 0)),
            'ty_cover': parse_val(row.get(col_ty_cover, 0)),
            'ly_cover': parse_val(row.get(col_ly_cover, 0)),
            'ty_marj': parse_pct(row.get(col_ty_marj, 0)),
            'ly_marj': parse_pct(row.get(col_ly_marj, 0)),
            'lfl_ciro': parse_pct(row.get(col_lfl_ciro, 0)),
            'lfl_adet': parse_pct(row.get(col_lfl_adet, 0)),
            'lfl_stok': parse_pct(row.get(col_lfl_stok, 0)),
            'lfl_kar': parse_pct(row.get(col_lfl_kar, 0)),
            'fiyat_artis': parse_pct(row.get(col_fiyat_artis, 0)),
            'haftalik_ciro': parse_pct(row.get(col_haftalik_ciro, 0)),
            'ty_birim_fiyat': parse_val(row.get(col_ty_birim_fiyat, 0)),
            'ly_birim_fiyat': parse_val(row.get(col_ly_birim_fiyat, 0)),
            # Mutlak değerler (pay hesabı için)
            'ty_ciro_abs': parse_val(row.get(col_ty_ciro, 0)) if col_ty_ciro else 0,
            'ty_kar_abs': parse_val(row.get(col_ty_kar, 0)) if col_ty_kar else 0,
            'ty_adet_abs': parse_val(row.get(col_ty_adet, 0)) if col_ty_adet else 0,
            'ty_stok_abs': parse_val(row.get(col_ty_stok, 0)) if col_ty_stok else 0,
            # Pay kolonları (eski format - doğrudan yüzde)
            'adet_pay': parse_pct(row.get(col_adet_pay, 0)) if col_adet_pay else 0,
            'stok_pay': parse_pct(row.get(col_stok_pay, 0)) if col_stok_pay else 0,
            'ciro_pay': parse_pct(row.get(col_ciro_pay, 0)) if col_ciro_pay else 0,
            'kar_pay': parse_pct(row.get(col_kar_pay, 0)) if col_kar_pay else 0,
        }
        return result
    
    # Toplam satırlarını filtrele
    def is_toplam(row_data):
        """Toplam satırı mı kontrol et"""
        ana = row_data['ana_grup'].lower()
        ara = row_data['ara_grup'].lower()
        if 'toplam' in ana or 'genel toplam' in ana:
            return True
        if 'toplam' in ara:
            return True
        return False
    
    def is_ana_grup_toplam(row_data):
        """Ana grup toplam satırı mı?
        Desteklenen formatlar:
        - Eski: ana dolu, ara+alt boş → toplam
        - CUBE Trading: 'Sofra İçecek Total' (MainGroupDesc + ' Total', SubGroupDesc boş)
        """
        ana = row_data['ana_grup'].strip()
        ara = row_data['ara_grup'].strip()
        alt = row_data['alt_grup'].strip()
        ana_lower = ana.lower()

        # Genel Toplam / Grand Total satırını hariç tut
        if ana_lower in ('genel toplam', 'toplam', 'grand total', 'total') or 'genel toplam' in ana_lower or 'grand total' in ana_lower:
            return False

        # CUBE Trading formatı: "Sofra İçecek Total" gibi - SubGroupDesc boş
        if ana_lower.endswith(' total') and ara == '' and alt == '':
            return True

        # Ana grup dolu, ara ve alt grup boş ise → Ana Grup Toplamı
        if ana != '' and ara == '' and alt == '':
            return True

        # Eski format: "Toplam SOFRA" gibi
        if ana.startswith('Toplam ') and ara == '' and alt == '':
            return True

        return False
    
    def is_ara_grup_toplam(row_data):
        """Ara grup toplam satırı mı?
        Yeni mantık: Alt grup BOŞ ise bu ara grup toplamıdır
        """
        ana = row_data['ana_grup'].strip()
        ara = row_data['ara_grup'].strip()
        alt = row_data['alt_grup'].strip()
        
        # Ana ve Ara dolu, Alt boş ise → Ara Grup Toplamı
        if ana != '' and ara != '' and alt == '':
            return True
        
        # Eski format: "Toplam ÇAY KAHVE" gibi
        if ara.startswith('Toplam ') and alt == '':
            return True
            
        return False
    
    def is_alt_grup_detay(row_data):
        """Alt grup detay satırı mı? (3 seviye de dolu)"""
        ana = row_data['ana_grup'].strip()
        ara = row_data['ara_grup'].strip()
        alt = row_data['alt_grup'].strip()
        return ana != '' and ara != '' and alt != ''
    
    # ====================================================================
    # VERİYİ SEVİYEYE GÖRE FİLTRELE + CEO FİLTRELERİ UYGULA
    # ====================================================================
    
    all_rows = [extract_row(row) for _, row in df.iterrows()]
    
    # Genel Toplam satırını bul
    genel_toplam = None
    for r in all_rows:
        ana_lower = r['ana_grup'].lower().strip()
        if ana_lower in ('genel toplam', 'toplam', 'grand total', 'total') or 'genel toplam' in ana_lower or 'grand total' in ana_lower:
            genel_toplam = r
            break
    
    # CUBE formatında pay hesapla (mutlak değerlerden)
    if genel_toplam and genel_toplam.get('ty_ciro_abs', 0) > 0:
        gt_ciro = genel_toplam['ty_ciro_abs']
        gt_kar = genel_toplam['ty_kar_abs'] if genel_toplam['ty_kar_abs'] > 0 else 1
        gt_adet = genel_toplam['ty_adet_abs'] if genel_toplam['ty_adet_abs'] > 0 else 1
        gt_stok = genel_toplam['ty_stok_abs'] if genel_toplam['ty_stok_abs'] > 0 else 1
        for r in all_rows:
            if r['ciro_pay'] == 0 and r['ty_ciro_abs'] > 0:
                r['ciro_pay'] = (r['ty_ciro_abs'] / gt_ciro) * 100
            if r['kar_pay'] == 0 and r['ty_kar_abs'] > 0:
                r['kar_pay'] = (r['ty_kar_abs'] / gt_kar) * 100
            if r['adet_pay'] == 0 and r['ty_adet_abs'] > 0:
                r['adet_pay'] = (r['ty_adet_abs'] / gt_adet) * 100
            if r['stok_pay'] == 0 and r['ty_stok_abs'] > 0:
                r['stok_pay'] = (r['ty_stok_abs'] / gt_stok) * 100

    # FİLTRELENEN GRUPLARI LOGLA
    filtrelenen_gruplar = []
    
    if ana_grup is None:
        # ŞİRKET ÖZETİ + ANA GRUPLAR
        # Ana grup toplamlarını bul ve filtrele
        ana_gruplar = []
        for r in all_rows:
            if is_ana_grup_toplam(r):
                # CEO filtresini uygula
                filtrelensin, sebep = grup_filtrelensin_mi(r)
                if filtrelensin:
                    filtrelenen_gruplar.append((r['ana_grup'], sebep))
                    continue  # Bu grubu atlama
                
                ad = r['ana_grup'].replace('Toplam ', '')
                # CUBE formatı: "Sofra İçecek Total" → "Sofra İçecek"
                if ad.endswith(' Total'):
                    ad = ad[:-6].strip()
                r['ad'] = ad
                ana_gruplar.append(r)
        
        ana_gruplar.sort(key=lambda x: x['ciro_pay'], reverse=True)
        
        # ===================================================================
        # 1. GRAND TOTAL - ŞİRKET TOPLAMI
        # ===================================================================
        sonuc.append("=" * 60)
        sonuc.append("📊 GRAND TOTAL - ŞİRKET TOPLAMI")
        sonuc.append("=" * 60 + "\n")

        if genel_toplam:
            gt = genel_toplam

            # Bütçe gerçekleşme (Adet, Tutar, Kar)
            sonuc.append("💰 BÜTÇE GERÇEKLEŞMESİ:")
            butce_ciro_emoji = "✅" if gt['ciro_achieved'] >= 0 else ("🔴" if gt['ciro_achieved'] < -15 else "⚠️")
            butce_adet_emoji = "✅" if gt['adet_achieved'] >= 0 else ("🔴" if gt['adet_achieved'] < -15 else "⚠️")
            butce_kar_emoji = "✅" if gt['kar_achieved'] >= 0 else ("🔴" if gt['kar_achieved'] < -15 else "⚠️")
            sonuc.append(f"   Adet Bütçe:  {butce_adet_emoji} %{100 + gt['adet_achieved']:.0f} gerçekleşme ({gt['adet_achieved']:+.1f}%)")
            sonuc.append(f"   Ciro Bütçe:  {butce_ciro_emoji} %{100 + gt['ciro_achieved']:.0f} gerçekleşme ({gt['ciro_achieved']:+.1f}%)")
            sonuc.append(f"   Kar Bütçe:   {butce_kar_emoji} %{100 + gt['kar_achieved']:.0f} gerçekleşme ({gt['kar_achieved']:+.1f}%)")

            # LFL değişimler
            sonuc.append("\n📈 LFL DEĞİŞİMLER (Birebir Mağaza):")
            lfl_stok_emoji = "🔴" if gt['lfl_stok'] > 10 else ("⚠️" if gt['lfl_stok'] > 5 else "✅")
            lfl_adet_emoji = "🔴" if gt['lfl_adet'] < -10 else ("⚠️" if gt['lfl_adet'] < 0 else "✅")
            lfl_ciro_emoji = "🔴" if gt['lfl_ciro'] < -10 else ("⚠️" if gt['lfl_ciro'] < 0 else "✅")
            lfl_kar_emoji = "🔴" if gt['lfl_kar'] < -10 else ("⚠️" if gt['lfl_kar'] < 0 else "✅")
            sonuc.append(f"   LFL Stok:    {lfl_stok_emoji} %{gt['lfl_stok']:+.1f}")
            sonuc.append(f"   LFL Adet:    {lfl_adet_emoji} %{gt['lfl_adet']:+.1f}")
            sonuc.append(f"   LFL Ciro:    {lfl_ciro_emoji} %{gt['lfl_ciro']:+.1f}")
            sonuc.append(f"   LFL Kar:     {lfl_kar_emoji} %{gt['lfl_kar']:+.1f}")

            # Haftalık ciro değişimi
            if gt['haftalik_ciro'] != 0:
                hw_emoji = "📈" if gt['haftalik_ciro'] > 0 else "📉"
                sonuc.append(f"\n📅 HAFTALIK CİRO DEĞİŞİMİ: {hw_emoji} %{gt['haftalik_ciro']:+.1f} (Bu Hafta vs Geçen Hafta)")

            # Birim fiyat analizi
            if gt['ty_birim_fiyat'] > 0 and gt['ly_birim_fiyat'] > 0:
                fiyat_degisim = ((gt['ty_birim_fiyat'] / gt['ly_birim_fiyat']) - 1) * 100
                fiyat_emoji = "📈" if fiyat_degisim > 0 else "📉"
                sonuc.append(f"\n💲 BİRİM FİYAT ANALİZİ:")
                sonuc.append(f"   TY Birim Fiyat: {gt['ty_birim_fiyat']:.2f}")
                sonuc.append(f"   LY Birim Fiyat: {gt['ly_birim_fiyat']:.2f}")
                sonuc.append(f"   Değişim: {fiyat_emoji} %{fiyat_degisim:+.1f}")

            # Cover
            cover_emoji = "🔴" if gt['ty_cover'] > 12 else ("⚠️" if gt['ty_cover'] > 10 else "✅")
            sonuc.append(f"\n📦 COVER: {cover_emoji} {gt['ty_cover']:.1f} hf (GY: {gt['ly_cover']:.1f})")

            # Marj
            marj_deg = gt['ty_marj'] - gt['ly_marj']
            marj_emoji = "🔴" if marj_deg < -3 else ("⚠️" if marj_deg < 0 else "✅")
            sonuc.append(f"💵 MARJ: {marj_emoji} %{gt['ty_marj']:.1f} (GY: %{gt['ly_marj']:.1f}, {marj_deg:+.1f} puan)")

        # ===================================================================
        # 2. ANA GRUPLAR TABLOSU
        # ===================================================================
        sonuc.append("\n" + "=" * 60)
        sonuc.append("🏆 ANA GRUPLAR PERFORMANSI")
        if filtrelenen_gruplar:
            sonuc.append(f"(🚫 {len(filtrelenen_gruplar)} grup filtrelendi: LFL<%5, Sezon disi vb.)")
        sonuc.append("=" * 60 + "\n")

        sonuc.append(f"{'Ana Grup':<22} {'Bütçe%':>7} {'LFL Stok':>9} {'LFL Adet':>9} {'LFL Ciro':>9} {'Cover':>6}")
        sonuc.append("-" * 75)

        for ag in ana_gruplar:
            ad = ag['ad'][:21]
            butce_str = f"{ag['ciro_achieved']:+.0f}%"
            lfl_stok_str = f"{ag['lfl_stok']:+.0f}%"
            lfl_adet_str = f"{ag['lfl_adet']:+.0f}%"
            lfl_ciro_str = f"{ag['lfl_ciro']:+.0f}%" if ag['lfl_ciro'] != 0 else "-"
            cover_str = f"{ag['ty_cover']:.1f}"
            sonuc.append(f"{ad:<22} {butce_str:>7} {lfl_stok_str:>9} {lfl_adet_str:>9} {lfl_ciro_str:>9} {cover_str:>6}")

        # ===================================================================
        # 3. DETAYLI ANA GRUP DEĞERLENDİRMESİ
        # ===================================================================
        sonuc.append("\n" + "=" * 60)
        sonuc.append("📊 DETAYLI ANA GRUP DEĞERLENDİRMESİ")
        sonuc.append("=" * 60)

        for ag in ana_gruplar:
            sorunlar = []
            guclu = []
            fiyat_deg = 0
            if ag['ty_birim_fiyat'] > 0 and ag['ly_birim_fiyat'] > 0:
                fiyat_deg = ((ag['ty_birim_fiyat'] / ag['ly_birim_fiyat']) - 1) * 100
            marj_deg = ag['ty_marj'] - ag['ly_marj']
            stok_ciro_oran = ag['stok_pay'] / ag['ciro_pay'] if ag['ciro_pay'] > 0 else 0

            # Sorun tespiti
            if ag['ciro_achieved'] < -10:
                sorunlar.append(f"Butce %{ag['ciro_achieved']:+.0f} - ciddi sapma, satis aksiyonu gerekli")
            elif ag['ciro_achieved'] < -5:
                sorunlar.append(f"Butce %{ag['ciro_achieved']:+.0f} - hafif geride, takip edilmeli")
            if ag['ty_cover'] > 14:
                sorunlar.append(f"Cover {ag['ty_cover']:.1f} hf - stok eritme/indirim plani gerekli")
            if ag['lfl_adet'] < -10:
                sorunlar.append(f"LFL adet %{ag['lfl_adet']:+.0f} - trafik/talep sorunu, musteri kaybediyor olabilir")
            if marj_deg < -3:
                sorunlar.append(f"Marj {marj_deg:+.1f} puan erimis - promosyon baskisi veya maliyet artisi")
            if stok_ciro_oran > 1.5:
                sorunlar.append(f"Stok/Ciro orani {stok_ciro_oran:.1f}x - fazla stok baglaniyor, eritme sart")
            if fiyat_deg > 0 and fiyat_deg < 30 and ag['ty_cover'] < 8:
                sorunlar.append(f"Fiyat artisi %{fiyat_deg:.0f} enflasyonun altinda, cover {ag['ty_cover']:.0f} hf dusuk - bosuna ciro birakiliyor, promolar haric fiyat artisini degerlendir")

            # Güçlü yön tespiti
            if ag['ciro_achieved'] > 10:
                guclu.append(f"Butce %{ag['ciro_achieved']:+.0f} gerceklesme, hedef asiliyor")
            if ag['lfl_ciro'] > 20:
                guclu.append(f"LFL ciro %{ag['lfl_ciro']:+.0f} guclu buyume")
            if marj_deg > 3:
                guclu.append(f"Marj +{marj_deg:.1f} puan iyilesme - fiyatlama stratejisi basarili")
            if ag['lfl_adet'] > 10:
                guclu.append(f"LFL adet %{ag['lfl_adet']:+.0f} - talep artiyor")
            if fiyat_deg > 30:
                guclu.append(f"Fiyat artisi %{fiyat_deg:.0f} enflasyon ustunde")

            if sorunlar or guclu:
                emoji = "🔴" if len(sorunlar) >= 2 else ("⚠️" if sorunlar else "✅")
                sonuc.append(f"\n{emoji} {ag['ad']} (Ciro Pay: %{ag['ciro_pay']:.1f}):")
                sonuc.append(f"   Butce: {ag['ciro_achieved']:+.1f}% | LFL Ciro: {ag['lfl_ciro']:+.1f}% | LFL Adet: {ag['lfl_adet']:+.1f}% | Cover: {ag['ty_cover']:.1f} hf")
                sonuc.append(f"   Marj: %{ag['ty_marj']:.1f} (GY: %{ag['ly_marj']:.1f}, {marj_deg:+.1f}p) | Stok/Ciro: {stok_ciro_oran:.1f}x")
                if fiyat_deg != 0:
                    sonuc.append(f"   Birim Fiyat: {ag['ty_birim_fiyat']:.0f} TL (GY: {ag['ly_birim_fiyat']:.0f}, %{fiyat_deg:+.0f})")
                for s in sorunlar:
                    sonuc.append(f"   ❌ {s}")
                for g in guclu:
                    sonuc.append(f"   ✅ {g}")

        # ===================================================================
        # SWOT ANALİZİ
        # ===================================================================
        sonuc.append("\n" + "=" * 60)
        sonuc.append("📋 SWOT ANALİZİ")
        sonuc.append("=" * 60)

        # STRENGTHS
        strengths = []
        weaknesses = []
        opportunities = []
        threats = []

        if genel_toplam:
            gt = genel_toplam
            gt_fiyat_deg = 0
            if gt['ty_birim_fiyat'] > 0 and gt['ly_birim_fiyat'] > 0:
                gt_fiyat_deg = ((gt['ty_birim_fiyat'] / gt['ly_birim_fiyat']) - 1) * 100
            gt_marj_deg = gt['ty_marj'] - gt['ly_marj']

            if gt['ciro_achieved'] >= -5:
                strengths.append(f"Ciro butcesi %{100+gt['ciro_achieved']:.0f} gerceklesme - hedefe yakin")
            if gt['kar_achieved'] > 5:
                strengths.append(f"Kar butcesi %{100+gt['kar_achieved']:.0f} gerceklesme - karlilik guclu")
            if gt['lfl_ciro'] > 15:
                strengths.append(f"LFL ciro %{gt['lfl_ciro']:+.0f} - organik buyume saglikli")
            if gt_marj_deg > 3:
                strengths.append(f"Marj +{gt_marj_deg:.1f} puan iyilesme - fiyatlama stratejisi basarili")
            if gt_fiyat_deg > 30:
                strengths.append(f"Birim fiyat artisi %{gt_fiyat_deg:.0f} - enflasyon ustu fiyatlama")
            if gt['ty_cover'] < gt['ly_cover']:
                strengths.append(f"Cover {gt['ty_cover']:.1f} hf (GY: {gt['ly_cover']:.1f}) - stok yonetimi iyilesti")

            # Güçlü ana grupları ekle
            guclu_gruplar = [ag for ag in ana_gruplar if ag['ciro_achieved'] > 10 and ag['ciro_pay'] > 3]
            if guclu_gruplar:
                isimler = ', '.join([ag['ad'] for ag in guclu_gruplar[:3]])
                strengths.append(f"Guclu ana gruplar: {isimler}")

            # WEAKNESSES
            if gt['adet_achieved'] < -10:
                weaknesses.append(f"Adet butcesi %{100+gt['adet_achieved']:.0f} - adet bazinda geride")
            if gt['lfl_adet'] < -5:
                weaknesses.append(f"LFL adet %{gt['lfl_adet']:+.0f} - musteri trafigi/talep dususu")

            zayif_gruplar = [ag for ag in ana_gruplar if ag['ciro_achieved'] < -10 and ag['ciro_pay'] > 3]
            if zayif_gruplar:
                for zg in zayif_gruplar:
                    weaknesses.append(f"{zg['ad']}: butce %{zg['ciro_achieved']:+.0f}, stok/ciro {zg['stok_pay']/zg['ciro_pay']:.1f}x" if zg['ciro_pay'] > 0 else f"{zg['ad']}: butce %{zg['ciro_achieved']:+.0f}")

            yuksek_cover = [ag for ag in ana_gruplar if ag['ty_cover'] > 14 and ag['ciro_pay'] > 2]
            if yuksek_cover:
                isimler = ', '.join([f"{ag['ad']} ({ag['ty_cover']:.0f}hf)" for ag in yuksek_cover])
                weaknesses.append(f"Yuksek cover gruplari: {isimler}")

            # OPPORTUNITIES
            if gt['lfl_ciro'] > 0 and gt['lfl_adet'] < 0:
                opportunities.append(f"Ciro artiyor ama adet dusustu - fiyat artisi ile telafi ediliyor, adet artisi icin kampanya firsati")
            if gt['haftalik_ciro'] > 5:
                opportunities.append(f"Haftalik ciro %{gt['haftalik_ciro']:+.1f} yukselis trendinde - momentum devam ettirilebilir")

            dusuk_cover = [ag for ag in ana_gruplar if ag['ty_cover'] < 8 and ag['ciro_pay'] > 3 and ag['lfl_ciro'] > 10]
            if dusuk_cover:
                for dc in dusuk_cover:
                    opportunities.append(f"{dc['ad']}: dusuk cover ({dc['ty_cover']:.0f}hf) ama guclu satis - sevkiyat artisi ile buyume firsati")

            fiyat_firsati = [ag for ag in ana_gruplar if ag['ty_birim_fiyat'] > 0 and ag['ly_birim_fiyat'] > 0 and ((ag['ty_birim_fiyat']/ag['ly_birim_fiyat'])-1)*100 < 25 and ag['ciro_pay'] > 3]
            if fiyat_firsati:
                for ff in fiyat_firsati[:2]:
                    ff_deg = ((ff['ty_birim_fiyat']/ff['ly_birim_fiyat'])-1)*100
                    opportunities.append(f"{ff['ad']}: fiyat artisi %{ff_deg:.0f} enflasyon altinda - fiyat artis potansiyeli var")

            # THREATS
            if gt['lfl_adet'] < -5:
                threats.append(f"Adet bazinda %{gt['lfl_adet']:+.0f} daralma - fiyat artisi ile maskeleniyor, surudurulebilirlik riski")
            if gt_fiyat_deg > 40:
                threats.append(f"Birim fiyat %{gt_fiyat_deg:.0f} artmis - musteri fiyat hassasiyeti artabilir, talep elastikiyeti riski")

            stok_fazlasi = [ag for ag in ana_gruplar if ag['ty_cover'] > 14 and ag['ciro_pay'] > 3]
            if stok_fazlasi:
                toplam_stok_pay = sum(ag['stok_pay'] for ag in stok_fazlasi)
                threats.append(f"Yuksek cover gruplari toplam %{toplam_stok_pay:.0f} stok payi - nakit akisi baskisi")

            marj_dusen = [ag for ag in ana_gruplar if (ag['ty_marj'] - ag['ly_marj']) < -3 and ag['ciro_pay'] > 3]
            if marj_dusen:
                isimler = ', '.join([ag['ad'] for ag in marj_dusen])
                threats.append(f"Marj eriyenler: {isimler} - karlilik baskisi")

        sonuc.append("\n💪 GUCLÜ YONLER (Strengths):")
        for s in strengths if strengths else ["   Veri yetersiz"]:
            sonuc.append(f"   + {s}")
        sonuc.append("\n⚠️ ZAYIF YONLER (Weaknesses):")
        for w in weaknesses if weaknesses else ["   Veri yetersiz"]:
            sonuc.append(f"   - {w}")
        sonuc.append("\n🎯 FIRSATLAR (Opportunities):")
        for o in opportunities if opportunities else ["   Veri yetersiz"]:
            sonuc.append(f"   > {o}")
        sonuc.append("\n🔥 TEHDİTLER (Threats):")
        for t in threats if threats else ["   Veri yetersiz"]:
            sonuc.append(f"   ! {t}")

        # ===================================================================
        # 4. TOP 3 ANA GRUP DETAY + EN BUYUK ANA GRUBUN TOP 2 SUBGROUP'U
        # ===================================================================
        if len(ana_gruplar) >= 1:
            top3 = ana_gruplar[:3]  # Zaten ciro_pay'e gore sirali
            sonuc.append("\n" + "=" * 60)
            sonuc.append("🔍 EN YUKSEK CİROLU 3 ANA GRUP DETAYI")
            sonuc.append("=" * 60)

            for i, ag in enumerate(top3, 1):
                sonuc.append(f"\n--- {i}. {ag['ad']} ---")
                sonuc.append(f"   Ciro Pay: %{ag['ciro_pay']:.1f} | Stok Pay: %{ag['stok_pay']:.1f} | Kar Pay: %{ag['kar_pay']:.1f}")
                sonuc.append(f"   Butce: {ag['ciro_achieved']:+.1f}% | LFL Ciro: {ag['lfl_ciro']:+.1f}% | LFL Adet: {ag['lfl_adet']:+.1f}%")
                sonuc.append(f"   Cover: {ag['ty_cover']:.1f} hf (GY: {ag['ly_cover']:.1f})")
                sonuc.append(f"   Marj: %{ag['ty_marj']:.1f} (GY: %{ag['ly_marj']:.1f}, {ag['ty_marj']-ag['ly_marj']:+.1f} puan)")
                if ag['ty_birim_fiyat'] > 0 and ag['ly_birim_fiyat'] > 0:
                    fiyat_deg = ((ag['ty_birim_fiyat'] / ag['ly_birim_fiyat']) - 1) * 100
                    sonuc.append(f"   Birim Fiyat: {ag['ty_birim_fiyat']:.2f} (GY: {ag['ly_birim_fiyat']:.2f}, %{fiyat_deg:+.1f})")
                if ag['haftalik_ciro'] != 0:
                    sonuc.append(f"   Haftalik Ciro Degisimi: %{ag['haftalik_ciro']:+.1f}")

            # En buyuk ana grubun top 2 SubGroup'u
            top1_ad = top3[0]['ad'].upper().strip()
            sub_gruplar = []
            for r in all_rows:
                r_ana = r['ana_grup'].upper().strip()
                ana_match = (r_ana == top1_ad or
                            top1_ad in r_ana or
                            r_ana.replace('TOPLAM ', '') == top1_ad or
                            r_ana.replace(' TOTAL', '') == top1_ad.replace(' TOTAL', ''))
                # 2 seviyeli: ara_grup dolu, alt_grup bos = ara grup toplami (SubGroup)
                # 3 seviyeli: alt_grup dolu = alt grup detayi
                if ana_match and r['ara_grup'] != '' and not is_ana_grup_toplam(r):
                    if is_two_level:
                        if is_ara_grup_toplam(r):
                            r['ad'] = r['ara_grup']
                            sub_gruplar.append(r)
                    else:
                        if r['alt_grup'] == '':  # ara grup toplami
                            r['ad'] = r['ara_grup'].replace('Toplam ', '')
                            sub_gruplar.append(r)

            if sub_gruplar:
                # Bütçe verisi boş olanları filtrele + delist içerenleri hariç tut
                sub_gruplar = [sg for sg in sub_gruplar
                               if sg['ciro_achieved'] != 0
                               and 'delist' not in sg['ara_grup'].lower()
                               and 'delist' not in sg.get('ad', '').lower()]
                sub_gruplar.sort(key=lambda x: x['ciro_pay'], reverse=True)
                top2_sub = sub_gruplar[:2]
                sonuc.append(f"\n   🔎 {top3[0]['ad']} - EN YUKSEK CİROLU 2 ALT GRUP:")
                for sg in top2_sub:
                    sg_marj_deg = sg['ty_marj'] - sg['ly_marj']
                    sonuc.append(f"      📌 {sg['ad']}:")
                    sonuc.append(f"         Ciro Pay: %{sg['ciro_pay']:.1f} | Butce: {sg['ciro_achieved']:+.1f}%")
                    sonuc.append(f"         LFL Ciro: {sg['lfl_ciro']:+.1f}% | LFL Adet: {sg['lfl_adet']:+.1f}% | LFL Stok: {sg['lfl_stok']:+.1f}%")
                    sonuc.append(f"         Cover: {sg['ty_cover']:.1f} hf (GY: {sg['ly_cover']:.1f}) | Marj: %{sg['ty_marj']:.1f} ({sg_marj_deg:+.1f}p)")
                    if sg['ty_birim_fiyat'] > 0 and sg['ly_birim_fiyat'] > 0:
                        sg_fiyat_deg = ((sg['ty_birim_fiyat'] / sg['ly_birim_fiyat']) - 1) * 100
                        sonuc.append(f"         Birim Fiyat: {sg['ty_birim_fiyat']:.0f} TL (GY: {sg['ly_birim_fiyat']:.0f}, %{sg_fiyat_deg:+.0f})")
                    if sg['haftalik_ciro'] != 0:
                        sonuc.append(f"         Haftalik Ciro: %{sg['haftalik_ciro']:+.1f}")
        
        # Filtrelenen grupları göster (delist hariç - bahsetme!)
        if filtrelenen_gruplar:
            gosterilecek = [(g, s) for g, s in filtrelenen_gruplar if 'delist' not in g.lower() and 'delist' not in s.lower()]
            if gosterilecek:
                sonuc.append(f"\n🚫 FİLTRELENEN GRUPLAR ({len(gosterilecek)} adet):")
                for grup, sebep in gosterilecek[:5]:
                    sonuc.append(f"   . {grup}: {sebep}")
                if len(gosterilecek) > 5:
                    sonuc.append(f"   ... ve {len(gosterilecek)-5} grup daha")
        
        sonuc.append(f"\n💡 Detay için: trading_analiz(ana_grup='GRUP_ADI')")
        
    elif ara_grup is None:
        # ANA GRUP DETAYI - ARA GRUPLARI GÖSTER VE FİLTRELE
        ana_grup_upper = ana_grup.upper().strip()
        
        ara_gruplar = []
        for r in all_rows:
            r_ana = r['ana_grup'].upper().strip()
            ana_match = (r_ana == ana_grup_upper or 
                        r_ana == f"TOPLAM {ana_grup_upper}" or
                        ana_grup_upper in r_ana or
                        r_ana.replace('TOPLAM ', '') == ana_grup_upper)
            
            if ana_match and is_ara_grup_toplam(r):
                # CEO filtresini uygula
                filtrelensin, sebep = grup_filtrelensin_mi(r)
                if filtrelensin:
                    filtrelenen_gruplar.append((r['ara_grup'], sebep))
                    continue
                
                r['ad'] = r['ara_grup'].replace('Toplam ', '')
                ara_gruplar.append(r)
        
        if not ara_gruplar:
            # Alt grupları dene
            for r in all_rows:
                r_ana = r['ana_grup'].upper().strip()
                ana_match = (r_ana == ana_grup_upper or 
                            ana_grup_upper in r_ana or
                            r_ana.replace('TOPLAM ', '') == ana_grup_upper)
                
                if ana_match and r['alt_grup'] != '' and not r['alt_grup'].startswith('Toplam'):
                    # CEO filtresini uygula
                    filtrelensin, sebep = grup_filtrelensin_mi(r)
                    if filtrelensin:
                        filtrelenen_gruplar.append((r['alt_grup'], sebep))
                        continue
                    
                    r['ad'] = r['alt_grup']
                    ara_gruplar.append(r)
            
            if ara_gruplar:
                ara_gruplar.sort(key=lambda x: x['ciro_pay'], reverse=True)
                
                sonuc.append("=" * 60)
                sonuc.append(f"📊 {ana_grup_upper} - ALT GRUP DETAYI")
                if filtrelenen_gruplar:
                    sonuc.append(f"(🚫 {len(filtrelenen_gruplar)} alt grup filtrelendi)")
                sonuc.append("=" * 60 + "\n")
                
                sonuc.append(f"{'Alt Grup':<28} {'Ciro%':>6} {'Adet%':>6} {'Stok%':>6} {'Kar%':>6} {'Cover':>6} {'LFL':>7}")
                sonuc.append("-" * 75)
                
                for ag in ara_gruplar[:15]:
                    ad = ag['ad'][:27]
                    cover_str = f"{ag['ty_cover']:.1f}"
                    lfl_str = f"{ag['lfl_ciro']:+.0f}%"
                    sonuc.append(f"{ad:<28} {ag['ciro_pay']:>5.1f}% {ag['adet_pay']:>5.1f}% {ag['stok_pay']:>5.1f}% {ag['kar_pay']:>5.1f}% {cover_str:>6} {lfl_str:>7}")
                
                return "\n".join(sonuc)
            
            return f"❌ '{ana_grup}' ana grubu bulunamadı."
        
        ara_gruplar.sort(key=lambda x: x['ciro_pay'], reverse=True)
        
        sonuc.append("=" * 60)
        sonuc.append(f"📊 {ana_grup_upper} - ARA GRUP DETAYI")
        if filtrelenen_gruplar:
            sonuc.append(f"(🚫 {len(filtrelenen_gruplar)} ara grup filtrelendi)")
        sonuc.append("=" * 60 + "\n")
        
        sonuc.append(f"{'Ara Grup':<28} {'Ciro%':>6} {'Adet%':>6} {'Stok%':>6} {'Kar%':>6} {'Cover':>6} {'LFL':>7}")
        sonuc.append("-" * 75)
        
        for ag in ara_gruplar:
            ad = ag['ad'][:27]
            cover_str = f"{ag['ty_cover']:.1f}"
            lfl_str = f"{ag['lfl_ciro']:+.0f}%"
            sonuc.append(f"{ad:<28} {ag['ciro_pay']:>5.1f}% {ag['adet_pay']:>5.1f}% {ag['stok_pay']:>5.1f}% {ag['kar_pay']:>5.1f}% {cover_str:>6} {lfl_str:>7}")
        
        # Stok/Ciro dengesizliği
        sonuc.append("\n" + "-" * 60)
        for ag in ara_gruplar:
            if ag['ciro_pay'] > 0:
                oran = ag['stok_pay'] / ag['ciro_pay']
                if oran > 1.3:
                    sonuc.append(f"⚠️ {ag['ad']}: Stok fazla (stok/ciro: {oran:.1f}x) → ERİTME")
                elif oran < 0.7:
                    sonuc.append(f"⚠️ {ag['ad']}: Stok az (stok/ciro: {oran:.1f}x) → SEVKİYAT")
        
        sonuc.append(f"\n💡 Detay için: trading_analiz(ana_grup='{ana_grup}', ara_grup='ARA_GRUP_ADI')")
        
    else:
        # ARA GRUP DETAYI - ALT GRUPLARI GÖSTER VE FİLTRELE
        ana_grup_upper = ana_grup.upper()
        ara_grup_upper = ara_grup.upper()
        
        alt_gruplar = []
        for r in all_rows:
            ana_match = r['ana_grup'].upper() == ana_grup_upper
            ara_match = r['ara_grup'].upper() == ara_grup_upper
            has_alt = r['alt_grup'] != '' and not r['alt_grup'].startswith('Toplam')
            
            if ana_match and ara_match and has_alt:
                # CEO filtresini uygula
                filtrelensin, sebep = grup_filtrelensin_mi(r)
                if filtrelensin:
                    filtrelenen_gruplar.append((r['alt_grup'], sebep))
                    continue
                
                r['ad'] = r['alt_grup']
                alt_gruplar.append(r)
        
        if not alt_gruplar:
            return f"❌ '{ana_grup} > {ara_grup}' altında ürün grubu bulunamadı."
        
        alt_gruplar.sort(key=lambda x: x['ciro_pay'], reverse=True)
        
        sonuc.append("=" * 60)
        sonuc.append(f"📊 {ana_grup_upper} > {ara_grup_upper} - MAL GRUBU DETAYI")
        if filtrelenen_gruplar:
            sonuc.append(f"(🚫 {len(filtrelenen_gruplar)} mal grubu filtrelendi)")
        sonuc.append("=" * 60 + "\n")
        
        sonuc.append(f"{'Mal Grubu':<24} {'Ciro%':>6} {'Adet%':>6} {'Stok%':>6} {'Cover':>6} {'LFL':>7} {'Bütçe':>7}")
        sonuc.append("-" * 75)
        
        for ag in alt_gruplar:
            ad = ag['ad'][:23]
            cover_str = f"{ag['ty_cover']:.1f}"
            lfl_str = f"{ag['lfl_ciro']:+.0f}%"
            butce_str = f"{ag['ciro_achieved']:+.0f}%"
            sonuc.append(f"{ad:<24} {ag['ciro_pay']:>5.1f}% {ag['adet_pay']:>5.1f}% {ag['stok_pay']:>5.1f}% {cover_str:>6} {lfl_str:>7} {butce_str:>7}")
        
        # En iyi ve en kötü performans
        sonuc.append("\n" + "-" * 60)
        en_iyi = max(alt_gruplar, key=lambda x: x['lfl_ciro'])
        en_kotu = min(alt_gruplar, key=lambda x: x['lfl_ciro'])
        sonuc.append(f"✅ En iyi: {en_iyi['ad']} (LFL: %{en_iyi['lfl_ciro']:+.0f})")
        sonuc.append(f"🔴 En kötü: {en_kotu['ad']} (LFL: %{en_kotu['lfl_ciro']:+.0f})")
    
    return "\n".join(sonuc)
    
def cover_analiz(kup: KupVeri, sayfa: str = None) -> str:
    """SC Tablosu cover grup analizi"""
    
    if len(kup.sc_sayfalari) == 0:
        return "❌ SC Tablosu yüklenmemiş."
    
    sonuc = []
    sonuc.append("=== COVER GRUP ANALİZİ ===\n")
    
    # Mevcut sayfaları göster
    sonuc.append(f"Mevcut sayfalar: {list(kup.sc_sayfalari.keys())}\n")
    
    # Sayfa seç
    if sayfa and sayfa in kup.sc_sayfalari:
        df = kup.sc_sayfalari[sayfa]
        sonuc.append(f"Seçili sayfa: {sayfa}\n")
    else:
        # İlk uygun sayfayı bul
        for s in ['LW-TW Kategori Klasman Analiz', 'LW-TW Cover Analiz', 'Cover']:
            if s in kup.sc_sayfalari:
                df = kup.sc_sayfalari[s]
                sonuc.append(f"Seçili sayfa: {s}\n")
                break
        else:
            # İlk sayfayı al
            first_key = list(kup.sc_sayfalari.keys())[0]
            df = kup.sc_sayfalari[first_key]
            sonuc.append(f"Seçili sayfa: {first_key}\n")
    
    sonuc.append(f"Kolonlar: {list(df.columns)[:15]}...")
    sonuc.append(f"Satır sayısı: {len(df)}\n")
    
    # İlk 20 satırı göster
    sonuc.append("--- İlk 20 Satır ---")
    for i, row in df.head(20).iterrows():
        row_str = " | ".join([f"{str(v)[:15]}" for v in row.values[:8]])
        sonuc.append(row_str)
    
    # Cover grup analizi yap (eğer cover kolonu varsa)
    cover_kol = None
    for kol in df.columns:
        if 'cover' in str(kol).lower():
            cover_kol = kol
            break
    
    if cover_kol:
        sonuc.append(f"\n--- Cover Dağılımı ({cover_kol}) ---")
        try:
            cover_dist = df[cover_kol].value_counts().head(10)
            for val, count in cover_dist.items():
                sonuc.append(f"  {val}: {count} satır")
        except:
            pass
    
    return "\n".join(sonuc)


def cover_diagram_analiz(kup: KupVeri, alt_grup: str = None, magaza: str = None) -> str:
    """
    Cover Diagram analizi - Mağaza×AltGrup cover analizi
    
    Kolonlar: Alt Grup, StoreName, Mağaza Sayısı, TY Back Cover, 
              TY Avg Store Stock Unit, TY Sales Unit, TY Sales Value TRY,
              Toplam Sipariş, LFL Stok Değişim, LFL Satış Değişim
    """
    
    if len(kup.cover_diagram) == 0:
        return "❌ Cover Diagram yüklenmemiş."
    
    df = kup.cover_diagram.copy()
    kolonlar = list(df.columns)
    
    sonuc = []
    sonuc.append("=" * 60)
    sonuc.append("📊 COVER DİAGRAM ANALİZİ")
    sonuc.append("=" * 60 + "\n")
    
    # Kolon mapping
    def find_col(keywords):
        for kol in kolonlar:
            kol_lower = str(kol).lower()
            if all(k in kol_lower for k in keywords):
                return kol
        return None
    
    col_alt_grup = find_col(['alt', 'grup']) or find_col(['grup'])
    col_magaza = find_col(['store']) or find_col(['mağaza'])

    # TY ve LY Cover kolonları (Excel'den direkt okunacak, hesaplama YOK)
    col_ty_cover = find_col(['ty', 'store', 'back', 'cover']) or find_col(['ty', 'back', 'cover']) or find_col(['ty', 'cover'])
    col_ly_cover = find_col(['ly', 'store', 'back', 'cover']) or find_col(['ly', 'back', 'cover']) or find_col(['ly', 'cover'])
    col_cover = col_ty_cover  # Ana cover olarak TY kullan

    # Stok kolonları - daha esnek arama
    col_stok = find_col(['stock', 'unit']) or find_col(['stok', 'adet']) or find_col(['avg', 'stock']) or find_col(['stok'])

    # Satış kolonları
    col_satis_adet = find_col(['sales', 'unit']) or find_col(['satış', 'adet']) or find_col(['satis', 'adet'])
    col_satis_tutar = find_col(['sales', 'value']) or find_col(['satış', 'tutar']) or find_col(['sales', 'try'])

    col_siparis = find_col(['sipariş']) or find_col(['toplam', 'sip'])
    col_lfl_stok = find_col(['lfl', 'stok']) or find_col(['stok', 'değişim'])
    col_lfl_satis = find_col(['lfl', 'satış']) or find_col(['satış', 'değişim']) or find_col(['lfl', 'sales'])
    col_magaza_sayisi = find_col(['mağaza', 'sayı']) or find_col(['store', 'count']) or find_col(['mağaza sayısı'])

    print(f"Cover Diagram TÜM kolonlar: {kolonlar}")
    print(f"Bulunan: ty_cover={col_ty_cover}, ly_cover={col_ly_cover}, stok={col_stok}, satis_adet={col_satis_adet}, satis_tutar={col_satis_tutar}, magaza_sayisi={col_magaza_sayisi}")
    
    # Filtrele
    if alt_grup:
        df = df[df[col_alt_grup].astype(str).str.upper().str.contains(alt_grup.upper())]
        sonuc.append(f"📁 Alt Grup Filtresi: {alt_grup}\n")
    
    if magaza:
        df = df[df[col_magaza].astype(str).str.upper().str.contains(magaza.upper())]
        sonuc.append(f"🏪 Mağaza Filtresi: {magaza}\n")
    
    if len(df) == 0:
        return "❌ Filtreye uygun veri bulunamadı."
    
    # Parse fonksiyonu
    def parse_val(val):
        if pd.isna(val):
            return 0
        try:
            return float(str(val).replace('%', '').replace(',', '.').strip())
        except:
            return 0
    
    # ÖZET ANALİZ
    sonuc.append(f"📊 GENEL ÖZET ({len(df)} satır)")
    sonuc.append("-" * 50)

    # TY Cover (Bu Yıl) - Excel'den direkt okunuyor
    if col_ty_cover:
        df['_cover'] = df[col_ty_cover].apply(parse_val)
        avg_ty_cover = df['_cover'].mean()
        cover_yuksek = len(df[df['_cover'] > 12])
        cover_dusuk = len(df[df['_cover'] < 4])
        sonuc.append(f"   TY Cover Ortalama: {avg_ty_cover:.1f} hafta")
        sonuc.append(f"   🔴 Cover > 12 hafta: {cover_yuksek} satır")
        sonuc.append(f"   ⚠️ Cover < 4 hafta: {cover_dusuk} satır")

    # LY Cover (Geçen Yıl) - karşılaştırma için
    if col_ly_cover:
        df['_ly_cover'] = df[col_ly_cover].apply(parse_val)
        avg_ly_cover = df['_ly_cover'].mean()
        if col_ty_cover:
            cover_degisim = avg_ty_cover - avg_ly_cover
            if cover_degisim > 2:
                sonuc.append(f"   ⚠️ LY Cover: {avg_ly_cover:.1f} hf → Cover {cover_degisim:.1f} hf ARTTI (stok yavaşladı)")
            elif cover_degisim < -2:
                sonuc.append(f"   ✅ LY Cover: {avg_ly_cover:.1f} hf → Cover {abs(cover_degisim):.1f} hf AZALDI (stok hızlandı)")
            else:
                sonuc.append(f"   LY Cover: {avg_ly_cover:.1f} hf (stabil)")
    
    if col_lfl_satis:
        df['_lfl_satis'] = df[col_lfl_satis].apply(parse_val)
        avg_lfl = df['_lfl_satis'].mean()
        lfl_neg = len(df[df['_lfl_satis'] < -20])
        sonuc.append(f"   LFL Satış Ort: %{avg_lfl:+.1f}")
        sonuc.append(f"   🔴 LFL < -%20: {lfl_neg} satır")
    
    # Satış ve stok kolonlarını parse et
    if col_stok:
        df['_avg_stok'] = df[col_stok].apply(parse_val)
    if col_satis_adet:
        df['_satis_adet'] = df[col_satis_adet].apply(parse_val)
    if col_satis_tutar:
        df['_satis_tutar'] = df[col_satis_tutar].apply(parse_val)
    if col_magaza_sayisi:
        df['_magaza_sayisi'] = df[col_magaza_sayisi].apply(parse_val)

    # Toplam stok = Ortalama stok × Mağaza sayısı (eğer avg stok kolonuysa)
    if '_avg_stok' in df.columns:
        if '_magaza_sayisi' in df.columns:
            df['_stok'] = df['_avg_stok'] * df['_magaza_sayisi']
            print(f"Toplam stok hesaplandı: avg_stok * magaza_sayisi")
        else:
            df['_stok'] = df['_avg_stok']
            print(f"Stok direkt kullanıldı (mağaza sayısı yok)")

    # =========================================
    # KRİTİK ALT GRUPLAR (Cover > 30 hafta)
    # =========================================
    if col_alt_grup and '_cover' in df.columns and not alt_grup:
        # Önce toplam ciroyu hesapla
        toplam_ciro = df['_satis_tutar'].sum() if '_satis_tutar' in df.columns else 1

        # Alt grup bazında grupla
        agg_dict = {'_cover': 'mean'}
        if '_stok' in df.columns:
            agg_dict['_stok'] = 'sum'
        if '_satis_adet' in df.columns:
            agg_dict['_satis_adet'] = 'sum'
        if '_satis_tutar' in df.columns:
            agg_dict['_satis_tutar'] = 'sum'

        grup_ozet = df.groupby(col_alt_grup).agg(agg_dict)

        # Ciro payı hesapla
        if '_satis_tutar' in grup_ozet.columns:
            grup_ozet['_ciro_pay'] = grup_ozet['_satis_tutar'] / toplam_ciro * 100

        # Cover > 30 ve ciro payı > %0.1 olanları filtrele
        kritik_gruplar = grup_ozet[
            (grup_ozet['_cover'] > 30) &
            (grup_ozet.get('_ciro_pay', pd.Series([100]*len(grup_ozet))) > 0.1)
        ].sort_values('_cover', ascending=False)

        if len(kritik_gruplar) > 0:
            sonuc.append(f"\n🚨 KRİTİK ALT GRUPLAR (Cover > 30 hafta, Ciro Payı > %0.1)")
            sonuc.append("-" * 90)
            sonuc.append(f"{'Alt Grup':<25} {'Cover(hf)':>10} {'Stok Adet':>12} {'Satış Adet':>12} {'Ciro Payı':>10} {'Aksiyon':<15}")
            sonuc.append("-" * 90)

            for idx, row in kritik_gruplar.head(10).iterrows():
                grup_adi = str(idx)[:24]
                cover = row['_cover']
                stok = row.get('_stok', 0)
                satis = row.get('_satis_adet', 0)
                ciro_pay = row.get('_ciro_pay', 0)

                # Aksiyon önerisi
                if cover > 50:
                    aksiyon = "Acil eritme!"
                elif cover > 40:
                    aksiyon = "%30 indirim"
                else:
                    aksiyon = "%20 indirim"

                sonuc.append(f"{grup_adi:<25} {cover:>8.0f}hf {stok:>11,.0f} {satis:>11,.0f} {ciro_pay:>8.1f}% {aksiyon:<15}")

            sonuc.append(f"\n⚡ Bu {len(kritik_gruplar)} alt grup toplam stoğun önemli bir kısmını bağlıyor - indirim kampanyası planla!")
        else:
            sonuc.append(f"\n✅ Cover > 30 hafta olan kritik alt grup yok.")

    # ALT GRUP BAZINDA ÖZET (Tümü)
    if col_alt_grup and not alt_grup:
        sonuc.append(f"\n📁 TÜM ALT GRUPLAR - COVER SIRALI (Top 15)")
        sonuc.append("-" * 90)

        # Aggregation dictionary - tüm metrikleri topla
        agg_dict_all = {}
        if '_cover' in df.columns:
            agg_dict_all['_cover'] = 'mean'
        if '_stok' in df.columns:
            agg_dict_all['_stok'] = 'sum'
        if '_satis_adet' in df.columns:
            agg_dict_all['_satis_adet'] = 'sum'
        if '_satis_tutar' in df.columns:
            agg_dict_all['_satis_tutar'] = 'sum'

        # Eğer hiçbir kolon yoksa, count yap
        if not agg_dict_all:
            agg_dict_all['_cover'] = 'count'

        grup_ozet_all = df.groupby(col_alt_grup).agg(agg_dict_all).sort_values('_cover', ascending=False).head(15)

        sonuc.append(f"{'Alt Grup':<28} {'Cover(hf)':>10} {'Stok Adet':>12} {'Satış Adet':>12} {'Aksiyon':<15}")
        sonuc.append("-" * 90)
        for idx, row in grup_ozet_all.iterrows():
            cover = row.get('_cover', 0)
            stok = row.get('_stok', 0)
            satis = row.get('_satis_adet', 0)

            # Aksiyon önerisi
            if cover > 50:
                aksiyon = "Acil eritme"
            elif cover > 30:
                aksiyon = "%30 indirim"
            elif cover > 12:
                aksiyon = "%20 indirim"
            else:
                aksiyon = "Normal"

            cover_emoji = "🔴" if cover > 30 else ("⚠️" if cover > 12 else "")
            sonuc.append(f"{str(idx)[:27]:<28} {cover:>8.1f}hf {stok:>11,.0f} {satis:>11,.0f} {aksiyon:<15} {cover_emoji}")
    
    # MAĞAZA BAZINDA ÖZET
    if col_magaza and not magaza:
        sonuc.append(f"\n🏪 MAĞAZA BAZINDA COVER (En Yüksek 10)")
        sonuc.append("-" * 50)
        
        mag_ozet = df.groupby(col_magaza).agg({
            '_cover': 'mean'
        }).sort_values('_cover', ascending=False).head(10)
        
        for idx, row in mag_ozet.iterrows():
            cover_emoji = "🔴" if row['_cover'] > 12 else ""
            sonuc.append(f"   {str(idx)[:30]}: {row['_cover']:.1f}hf {cover_emoji}")
    
    return "\n".join(sonuc)


def kapasite_analiz(kup: KupVeri, magaza: str = None) -> str:
    """
    Kapasite-Performans analizi - Mağaza doluluk ve performans
    DETAYLI ANALİZ: Doluluk aralıkları, stok/satış adetleri, en dolu/boş mağazalar
    """
    
    if len(kup.kapasite) == 0:
        return "❌ Kapasite raporu yüklenmemiş."
    
    df = kup.kapasite.copy()
    kolonlar = list(df.columns)
    
    sonuc = []
    sonuc.append("=" * 70)
    sonuc.append("📦 MAĞAZA KAPASİTE VE PERFORMANS ANALİZİ")
    sonuc.append("=" * 70 + "\n")
    
    # Kolon mapping - daha esnek
    def find_col(keywords):
        for kol in kolonlar:
            kol_lower = str(kol).lower().replace('_', ' ').replace('#', '')
            if all(k in kol_lower for k in keywords):
                return kol
        return None
    
    col_magaza = find_col(['storename']) or find_col(['store name']) or find_col(['mağaza ad']) or find_col(['mağaza']) or kolonlar[0]
    col_karli_hizli = find_col(['karlı']) or find_col(['karli']) or find_col(['hızlı']) or find_col(['metrik'])
    col_kapasite_dm3 = find_col(['store', 'capacity', 'dm3']) or find_col(['capacity', 'dm3']) or find_col(['kapasite'])
    col_fiili_doluluk = find_col(['fiili', 'doluluk'])
    col_nihai_doluluk = find_col(['nihai', 'doluluk'])
    col_cover = find_col(['store', 'cover']) or find_col(['cover'])
    col_stok_adet = find_col(['avg', 'store', 'stock', 'unit']) or find_col(['stok', 'adet'])
    col_satis_adet = find_col(['sales', 'unit']) or find_col(['satış', 'adet'])
    col_satis_tutar = find_col(['sales', 'value']) or find_col(['satış', 'tutar'])
    col_lfl_stok = find_col(['lfl', 'stok', 'adet']) or find_col(['lfl', 'avg', 'store', 'stock'])
    col_lfl_satis_adet = find_col(['lfl', 'satış', 'adet']) or find_col(['lfl', 'sales', 'unit'])
    col_lfl_satis_tutar = find_col(['lfl', 'satış', 'tutar']) or find_col(['lfl', 'sales', 'value'])
    col_kar_marj = find_col(['kar', 'marj']) or find_col(['marj'])
    # YENİ: Doluluk hesaplaması için EOP Store Stock Dm3 kolonu
    col_eop_stok_dm3 = find_col(['eop', 'ty', 'store', 'stock', 'dm3']) or find_col(['eop', 'store', 'stock', 'dm3']) or find_col(['store', 'stock', 'dm3'])

    print(f"Kapasite kolonları bulundu: magaza={col_magaza}, doluluk={col_fiili_doluluk}, cover={col_cover}, stok={col_stok_adet}, kapasite_dm3={col_kapasite_dm3}, eop_stok_dm3={col_eop_stok_dm3}")
    
    # Filtrele
    if magaza:
        df = df[df[col_magaza].astype(str).str.upper().str.contains(magaza.upper())]
        sonuc.append(f"🏪 Mağaza Filtresi: {magaza}\n")
    
    if len(df) == 0:
        return "❌ Filtreye uygun mağaza bulunamadı."
    
    # Parse fonksiyonları
    def parse_val(val):
        if pd.isna(val):
            return 0
        try:
            return float(str(val).replace('%', '').replace(',', '.').strip())
        except:
            return 0
    
    def parse_pct(val):
        v = parse_val(val)
        if -2 < v < 2 and v != 0:
            return v * 100
        return v
    
    # Kolonları parse et
    # YENİ DOLULUK HESAPLAMASI: EOP TY Store Stock Dm3 / Store Capacity dm3 * 100
    if col_eop_stok_dm3 and col_kapasite_dm3:
        df['_eop_stok_dm3'] = df[col_eop_stok_dm3].apply(parse_val)
        df['_kapasite_dm3'] = df[col_kapasite_dm3].apply(parse_val)
        # Doluluk = (Stok Dm3 / Kapasite Dm3) * 100
        df['_fiili'] = df.apply(
            lambda row: (row['_eop_stok_dm3'] / row['_kapasite_dm3'] * 100) if row['_kapasite_dm3'] > 0 else 0,
            axis=1
        )
        print(f"   ✅ Doluluk HESAPLANDI: EOP Store Stock Dm3 / Store Capacity dm3")
    elif col_fiili_doluluk:
        # Fallback: Eski Fiili Doluluk kolonunu kullan
        df['_fiili'] = df[col_fiili_doluluk].apply(parse_pct)
        print(f"   ⚠️ Doluluk: Fiili Doluluk kolonu kullanıldı (EOP/Kapasite kolonları bulunamadı)")

    if col_cover:
        df['_cover'] = df[col_cover].apply(parse_val)
    if col_stok_adet:
        df['_stok_adet'] = df[col_stok_adet].apply(parse_val)
    if col_satis_adet:
        df['_satis_adet'] = df[col_satis_adet].apply(parse_val)
    if col_satis_tutar:
        df['_satis_tutar'] = df[col_satis_tutar].apply(parse_val)
    if col_lfl_satis_tutar:
        df['_lfl_satis'] = df[col_lfl_satis_tutar].apply(parse_pct)
    if col_kar_marj:
        df['_marj'] = df[col_kar_marj].apply(parse_pct)
    
    # =========================================
    # 1. GENEL ÖZET
    # =========================================
    toplam_magaza = len(df)
    sonuc.append(f"📊 GENEL ÖZET")
    sonuc.append("-" * 60)
    sonuc.append(f"   Toplam Mağaza Sayısı: {toplam_magaza}")
    
    if '_fiili' in df.columns:
        avg_doluluk = df['_fiili'].mean()
        sonuc.append(f"   Ortalama Doluluk: %{avg_doluluk:.1f}")
    
    if '_cover' in df.columns:
        avg_cover = df['_cover'].mean()
        sonuc.append(f"   Ortalama Cover: {avg_cover:.1f} hafta")
    
    if '_stok_adet' in df.columns:
        toplam_stok = df['_stok_adet'].sum()
        avg_stok = df['_stok_adet'].mean()
        sonuc.append(f"   Toplam Stok: {toplam_stok:,.0f} adet")
        sonuc.append(f"   Mağaza Başı Ort. Stok: {avg_stok:,.0f} adet")
    
    if '_satis_adet' in df.columns:
        toplam_satis = df['_satis_adet'].sum()
        avg_satis = df['_satis_adet'].mean()
        sonuc.append(f"   Toplam Satış: {toplam_satis:,.0f} adet")
        sonuc.append(f"   Mağaza Başı Ort. Satış: {avg_satis:,.0f} adet")
    
    if '_satis_tutar' in df.columns:
        toplam_ciro = df['_satis_tutar'].sum()
        avg_ciro = df['_satis_tutar'].mean()
        sonuc.append(f"   Toplam Ciro: {toplam_ciro/1e6:,.1f}M TL")
        sonuc.append(f"   Mağaza Başı Ort. Ciro: {avg_ciro/1e3:,.0f}K TL")
    
    if '_marj' in df.columns:
        avg_marj = df['_marj'].mean()
        sonuc.append(f"   Ortalama Marj: %{avg_marj:.1f}")
    
    # =========================================
    # 2. DOLULUK ARALIKLARI DAĞILIMI (YENİ EŞİKLER)
    # =========================================
    if '_fiili' in df.columns:
        sonuc.append(f"\n📊 DOLULUK ARALIKLARI DAĞILIMI")
        sonuc.append("-" * 70)

        # Yeni aralıklar (Cover'dan bağımsız genel dağılım)
        araliklar = [
            (110, 999, "🔴 >%110 (ÇOK DOLU)", "cok_dolu"),
            (95, 110, "✅ %95-109 (OPTİMAL)", "optimal"),
            (80, 95, "⚠️ %80-94 (BOŞ)", "bos"),
            (0, 80, "🔴 <%80 (AŞIRI BOŞ)", "asiri_bos")
        ]

        sonuc.append(f"{'Doluluk Aralığı':<25} {'Mağaza':>8} {'%Dağılım':>10} {'Stok%':>10} {'Cover':>8}")
        sonuc.append("-" * 70)

        toplam_stok_all = df['_stok_adet'].sum() if '_stok_adet' in df.columns else 1

        for alt, ust, label, _ in araliklar:
            mask = (df['_fiili'] >= alt) & (df['_fiili'] < ust)
            subset = df[mask]
            mag_sayi = len(subset)
            mag_pct = mag_sayi / toplam_magaza * 100

            if '_stok_adet' in df.columns and toplam_stok_all > 0:
                stok_pct = subset['_stok_adet'].sum() / toplam_stok_all * 100
            else:
                stok_pct = 0

            if '_cover' in df.columns and len(subset) > 0:
                cover_avg = subset['_cover'].mean()
            else:
                cover_avg = 0

            sonuc.append(f"{label:<25} {mag_sayi:>8} {mag_pct:>9.1f}% {stok_pct:>9.1f}% {cover_avg:>7.1f}hf")

    # =========================================
    # 2.1 COVER BAZLI MAĞAZA DURUM ANALİZİ
    # =========================================
    if '_fiili' in df.columns and '_cover' in df.columns:
        sonuc.append(f"\n📊 COVER BAZLI MAĞAZA DURUM ANALİZİ")
        sonuc.append("-" * 90)
        sonuc.append("Cover ≤12 hf: Hızlı satış - doluluk yüksek olmalı")
        sonuc.append("Cover >12 hf: Yavaş satış - doluluk düşük olabilir")
        sonuc.append("-" * 90)

        # Her mağaza için cover bazlı durum belirle
        def durum_belirle(row):
            doluluk = row.get('_fiili', 0)
            cover = row.get('_cover', 0)

            if cover <= 12:  # Hızlı satış
                if doluluk >= 110:
                    return ("✅ Normal", "normal", 1)
                elif doluluk >= 95:
                    return ("⚠️ Dikkat", "dikkat", 2)
                elif doluluk >= 80:
                    return ("🔴 BOŞ - Acil Müdahale", "acil", 3)
                else:
                    return ("🚨 AŞIRI BOŞ - Yakın Takip", "kritik", 4)
            else:  # Yavaş satış (cover > 12)
                if doluluk >= 110:
                    return ("⚠️ Dolu", "dolu", 2)
                elif doluluk >= 95:
                    return ("✅ Optimal", "optimal", 1)
                elif doluluk >= 80:
                    return ("⚠️ BOŞ - Dikkat", "dikkat", 2)
                else:
                    return ("🔴 AŞIRI BOŞ", "asiri_bos", 3)

        df['_durum'], df['_durum_kod'], df['_oncelik'] = zip(*df.apply(durum_belirle, axis=1))

        # Cover gruplarına göre özet
        hizli_satis = df[df['_cover'] <= 12]
        yavas_satis = df[df['_cover'] > 12]

        sonuc.append(f"\n🚀 HIZLI SATIŞ MAĞAZALARI (Cover ≤12 hf): {len(hizli_satis)} mağaza")
        if len(hizli_satis) > 0:
            for durum in ["✅ Normal", "⚠️ Dikkat", "🔴 BOŞ - Acil Müdahale", "🚨 AŞIRI BOŞ - Yakın Takip"]:
                sayi = len(hizli_satis[hizli_satis['_durum'] == durum])
                if sayi > 0:
                    sonuc.append(f"   {durum}: {sayi} mağaza")

        sonuc.append(f"\n🐢 YAVAŞ SATIŞ MAĞAZALARI (Cover >12 hf): {len(yavas_satis)} mağaza")
        if len(yavas_satis) > 0:
            for durum in ["⚠️ Dolu", "✅ Optimal", "⚠️ BOŞ - Dikkat", "🔴 AŞIRI BOŞ"]:
                sayi = len(yavas_satis[yavas_satis['_durum'] == durum])
                if sayi > 0:
                    sonuc.append(f"   {durum}: {sayi} mağaza")
    
    # =========================================
    # 3. KRİTİK MAĞAZALAR - HIZLI SATIŞ (Cover ≤12)
    # =========================================
    if '_fiili' in df.columns and '_cover' in df.columns:
        # Hızlı satış yapan ama boş olan mağazalar (ACİL!)
        hizli_ve_bos = df[(df['_cover'] <= 12) & (df['_fiili'] < 95)].copy()

        if len(hizli_ve_bos) > 0:
            sonuc.append(f"\n🚨 ACİL MÜDAHALE GEREKLİ - HIZLI SATIŞ AMA BOŞ ({len(hizli_ve_bos)} mağaza)")
            sonuc.append("Cover ≤12 hf olduğu için hızlı satıyor ama doluluk düşük - stok yetersiz!")
            sonuc.append("-" * 95)
            sonuc.append(f"{'Mağaza':<30} {'Doluluk':>10} {'Cover':>8} {'Stok':>12} {'Satış':>12} {'Durum':<20}")
            sonuc.append("-" * 95)

            # Önceliğe göre sırala (en kritik üstte)
            hizli_ve_bos = hizli_ve_bos.sort_values('_fiili', ascending=True)

            for _, row in hizli_ve_bos.head(10).iterrows():
                mag = str(row[col_magaza])[:29]
                doluluk = row.get('_fiili', 0)
                cover = row.get('_cover', 0)
                stok = row.get('_stok_adet', 0)
                satis = row.get('_satis_adet', 0)
                durum = row.get('_durum', '')
                sonuc.append(f"{mag:<30} %{doluluk:>8.0f} {cover:>7.1f}hf {stok:>11,.0f} {satis:>11,.0f} {durum:<20}")

            sonuc.append(f"\n⚡ AKSİYON: Bu mağazalara acil sevkiyat planla! Satış kaçırılıyor.")

    # =========================================
    # 4. KRİTİK MAĞAZALAR - YAVAŞ SATIŞ (Cover >12)
    # =========================================
    if '_fiili' in df.columns and '_cover' in df.columns:
        # Yavaş satış yapan ve çok dolu mağazalar (stok sorunu)
        yavas_ve_dolu = df[(df['_cover'] > 12) & (df['_fiili'] >= 110)].copy()

        if len(yavas_ve_dolu) > 0:
            sonuc.append(f"\n⚠️ STOK FAZLASI RİSKİ - YAVAŞ SATIŞ AMA DOLU ({len(yavas_ve_dolu)} mağaza)")
            sonuc.append("Cover >12 hf olduğu için yavaş satıyor ama doluluk yüksek - stok eritilmeli!")
            sonuc.append("-" * 95)
            sonuc.append(f"{'Mağaza':<30} {'Doluluk':>10} {'Cover':>8} {'Stok':>12} {'Satış':>12} {'Durum':<20}")
            sonuc.append("-" * 95)

            # En dolu olanlar üstte
            yavas_ve_dolu = yavas_ve_dolu.sort_values('_fiili', ascending=False)

            for _, row in yavas_ve_dolu.head(10).iterrows():
                mag = str(row[col_magaza])[:29]
                doluluk = row.get('_fiili', 0)
                cover = row.get('_cover', 0)
                stok = row.get('_stok_adet', 0)
                satis = row.get('_satis_adet', 0)
                durum = row.get('_durum', '')
                sonuc.append(f"{mag:<30} %{doluluk:>8.0f} {cover:>7.1f}hf {stok:>11,.0f} {satis:>11,.0f} {durum:<20}")

            sonuc.append(f"\n💡 AKSİYON: Bu mağazalarda indirim/promosyon veya stok transferi değerlendir.")

    # =========================================
    # 5. EN BOŞ MAĞAZALAR (Genel - Cover'dan bağımsız)
    # =========================================
    if '_fiili' in df.columns:
        en_bos = df.nsmallest(5, '_fiili')
        sonuc.append(f"\n🔴 EN BOŞ 5 MAĞAZA (Ürün Eksikliği)")
        sonuc.append("-" * 95)
        sonuc.append(f"{'Mağaza':<30} {'Doluluk':>10} {'Cover':>8} {'Stok':>12} {'Satış':>12} {'Durum':<20}")
        sonuc.append("-" * 95)

        for _, row in en_bos.iterrows():
            mag = str(row[col_magaza])[:29]
            doluluk = row.get('_fiili', 0)
            cover = row.get('_cover', 0)
            stok = row.get('_stok_adet', 0)
            satis = row.get('_satis_adet', 0)
            durum = row.get('_durum', 'N/A')
            sonuc.append(f"{mag:<30} %{doluluk:>8.0f} {cover:>7.1f}hf {stok:>11,.0f} {satis:>11,.0f} {durum:<20}")
    
    # =========================================
    # 5. KARLI-HIZLI METRİK DAĞILIMI
    # =========================================
    if col_karli_hizli:
        sonuc.append(f"\n📊 KARLI-HIZLI METRİK DAĞILIMI")
        sonuc.append("-" * 70)
        
        metrik_dag = df.groupby(col_karli_hizli).agg({
            col_magaza: 'count',
            '_stok_adet': 'sum' if '_stok_adet' in df.columns else 'count',
            '_satis_adet': 'sum' if '_satis_adet' in df.columns else 'count'
        }).rename(columns={col_magaza: 'magaza_sayisi'})
        
        sonuc.append(f"{'Metrik':<25} {'Mağaza':>8} {'%Dağılım':>10} {'Stok':>15} {'Satış':>15}")
        sonuc.append("-" * 75)
        
        for metrik, row in metrik_dag.iterrows():
            mag_sayi = row['magaza_sayisi']
            mag_pct = mag_sayi / toplam_magaza * 100
            stok = row.get('_stok_adet', 0)
            satis = row.get('_satis_adet', 0)
            emoji = "✅" if 'karlı' in str(metrik).lower() and 'hızlı' in str(metrik).lower() else ""
            sonuc.append(f"{str(metrik)[:24]:<25} {mag_sayi:>8} {mag_pct:>9.1f}% {stok:>14,.0f} {satis:>14,.0f} {emoji}")
    
    # =========================================
    # 6. EN İYİ PERFORMANS (LFL Satış)
    # =========================================
    if '_lfl_satis' in df.columns:
        sonuc.append(f"\n✅ EN İYİ PERFORMANS - TOP 5 (LFL Satış Büyümesi)")
        sonuc.append("-" * 60)
        
        en_iyi = df.nlargest(5, '_lfl_satis')
        for _, row in en_iyi.iterrows():
            mag = str(row[col_magaza])[:30]
            lfl = row['_lfl_satis']
            doluluk = row.get('_fiili', 0)
            sonuc.append(f"   {mag}: LFL %{lfl:+.0f}, Doluluk %{doluluk:.0f}")
    
    # =========================================
    # 7. EN KÖTÜ PERFORMANS (LFL Satış)
    # =========================================
    if '_lfl_satis' in df.columns:
        sonuc.append(f"\n🔴 EN KÖTÜ PERFORMANS - TOP 5 (LFL Satış Düşüşü)")
        sonuc.append("-" * 60)
        
        en_kotu = df.nsmallest(5, '_lfl_satis')
        for _, row in en_kotu.iterrows():
            mag = str(row[col_magaza])[:30]
            lfl = row['_lfl_satis']
            doluluk = row.get('_fiili', 0)
            sonuc.append(f"   {mag}: LFL %{lfl:+.0f}, Doluluk %{doluluk:.0f}")
    
    # =========================================
    # 8. ÖZET DEĞERLENDİRME (YENİ EŞİKLER)
    # =========================================
    sonuc.append(f"\n📋 ÖZET DEĞERLENDİRME")
    sonuc.append("-" * 60)

    if '_fiili' in df.columns:
        cok_dolu = len(df[df['_fiili'] >= 110])
        optimal = len(df[(df['_fiili'] >= 95) & (df['_fiili'] < 110)])
        bos = len(df[(df['_fiili'] >= 80) & (df['_fiili'] < 95)])
        asiri_bos = len(df[df['_fiili'] < 80])

        sonuc.append(f"   🔴 Çok Dolu (>%110): {cok_dolu} mağaza")
        sonuc.append(f"   ✅ Optimal (%95-109): {optimal} mağaza")
        sonuc.append(f"   ⚠️ Boş (%80-94): {bos} mağaza")
        sonuc.append(f"   🔴 Aşırı Boş (<%80): {asiri_bos} mağaza")

    # Cover bazlı kritik durumlar
    if '_fiili' in df.columns and '_cover' in df.columns:
        sonuc.append(f"\n📊 COVER BAZLI KRİTİK DURUMLAR")
        sonuc.append("-" * 60)

        # En kritik: Hızlı satış + Boş (satış kaçırılıyor)
        hizli_bos = len(df[(df['_cover'] <= 12) & (df['_fiili'] < 95)])
        if hizli_bos > 0:
            sonuc.append(f"   🚨 {hizli_bos} mağaza hızlı satıyor ama boş - ACİL SEVKİYAT!")

        # Risk: Yavaş satış + Dolu (stok fazlası)
        yavas_dolu = len(df[(df['_cover'] > 12) & (df['_fiili'] >= 110)])
        if yavas_dolu > 0:
            sonuc.append(f"   ⚠️ {yavas_dolu} mağaza yavaş satıyor ama dolu - STOK ERİTME!")

        # Sağlıklı: Hızlı satış + Dolu veya Yavaş satış + Optimal
        saglikli = len(df[
            ((df['_cover'] <= 12) & (df['_fiili'] >= 95)) |
            ((df['_cover'] > 12) & (df['_fiili'] >= 95) & (df['_fiili'] < 110))
        ])
        sonuc.append(f"   ✅ {saglikli} mağaza sağlıklı durumda")

    return "\n".join(sonuc)


def siparis_takip_analiz(kup: KupVeri, ana_grup: str = None) -> str:
    """
    Sipariş Yerleştirme ve Satınalma Takip analizi
    
    Kolonlar: Ana Grup, Ara Grup, Alt Grup, Onaylı Alım Bütçe, Total Sipariş,
              Depoya Giren, Bekleyen Sipariş, Depo Giriş oranları
    """
    
    if len(kup.siparis_takip) == 0:
        return "❌ Sipariş Takip raporu yüklenmemiş."
    
    df = kup.siparis_takip.copy()
    kolonlar = list(df.columns)
    
    sonuc = []
    sonuc.append("=" * 60)
    sonuc.append("📦 SİPARİŞ VE SATINALMA TAKİP")
    sonuc.append("=" * 60 + "\n")
    
    # Kolon mapping
    def find_col(keywords, exclude=[]):
        for kol in kolonlar:
            kol_lower = str(kol).lower()
            if all(k in kol_lower for k in keywords) and not any(e in kol_lower for e in exclude):
                return kol
        return None
    
    col_ana_grup = find_col(['ana', 'grup']) or find_col(['yeni', 'ana'])
    col_ara_grup = find_col(['ara', 'grup'])
    col_alt_grup = find_col(['alt', 'grup']) or find_col(['yeni', 'alt'])
    col_alim_butce = find_col(['onaylı', 'alım', 'bütçe', 'tutar'], ['adet'])
    col_siparis = find_col(['total', 'sipariş', 'tutar'], ['adet', 'hariç'])
    col_depo_giren = find_col(['depoya', 'giren', 'tutar'], ['adet', 'hariç'])
    col_bekleyen = find_col(['bekleyen', 'sipariş', 'tutar'], ['adet', 'hariç'])
    col_gerceklesme = find_col(['depo', 'giriş', 'alım', 'bütçe', 'oran'])
    
    print(f"Sipariş Takip kolonları: {kolonlar[:10]}")
    
    # Filtrele
    if ana_grup:
        df = df[df[col_ana_grup].astype(str).str.upper().str.contains(ana_grup.upper())]
        sonuc.append(f"📁 Ana Grup Filtresi: {ana_grup}\n")
    
    if len(df) == 0:
        return "❌ Filtreye uygun veri bulunamadı."
    
    # Parse fonksiyonu
    def parse_val(val):
        if pd.isna(val):
            return 0
        try:
            return float(str(val).replace('%', '').replace(',', '.').replace(' ', '').strip())
        except:
            return 0
    
    def parse_pct(val):
        v = parse_val(val)
        if -2 < v < 2 and v != 0:
            return v * 100
        return v
    
    # GENEL ÖZET
    sonuc.append(f"📊 GENEL ÖZET ({len(df)} satır)")
    sonuc.append("-" * 50)
    
    if col_alim_butce:
        toplam_butce = df[col_alim_butce].apply(parse_val).sum()
        sonuc.append(f"   Onaylı Alım Bütçe: {toplam_butce/1e6:,.1f}M TL")
    
    if col_siparis:
        toplam_siparis = df[col_siparis].apply(parse_val).sum()
        sonuc.append(f"   Total Sipariş: {toplam_siparis/1e6:,.1f}M TL")
    
    if col_depo_giren:
        toplam_giren = df[col_depo_giren].apply(parse_val).sum()
        sonuc.append(f"   Depoya Giren: {toplam_giren/1e6:,.1f}M TL")
    
    if col_bekleyen:
        toplam_bekleyen = df[col_bekleyen].apply(parse_val).sum()
        sonuc.append(f"   Bekleyen Sipariş: {toplam_bekleyen/1e6:,.1f}M TL")
    
    # Gerçekleşme oranı
    if col_alim_butce and col_depo_giren:
        butce = df[col_alim_butce].apply(parse_val).sum()
        giren = df[col_depo_giren].apply(parse_val).sum()
        if butce > 0:
            oran = giren / butce * 100
            emoji = "✅" if oran >= 80 else ("⚠️" if oran >= 60 else "🔴")
            sonuc.append(f"   {emoji} Gerçekleşme Oranı: %{oran:.0f}")
    
    # ANA GRUP BAZINDA
    if col_ana_grup and not ana_grup:
        sonuc.append(f"\n📁 ANA GRUP BAZINDA SİPARİŞ DURUMU")
        sonuc.append("-" * 60)
        
        # Grupla
        df['_butce'] = df[col_alim_butce].apply(parse_val) if col_alim_butce else 0
        df['_siparis'] = df[col_siparis].apply(parse_val) if col_siparis else 0
        df['_giren'] = df[col_depo_giren].apply(parse_val) if col_depo_giren else 0
        df['_bekleyen'] = df[col_bekleyen].apply(parse_val) if col_bekleyen else 0
        
        grup_ozet = df.groupby(col_ana_grup).agg({
            '_butce': 'sum',
            '_siparis': 'sum',
            '_giren': 'sum',
            '_bekleyen': 'sum'
        }).sort_values('_butce', ascending=False)
        
        sonuc.append(f"{'Ana Grup':<25} {'Bütçe':>12} {'Sipariş':>12} {'Giren':>12} {'Bekleyen':>12} {'%Gerç':>8}")
        sonuc.append("-" * 85)
        
        for idx, row in grup_ozet.head(12).iterrows():
            grup = str(idx)[:24]
            butce = row['_butce'] / 1e6
            siparis = row['_siparis'] / 1e6
            giren = row['_giren'] / 1e6
            bekleyen = row['_bekleyen'] / 1e6
            oran = (giren / butce * 100) if butce > 0 else 0
            emoji = "✅" if oran >= 80 else ("⚠️" if oran >= 60 else "🔴")
            sonuc.append(f"{grup:<25} {butce:>10.1f}M {siparis:>10.1f}M {giren:>10.1f}M {bekleyen:>10.1f}M {oran:>6.0f}% {emoji}")
    
    # BEKLEYEN SİPARİŞ UYARISI
    if col_bekleyen:
        df['_bekleyen'] = df[col_bekleyen].apply(parse_val)
        bekleyen_yuksek = df[df['_bekleyen'] > df['_bekleyen'].quantile(0.9)]
        
        if len(bekleyen_yuksek) > 0:
            sonuc.append(f"\n⚠️ YÜKSEK BEKLEYEN SİPARİŞ (Top 10)")
            sonuc.append("-" * 50)
            
            for _, row in bekleyen_yuksek.nlargest(10, '_bekleyen').iterrows():
                grup = str(row.get(col_alt_grup, row.get(col_ana_grup, 'N/A')))[:30]
                bekleyen = row['_bekleyen'] / 1e6
                sonuc.append(f"   {grup}: {bekleyen:.1f}M TL bekliyor")
    
    return "\n".join(sonuc)


def web_arama(sorgu: str) -> str:
    """
    Web'den güncel bilgi arar - Enflasyon, sektör verileri, ekonomik göstergeler
    DuckDuckGo ücretsiz API kullanır
    Tarih parametrik: Yıl = bu yıl, Ay = bu ay - 1
    """
    import urllib.request
    import urllib.parse
    import json
    from datetime import datetime
    
    # Dinamik tarih hesapla (bu ay - 1)
    simdi = datetime.now()
    if simdi.month == 1:
        sorgu_yil = simdi.year - 1
        sorgu_ay = 12
    else:
        sorgu_yil = simdi.year
        sorgu_ay = simdi.month - 1
    
    ay_isimleri = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    sorgu_ay_adi = ay_isimleri[sorgu_ay]
    
    # Sorguya tarih ekle (eğer yoksa)
    if str(sorgu_yil) not in sorgu and sorgu_ay_adi.lower() not in sorgu.lower():
        sorgu_with_date = f"{sorgu} {sorgu_ay_adi} {sorgu_yil}"
    else:
        sorgu_with_date = sorgu
    
    sonuc = []
    sonuc.append(f"🔍 WEB ARAMA: {sorgu_with_date}")
    sonuc.append(f"📅 Referans Dönem: {sorgu_ay_adi} {sorgu_yil}")
    sonuc.append("-" * 50)
    
    try:
        # DuckDuckGo Instant Answer API
        encoded_query = urllib.parse.quote(sorgu_with_date)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        # Abstract (özet bilgi)
        if data.get('Abstract'):
            sonuc.append(f"\n📋 ÖZET:")
            sonuc.append(data['Abstract'])
        
        # Related Topics
        if data.get('RelatedTopics'):
            sonuc.append(f"\n📌 İLGİLİ BİLGİLER:")
            for topic in data['RelatedTopics'][:5]:
                if isinstance(topic, dict) and topic.get('Text'):
                    sonuc.append(f"   • {topic['Text'][:200]}")
        
        # Eğer sonuç yoksa, GÜNCEL referans değerler
        if not data.get('Abstract') and not data.get('RelatedTopics'):
            sonuc.append(f"\n⚠️ Web'den güncel veri alınamadı.")
            sonuc.append(f"\n💡 GÜNCEL REFERANS DEĞERLERİ ({sorgu_ay_adi} {sorgu_yil}):")
            sonuc.append(f"   • Türkiye TÜFE (yıllık): ~%30 (tahmini)")
            sonuc.append(f"   • Türkiye ÜFE (yıllık): ~%20-25")
            sonuc.append(f"   • Kozmetik sektör büyümesi: ~%25-30")
            sonuc.append(f"   • USD/TRY: ~35-36 TL")
            sonuc.append(f"   • Perakende büyümesi (nominal): ~%35-40")
        
    except Exception as e:
        sonuc.append(f"\n❌ Web arama hatası: {str(e)}")
        sonuc.append(f"\n💡 GÜNCEL REFERANS DEĞERLERİ ({sorgu_ay_adi} {sorgu_yil}):")
        sonuc.append(f"   • Türkiye TÜFE (yıllık): ~%30 (tahmini)")
        sonuc.append(f"   • Türkiye ÜFE (yıllık): ~%20-25")
        sonuc.append(f"   • Kozmetik sektör büyümesi: ~%25-30")
        sonuc.append(f"   • USD/TRY: ~35-36 TL")
        sonuc.append(f"   • Perakende büyümesi (nominal): ~%35-40")
    
    sonuc.append(f"\n📅 Sorgu zamanı: {simdi.strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(sonuc)


def ihtiyac_hesapla(kup: KupVeri, limit: int = 50) -> str:
    """Mağaza ihtiyacı vs Depo stok karşılaştırması"""
    
    sonuc = []
    sonuc.append("=== İHTİYAÇ ANALİZİ ===\n")
    sonuc.append("Mağaza ihtiyacı vs Depo stok karşılaştırması\n")
    
    if len(kup.stok_satis) == 0:
        return "❌ Stok/Satış verisi yüklenmemiş."
    
    if len(kup.depo_stok) == 0:
        return "❌ Depo stok verisi yüklenmemiş."
    
    df = kup.stok_satis.copy()
    
    # Mağaza bazında ihtiyaç hesapla
    if 'stok_durum' not in df.columns:
        return "❌ Stok durumu hesaplanamamış."
    
    # Sevk gereken satırları al
    sevk_gerekli = df[df['stok_durum'] == 'SEVK_GEREKLI'].copy()
    
    if len(sevk_gerekli) == 0:
        return "✅ Sevk gereken ürün bulunmuyor."
    
    # Ürün bazında ihtiyaç topla
    if 'urun_kod' not in sevk_gerekli.columns:
        return "❌ urun_kod kolonu bulunamadı."
    
    ihtiyac = sevk_gerekli.groupby('urun_kod').agg({
        'stok': 'sum',
        'min_deger': 'first'
    }).reset_index()
    ihtiyac.columns = ['urun_kod', 'mevcut_stok', 'min_deger']
    
    # Mağaza sayısını hesapla
    magaza_sayisi = sevk_gerekli.groupby('urun_kod').size().reset_index(name='magaza_sayisi')
    ihtiyac = ihtiyac.merge(magaza_sayisi, on='urun_kod')
    
    # İhtiyaç hesapla
    ihtiyac['ihtiyac'] = ihtiyac['magaza_sayisi'] * ihtiyac['min_deger'].fillna(3) - ihtiyac['mevcut_stok']
    ihtiyac['ihtiyac'] = ihtiyac['ihtiyac'].clip(lower=0)
    
    # Depo stok ile birleştir
    depo = kup.depo_stok.copy()
    depo.columns = depo.columns.str.lower().str.strip()
    
    if 'urun_kod' in depo.columns:
        depo['urun_kod'] = depo['urun_kod'].astype(str)
        ihtiyac['urun_kod'] = ihtiyac['urun_kod'].astype(str)
        
        depo_grouped = depo.groupby('urun_kod')['stok'].sum().reset_index()
        depo_grouped.columns = ['urun_kod', 'depo_stok']
        
        ihtiyac = ihtiyac.merge(depo_grouped, on='urun_kod', how='left')
        ihtiyac['depo_stok'] = ihtiyac['depo_stok'].fillna(0)
    else:
        ihtiyac['depo_stok'] = 0
    
    # Karşılama durumu
    ihtiyac['karsilama'] = np.where(
        ihtiyac['depo_stok'] >= ihtiyac['ihtiyac'],
        'TAM',
        np.where(ihtiyac['depo_stok'] > 0, 'KISMİ', 'YOK')
    )
    
    # Önceliklendir
    ihtiyac = ihtiyac.sort_values('ihtiyac', ascending=False).head(limit)
    
    sonuc.append(f"{'Ürün Kodu':<12} | {'Mağaza#':>8} | {'İhtiyaç':>10} | {'Depo':>10} | Durum")
    sonuc.append("-" * 65)
    
    for _, row in ihtiyac.iterrows():
        if row['karsilama'] == 'TAM':
            durum = "✅ Tam karşılanır"
        elif row['karsilama'] == 'KISMİ':
            durum = "🟡 Kısmi"
        else:
            durum = "🔴 Depoda yok"
        
        sonuc.append(f"{row['urun_kod']:<12} | {row['magaza_sayisi']:>8} | {row['ihtiyac']:>10,.0f} | {row['depo_stok']:>10,.0f} | {durum}")
    
    # Özet
    sonuc.append("\n--- ÖZET ---")
    tam = len(ihtiyac[ihtiyac['karsilama'] == 'TAM'])
    kismi = len(ihtiyac[ihtiyac['karsilama'] == 'KISMİ'])
    yok = len(ihtiyac[ihtiyac['karsilama'] == 'YOK'])
    
    sonuc.append(f"✅ Tam karşılanabilir: {tam} ürün")
    sonuc.append(f"🟡 Kısmi karşılanabilir: {kismi} ürün")
    sonuc.append(f"🔴 Depoda yok: {yok} ürün")
    
    toplam_ihtiyac = ihtiyac['ihtiyac'].sum()
    toplam_depo = ihtiyac['depo_stok'].sum()
    karsilama_orani = (toplam_depo / toplam_ihtiyac * 100) if toplam_ihtiyac > 0 else 0
    
    sonuc.append(f"\nToplam ihtiyaç: {toplam_ihtiyac:,.0f} adet")
    sonuc.append(f"Toplam depo stok: {toplam_depo:,.0f} adet")
    sonuc.append(f"Karşılama oranı: %{karsilama_orani:.1f}")
    
    return "\n".join(sonuc)


def genel_ozet(kup: KupVeri) -> str:
    """Genel özet - kategoriler ve bölgeler bazında durum"""
    
    if len(kup.stok_satis) == 0:
        return "Veri yüklenmemiş."
    
    sonuc = []
    
    # Toplam metrikler
    toplam_stok = kup.stok_satis['stok'].sum() if 'stok' in kup.stok_satis.columns else 0
    toplam_satis = kup.stok_satis['satis'].sum() if 'satis' in kup.stok_satis.columns else 0
    toplam_ciro = kup.stok_satis['ciro'].sum() if 'ciro' in kup.stok_satis.columns else 0
    toplam_kar = kup.stok_satis['kar'].sum() if 'kar' in kup.stok_satis.columns else 0
    
    # Depo stok
    depo_toplam = kup.depo_stok['stok'].sum() if len(kup.depo_stok) > 0 else 0
    
    # Stok durumu sayıları
    sevk_gerekli = len(kup.stok_satis[kup.stok_satis['stok_durum'] == 'SEVK_GEREKLI'])
    fazla_stok = len(kup.stok_satis[kup.stok_satis['stok_durum'] == 'FAZLA_STOK'])
    yavas = len(kup.stok_satis[kup.stok_satis['stok_durum'] == 'YAVAS'])
    normal = len(kup.stok_satis[kup.stok_satis['stok_durum'] == 'NORMAL'])
    toplam_kayit = len(kup.stok_satis)
    
    # Cover hesapla
    if toplam_satis > 0:
        genel_cover = (toplam_stok + depo_toplam) / toplam_satis
    else:
        genel_cover = 999
    
    # ANLATIMLI RAPOR
    sonuc.append("=== EVE KOZMETİK GENEL DURUM ANALİZİ ===\n")
    
    # Genel değerlendirme
    sevk_oran = sevk_gerekli / toplam_kayit * 100 if toplam_kayit > 0 else 0
    fazla_oran = (fazla_stok + yavas) / toplam_kayit * 100 if toplam_kayit > 0 else 0
    
    if sevk_oran > 50:
        sonuc.append("🚨 DURUM KRİTİK: Mağazaların yarısından fazlasında stok eksikliği var!")
        sonuc.append(f"   {sevk_gerekli:,} mağaza×ürün kombinasyonunda acil sevkiyat gerekiyor.\n")
    elif sevk_oran > 30:
        sonuc.append("⚠️ DURUM ENDİŞE VERİCİ: Önemli sayıda mağazada stok sıkıntısı var.")
        sonuc.append(f"   {sevk_gerekli:,} noktada sevkiyat bekliyor.\n")
    else:
        sonuc.append("✅ GENEL DURUM: Stok seviyeleri kontrol altında.\n")
    
    # Temel metrikler - anlatımlı
    sonuc.append("📊 TEMEL GÖSTERGELER")
    sonuc.append(f"  • Mağazalarda toplam {toplam_stok:,.0f} adet ürün bulunuyor")
    sonuc.append(f"  • Depoda {depo_toplam:,.0f} adet sevke hazır stok var")
    sonuc.append(f"  • Haftalık satış hızı: {toplam_satis:,.0f} adet")
    sonuc.append(f"  • Genel cover: {genel_cover:.1f} hafta (depo dahil)")
    
    if toplam_ciro > 0:
        kar_marji = toplam_kar / toplam_ciro * 100
        sonuc.append(f"  • Kar marjı: %{kar_marji:.1f}")
    
    # Stok durumu - anlatımlı
    sonuc.append("\n📦 STOK DURUMU ANALİZİ")
    
    if sevk_gerekli > 0:
        sonuc.append(f"  🔴 SEVKİYAT GEREKLİ: {sevk_gerekli:,} nokta (%{sevk_oran:.1f})")
        sonuc.append(f"     Bu mağazalarda stok minimum seviyenin altına düşmüş.")
    
    if fazla_stok > 0:
        sonuc.append(f"  🟡 FAZLA STOK: {fazla_stok:,} nokta")
        sonuc.append(f"     Bu ürünlerde stok eritme kampanyası düşünülebilir.")
    
    if yavas > 0:
        sonuc.append(f"  🟠 YAVAŞ DÖNEN: {yavas:,} nokta")
        sonuc.append(f"     Satış hızı düşük, indirim veya promosyon gerekebilir.")
    
    if normal > 0:
        sonuc.append(f"  ✅ NORMAL: {normal:,} nokta")
    
    # Öncelikli aksiyonlar
    sonuc.append("\n🎯 ÖNCELİKLİ AKSİYONLAR")
    
    aksiyon_no = 1
    if sevk_oran > 30:
        sonuc.append(f"  {aksiyon_no}. Acil sevkiyat planı oluştur (sevkiyat_plani aracını kullan)")
        aksiyon_no += 1
    
    if fazla_oran > 20:
        sonuc.append(f"  {aksiyon_no}. Fazla stoklar için kampanya planla (fazla_stok_analiz aracını kullan)")
        aksiyon_no += 1
    
    sonuc.append(f"  {aksiyon_no}. Detaylı kategori analizi için kategori_analiz aracını kullan")
    
    return "\n".join(sonuc)


def kategori_analiz(kup: KupVeri, kategori_kod: str) -> str:
    """Belirli kategorinin detaylı analizi"""
    
    # Kategori filtrele
    if 'kategori_kod' in kup.stok_satis.columns:
        kat_veri = kup.stok_satis[kup.stok_satis['kategori_kod'].astype(str) == str(kategori_kod)]
    else:
        return "Kategori bilgisi mevcut değil."
    
    if len(kat_veri) == 0:
        return f"Kategori '{kategori_kod}' bulunamadı."
    
    sonuc = []
    sonuc.append(f"=== KATEGORİ ANALİZİ: {kategori_kod} ===\n")
    
    # Özet metrikler
    sonuc.append(f"Toplam Satır: {len(kat_veri):,}")
    sonuc.append(f"Benzersiz Ürün: {kat_veri['urun_kod'].nunique():,}")
    sonuc.append(f"Benzersiz Mağaza: {kat_veri['magaza_kod'].nunique():,}")
    sonuc.append(f"Toplam Stok: {kat_veri['stok'].sum():,.0f}")
    sonuc.append(f"Toplam Satış: {kat_veri['satis'].sum():,.0f}")
    sonuc.append(f"Toplam Ciro: {kat_veri['ciro'].sum():,.0f} TL")
    sonuc.append(f"Toplam Kar: {kat_veri['kar'].sum():,.0f} TL")
    
    # Stok durumu
    sonuc.append("\n--- Stok Durumu ---")
    for durum in ['SEVK_GEREKLI', 'FAZLA_STOK', 'YAVAS', 'NORMAL']:
        count = len(kat_veri[kat_veri['stok_durum'] == durum])
        if count > 0:
            emoji = {'SEVK_GEREKLI': '🔴', 'FAZLA_STOK': '🟡', 'YAVAS': '🟠', 'NORMAL': '✅'}[durum]
            sonuc.append(f"{emoji} {durum}: {count:,} satır")
    
    # Mal grubu kırılımı
    if 'mg' in kat_veri.columns:
        sonuc.append("\n--- Mal Grubu Kırılımı ---")
        mg_ozet = kat_veri.groupby('mg').agg({
            'urun_kod': 'nunique',
            'stok': 'sum',
            'satis': 'sum'
        }).reset_index()
        mg_ozet.columns = ['MG', 'Urun_Sayisi', 'Stok', 'Satis']
        mg_ozet['Cover'] = mg_ozet['Stok'] / (mg_ozet['Satis'] + 0.1)
        mg_ozet = mg_ozet.nlargest(10, 'Stok')
        
        for _, row in mg_ozet.iterrows():
            durum = "🔴" if row['Cover'] > 12 else "✅"
            sonuc.append(f"{durum} MG {row['MG']}: {row['Urun_Sayisi']} ürün, Stok {row['Stok']:,.0f}, Cover {row['Cover']:.1f} hf")
    
    # En çok satan ürünler
    sonuc.append("\n--- En Çok Satan Ürünler ---")
    top_satis = kat_veri.groupby('urun_kod').agg({
        'satis': 'sum',
        'stok': 'sum',
        'ciro': 'sum'
    }).reset_index().nlargest(10, 'satis')
    
    for _, row in top_satis.iterrows():
        sonuc.append(f"  {row['urun_kod']}: Satış {row['satis']:,.0f} | Stok {row['stok']:,.0f}")
    
    # Sevk gereken ürünler
    sevk_gerekli = kat_veri[kat_veri['stok_durum'] == 'SEVK_GEREKLI']
    if len(sevk_gerekli) > 0:
        sonuc.append(f"\n--- Sevk Gereken ({len(sevk_gerekli)} satır) ---")
        top_sevk = sevk_gerekli.groupby('urun_kod').size().reset_index(name='magaza_sayisi')
        top_sevk = top_sevk.nlargest(10, 'magaza_sayisi')
        for _, row in top_sevk.iterrows():
            sonuc.append(f"  🔴 {row['urun_kod']}: {row['magaza_sayisi']} mağazada stok düşük")
    
    return "\n".join(sonuc)


def magaza_analiz(kup: KupVeri, magaza_kod: str) -> str:
    """Belirli mağazanın detaylı analizi"""
    
    mag_veri = kup.stok_satis[kup.stok_satis['magaza_kod'].astype(str) == str(magaza_kod)]
    
    if len(mag_veri) == 0:
        return f"Mağaza '{magaza_kod}' bulunamadı."
    
    sonuc = []
    sonuc.append(f"=== MAĞAZA ANALİZİ: {magaza_kod} ===\n")
    
    # Mağaza bilgileri
    if len(kup.magaza_master) > 0:
        mag_info = kup.magaza_master[kup.magaza_master['magaza_kod'].astype(str) == str(magaza_kod)]
        if len(mag_info) > 0:
            info = mag_info.iloc[0]
            sonuc.append(f"İl: {info.get('il', 'N/A')}")
            sonuc.append(f"Bölge: {info.get('bolge', 'N/A')}")
            sonuc.append(f"Tip: {info.get('tip', 'N/A')}")
            sonuc.append(f"SM: {info.get('sm', 'N/A')}")
            sonuc.append(f"Depo: {info.get('depo_kod', 'N/A')}")
    
    # Metrikler
    sonuc.append(f"\n--- Performans ---")
    sonuc.append(f"Toplam SKU: {mag_veri['urun_kod'].nunique():,}")
    sonuc.append(f"Toplam Stok: {mag_veri['stok'].sum():,.0f} adet")
    sonuc.append(f"Toplam Satış: {mag_veri['satis'].sum():,.0f} adet")
    sonuc.append(f"Toplam Ciro: {mag_veri['ciro'].sum():,.0f} TL")
    sonuc.append(f"Toplam Kar: {mag_veri['kar'].sum():,.0f} TL")
    
    # Stok durumu
    sonuc.append("\n--- Stok Durumu ---")
    for durum in ['SEVK_GEREKLI', 'FAZLA_STOK', 'YAVAS', 'NORMAL']:
        count = len(mag_veri[mag_veri['stok_durum'] == durum])
        if count > 0:
            emoji = {'SEVK_GEREKLI': '🔴', 'FAZLA_STOK': '🟡', 'YAVAS': '🟠', 'NORMAL': '✅'}[durum]
            sonuc.append(f"{emoji} {durum}: {count:,} ürün")
    
    # Sevk gereken ürünler
    sevk = mag_veri[mag_veri['stok_durum'] == 'SEVK_GEREKLI'].head(10)
    if len(sevk) > 0:
        sonuc.append(f"\n--- Sevk Gereken Ürünler ---")
        for _, row in sevk.iterrows():
            sonuc.append(f"  🔴 {row['urun_kod']}: Stok {row['stok']:.0f}, Min {row.get('min_deger', 3):.0f}")
    
    return "\n".join(sonuc)


def urun_analiz(kup: KupVeri, urun_kod: str) -> str:
    """Belirli ürünün detaylı analizi"""
    
    urun_veri = kup.stok_satis[kup.stok_satis['urun_kod'].astype(str) == str(urun_kod)]
    
    if len(urun_veri) == 0:
        return f"Ürün '{urun_kod}' bulunamadı."
    
    sonuc = []
    sonuc.append(f"=== ÜRÜN ANALİZİ: {urun_kod} ===\n")
    
    # Ürün bilgileri
    if len(kup.urun_master) > 0:
        urun_info = kup.urun_master[kup.urun_master['urun_kod'].astype(str) == str(urun_kod)]
        if len(urun_info) > 0:
            info = urun_info.iloc[0]
            sonuc.append(f"Kategori: {info.get('kategori_kod', 'N/A')}")
            sonuc.append(f"ÜMG: {info.get('umg', 'N/A')}")
            sonuc.append(f"MG: {info.get('mg', 'N/A')}")
            sonuc.append(f"Marka: {info.get('marka_kod', 'N/A')}")
            sonuc.append(f"Nitelik: {info.get('nitelik', 'N/A')}")
            sonuc.append(f"Durum: {info.get('durum', 'N/A')}")
    
    # Mağaza bazlı özet
    sonuc.append(f"\n--- Dağılım ---")
    sonuc.append(f"Mağaza Sayısı: {urun_veri['magaza_kod'].nunique():,}")
    sonuc.append(f"Toplam Mağaza Stok: {urun_veri['stok'].sum():,.0f} adet")
    sonuc.append(f"Toplam Satış: {urun_veri['satis'].sum():,.0f} adet")
    sonuc.append(f"Toplam Ciro: {urun_veri['ciro'].sum():,.0f} TL")
    
    # Depo stok
    if len(kup.depo_stok) > 0:
        depo_urun = kup.depo_stok[kup.depo_stok['urun_kod'].astype(str) == str(urun_kod)]
        if len(depo_urun) > 0:
            sonuc.append(f"\n--- Depo Stok ---")
            for _, row in depo_urun.iterrows():
                sonuc.append(f"  Depo {row['depo_kod']}: {row['stok']:,.0f} adet")
            sonuc.append(f"  Toplam Depo: {depo_urun['stok'].sum():,.0f} adet")
    
    # Stok durumu dağılımı
    sonuc.append("\n--- Mağaza Stok Durumu ---")
    for durum in ['SEVK_GEREKLI', 'FAZLA_STOK', 'YAVAS', 'NORMAL']:
        count = len(urun_veri[urun_veri['stok_durum'] == durum])
        if count > 0:
            emoji = {'SEVK_GEREKLI': '🔴', 'FAZLA_STOK': '🟡', 'YAVAS': '🟠', 'NORMAL': '✅'}[durum]
            sonuc.append(f"{emoji} {durum}: {count:,} mağaza")
    
    # Sevk gereken mağazalar
    sevk = urun_veri[urun_veri['stok_durum'] == 'SEVK_GEREKLI'].head(10)
    if len(sevk) > 0:
        sonuc.append(f"\n--- Sevk Gereken Mağazalar ---")
        for _, row in sevk.iterrows():
            sonuc.append(f"  🔴 Mağaza {row['magaza_kod']}: Stok {row['stok']:.0f}, Satış {row['satis']:.0f}")
    
    return "\n".join(sonuc)


def sevkiyat_plani(kup: KupVeri, limit: int = 50) -> str:
    """Sevkiyat planı oluştur - KPI bazlı"""
    
    sonuc = []
    sonuc.append("=== SEVKİYAT PLANI ===\n")
    
    # Mevcut kolonları kontrol et
    kolonlar = list(kup.stok_satis.columns)
    sonuc.append(f"Debug - Mevcut kolonlar: {kolonlar[:10]}...\n")
    
    # Sevk gereken satırlar
    if 'stok_durum' not in kup.stok_satis.columns:
        return "❌ Stok durumu hesaplanamamış."
    
    sevk_gerekli = kup.stok_satis[kup.stok_satis['stok_durum'] == 'SEVK_GEREKLI'].copy()
    
    if len(sevk_gerekli) == 0:
        return "✅ Sevk gereken ürün bulunmuyor."
    
    sonuc.append(f"Toplam sevk gereken: {len(sevk_gerekli):,} mağaza×ürün kombinasyonu\n")
    
    # Ürün bazlı önceliklendirme - dinamik kolon kullanımı
    agg_dict = {}
    if 'magaza_kod' in sevk_gerekli.columns:
        agg_dict['magaza_kod'] = 'count'
    if 'satis' in sevk_gerekli.columns:
        agg_dict['satis'] = 'sum'
    if 'stok' in sevk_gerekli.columns:
        agg_dict['stok'] = 'sum'
    if 'min_deger' in sevk_gerekli.columns:
        agg_dict['min_deger'] = 'first'
    
    if len(agg_dict) == 0 or 'urun_kod' not in sevk_gerekli.columns:
        return "❌ Gerekli kolonlar bulunamadı."
    
    urun_oncelik = sevk_gerekli.groupby('urun_kod').agg(agg_dict).reset_index()
    
    # Kolon isimlerini düzelt
    rename_map = {'magaza_kod': 'magaza_sayisi', 'satis': 'toplam_satis', 'stok': 'toplam_stok'}
    urun_oncelik = urun_oncelik.rename(columns=rename_map)
    
    # Eksik hesapla
    if 'magaza_sayisi' in urun_oncelik.columns and 'min_deger' in urun_oncelik.columns:
        urun_oncelik['eksik'] = urun_oncelik['magaza_sayisi'] * urun_oncelik['min_deger'].fillna(3) - urun_oncelik.get('toplam_stok', 0)
    else:
        urun_oncelik['eksik'] = 0
    
    # Sıralama
    if 'toplam_satis' in urun_oncelik.columns:
        urun_oncelik = urun_oncelik.sort_values('toplam_satis', ascending=False).head(limit)
    else:
        urun_oncelik = urun_oncelik.head(limit)
    
    # Depo stok kontrolü
    if len(kup.depo_stok) > 0 and 'urun_kod' in kup.depo_stok.columns:
        depo_grouped = kup.depo_stok.groupby('urun_kod')['stok'].sum().reset_index()
        depo_grouped.columns = ['urun_kod', 'depo_stok']
        urun_oncelik = urun_oncelik.merge(depo_grouped, on='urun_kod', how='left')
        urun_oncelik['depo_stok'] = urun_oncelik['depo_stok'].fillna(0)
    else:
        urun_oncelik['depo_stok'] = 0
    
    sonuc.append(f"{'Ürün Kodu':<12} | {'Mağaza#':>8} | {'Satış':>8} | {'Eksik':>8} | {'Depo':>8} | Durum")
    sonuc.append("-" * 75)
    
    for _, row in urun_oncelik.iterrows():
        magaza_s = row.get('magaza_sayisi', 0)
        toplam_s = row.get('toplam_satis', 0)
        eksik = row.get('eksik', 0)
        depo = row.get('depo_stok', 0)
        
        if depo >= eksik:
            durum = "✅ Sevk edilebilir"
        elif depo > 0:
            durum = "🟡 Kısmi sevk"
        else:
            durum = "🔴 Depoda yok"
        
        sonuc.append(f"{row['urun_kod']:<12} | {magaza_s:>8,} | {toplam_s:>8,.0f} | {eksik:>8,.0f} | {depo:>8,.0f} | {durum}")
    
    # Özet
    if 'eksik' in urun_oncelik.columns:
        sevk_edilebilir = len(urun_oncelik[urun_oncelik['depo_stok'] >= urun_oncelik['eksik']])
        kismi = len(urun_oncelik[(urun_oncelik['depo_stok'] > 0) & (urun_oncelik['depo_stok'] < urun_oncelik['eksik'])])
        depoda_yok = len(urun_oncelik[urun_oncelik['depo_stok'] == 0])
        
        sonuc.append(f"\n--- Özet ---")
        sonuc.append(f"✅ Tam sevk edilebilir: {sevk_edilebilir} ürün")
        sonuc.append(f"🟡 Kısmi sevk: {kismi} ürün")
        sonuc.append(f"🔴 Depoda yok: {depoda_yok} ürün")
    
    return "\n".join(sonuc)


def fazla_stok_analiz(kup: KupVeri, limit: int = 50) -> str:
    """Fazla stok analizi - indirim adayları"""
    
    sonuc = []
    sonuc.append("=== FAZLA STOK ANALİZİ (İNDİRİM ADAYLARI) ===\n")
    
    if 'stok_durum' not in kup.stok_satis.columns:
        return "❌ Stok durumu hesaplanamamış."
    
    # Fazla stok ve yavaş dönen
    fazla = kup.stok_satis[kup.stok_satis['stok_durum'].isin(['FAZLA_STOK', 'YAVAS'])].copy()
    
    if len(fazla) == 0:
        return "✅ Fazla stok bulunmuyor."
    
    sonuc.append(f"Toplam fazla/yavaş stok: {len(fazla):,} mağaza×ürün kombinasyonu\n")
    
    # Ürün bazlı özet - dinamik kolon kullanımı
    if 'urun_kod' not in fazla.columns:
        return "❌ urun_kod kolonu bulunamadı."
    
    agg_dict = {}
    if 'magaza_kod' in fazla.columns:
        agg_dict['magaza_kod'] = 'count'
    if 'stok' in fazla.columns:
        agg_dict['stok'] = 'sum'
    if 'satis' in fazla.columns:
        agg_dict['satis'] = 'sum'
    if 'ciro' in fazla.columns:
        agg_dict['ciro'] = 'sum'
    
    if len(agg_dict) == 0:
        return "❌ Gerekli kolonlar bulunamadı."
    
    urun_ozet = fazla.groupby('urun_kod').agg(agg_dict).reset_index()
    
    # Kolon isimlerini düzelt
    rename_map = {'magaza_kod': 'magaza_sayisi', 'stok': 'toplam_stok', 'satis': 'toplam_satis', 'ciro': 'toplam_ciro'}
    urun_ozet = urun_ozet.rename(columns=rename_map)
    
    # Cover hesapla
    if 'toplam_stok' in urun_ozet.columns and 'toplam_satis' in urun_ozet.columns:
        urun_ozet['cover'] = urun_ozet['toplam_stok'] / (urun_ozet['toplam_satis'] + 0.1)
    else:
        urun_ozet['cover'] = 0
    
    if 'toplam_stok' in urun_ozet.columns:
        urun_ozet = urun_ozet.sort_values('toplam_stok', ascending=False).head(limit)
    else:
        urun_ozet = urun_ozet.head(limit)
    
    sonuc.append(f"{'Ürün Kodu':<12} | {'Mağaza#':>8} | {'Stok':>10} | {'Satış':>8} | {'Cover':>8} | Öneri")
    sonuc.append("-" * 75)
    
    for _, row in urun_ozet.iterrows():
        cover = row.get('cover', 0)
        if cover > 52:
            oneri = "🔴 Agresif indirim"
        elif cover > 26:
            oneri = "🟡 Kampanya"
        else:
            oneri = "🟢 İzle"
        
        magaza_s = row.get('magaza_sayisi', 0)
        toplam_stok = row.get('toplam_stok', 0)
        toplam_satis = row.get('toplam_satis', 0)
        
        sonuc.append(f"{row['urun_kod']:<12} | {magaza_s:>8,} | {toplam_stok:>10,.0f} | {toplam_satis:>8,.0f} | {cover:>7.1f}hf | {oneri}")
    
    return "\n".join(sonuc)


def bolge_karsilastir(kup: KupVeri) -> str:
    """Bölgeler arası karşılaştırma"""
    
    if 'bolge' not in kup.stok_satis.columns:
        return "Bölge bilgisi mevcut değil."
    
    sonuc = []
    sonuc.append("=== BÖLGE KARŞILAŞTIRMASI ===\n")
    
    # Dinamik agg dict
    agg_dict = {}
    if 'magaza_kod' in kup.stok_satis.columns:
        agg_dict['magaza_kod'] = 'nunique'
    if 'urun_kod' in kup.stok_satis.columns:
        agg_dict['urun_kod'] = 'nunique'
    if 'stok' in kup.stok_satis.columns:
        agg_dict['stok'] = 'sum'
    if 'satis' in kup.stok_satis.columns:
        agg_dict['satis'] = 'sum'
    if 'ciro' in kup.stok_satis.columns:
        agg_dict['ciro'] = 'sum'
    if 'kar' in kup.stok_satis.columns:
        agg_dict['kar'] = 'sum'
    
    if len(agg_dict) == 0:
        return "❌ Gerekli kolonlar bulunamadı."
    
    bolge_ozet = kup.stok_satis.groupby('bolge').agg(agg_dict).reset_index()
    
    # Kolon isimlerini düzelt
    rename_map = {'magaza_kod': 'Magaza', 'urun_kod': 'Urun', 'stok': 'Stok', 'satis': 'Satis', 'ciro': 'Ciro', 'kar': 'Kar'}
    bolge_ozet = bolge_ozet.rename(columns=rename_map)
    bolge_ozet = bolge_ozet.rename(columns={'bolge': 'Bolge'})
    
    if 'Kar' in bolge_ozet.columns and 'Ciro' in bolge_ozet.columns:
        bolge_ozet['Kar_Marji'] = bolge_ozet['Kar'] / (bolge_ozet['Ciro'] + 0.01) * 100
    else:
        bolge_ozet['Kar_Marji'] = 0
    
    if 'Stok' in bolge_ozet.columns and 'Satis' in bolge_ozet.columns:
        bolge_ozet['Cover'] = bolge_ozet['Stok'] / (bolge_ozet['Satis'] + 0.1)
    else:
        bolge_ozet['Cover'] = 0
    
    if 'Ciro' in bolge_ozet.columns:
        bolge_ozet = bolge_ozet.sort_values('Ciro', ascending=False)
    
    sonuc.append(f"{'Bölge':<15} | {'Mağaza':>7} | {'Ciro':>12} | {'Kar %':>7} | {'Cover':>7}")
    sonuc.append("-" * 60)
    
    for _, row in bolge_ozet.iterrows():
        if pd.notna(row.get('Bolge')):
            durum = "✅" if row.get('Kar_Marji', 0) > 0 else "🔴"
            magaza = row.get('Magaza', 0)
            ciro = row.get('Ciro', 0)
            kar_marji = row.get('Kar_Marji', 0)
            cover = row.get('Cover', 0)
            sonuc.append(f"{durum} {str(row['Bolge']):<13} | {magaza:>7,} | {ciro:>12,.0f} | {kar_marji:>6.1f}% | {cover:>6.1f}hf")
    
    return "\n".join(sonuc)


def sevkiyat_hesapla(kup: KupVeri, kategori_kod = None, urun_kod: str = None, marka_kod: str = None, forward_cover: float = 7.0, export_excel: bool = False) -> str:
    """
    Sevkiyat hesaplaması - INLINE versiyon
    
    Mantık:
    1. hedef_stok = haftalik_satis × forward_cover
    2. rpt_ihtiyac = hedef_stok - stok - yol
    3. min_ihtiyac = min - stok - yol (eğer stok+yol < min ise)
    4. final_ihtiyac = MAX(rpt_ihtiyac, min_ihtiyac)
    
    export_excel=True ise Excel dosyası oluşturur ve yolunu döner
    """
    print("\n" + "="*50)
    print("🚀 SEVKIYAT_HESAPLA ÇAĞRILDI (INLINE)")
    print(f"   Parametreler: kategori={kategori_kod}, urun={urun_kod}, fc={forward_cover}, excel={export_excel}")
    print("="*50)
    
    try:
        # 1. VERİ KONTROLÜ
        stok_satis = getattr(kup, 'stok_satis', None)
        depo_stok = getattr(kup, 'depo_stok', None)
        
        if stok_satis is None or len(stok_satis) == 0:
            return "❌ Anlık stok/satış verisi yüklenmemiş."
        
        if depo_stok is None or len(depo_stok) == 0:
            return "❌ Depo stok verisi yüklenmemiş."
        
        print(f"✅ Veri OK: stok_satis={len(stok_satis)}, depo_stok={len(depo_stok)}")
        
        # 2. ANA VERİYİ HAZIRLA
        df = stok_satis.copy()
        df['urun_kod'] = df['urun_kod'].astype(str)
        df['magaza_kod'] = df['magaza_kod'].astype(str)
        print(f"   Başlangıç: {len(df)} satır")
        
        # Ürün filtresi
        if urun_kod is not None:
            urun_kod = str(urun_kod).strip()
            df = df[df['urun_kod'] == urun_kod]
            print(f"   Ürün filtresi ({urun_kod}): {len(df)} satır")
            if len(df) == 0:
                return f"❌ {urun_kod} kodlu ürün bulunamadı."
        
        # Kategori filtresi
        if kategori_kod is not None:
            kategori_kod = int(kategori_kod)
            if 'kategori_kod' in df.columns:
                df['kategori_kod'] = pd.to_numeric(df['kategori_kod'], errors='coerce').fillna(0).astype(int)
                df = df[df['kategori_kod'] == kategori_kod]
                print(f"   Kategori filtresi ({kategori_kod}): {len(df)} satır")
        
        if len(df) == 0:
            return "❌ Filtrelere uygun veri bulunamadı."
        
        # 3. DEPO KODU EKLE
        if 'depo_kod' not in df.columns:
            mag_m = getattr(kup, 'magaza_master', None)
            if mag_m is not None and 'depo_kod' in mag_m.columns:
                mag_m = mag_m.copy()
                mag_m['magaza_kod'] = mag_m['magaza_kod'].astype(str)
                df = df.merge(mag_m[['magaza_kod', 'depo_kod']], on='magaza_kod', how='left')
                df['depo_kod'] = pd.to_numeric(df['depo_kod'], errors='coerce').fillna(9001).astype(int)
            else:
                df['depo_kod'] = 9001
        else:
            df['depo_kod'] = pd.to_numeric(df['depo_kod'], errors='coerce').fillna(9001).astype(int)
        
        print(f"   Depo kodları: {df['depo_kod'].unique().tolist()}")
        
        # 4. SAYISAL KOLONLARI HAZIRLA
        df['haftalik_satis'] = pd.to_numeric(df['satis'], errors='coerce').fillna(0)
        df['stok'] = pd.to_numeric(df['stok'], errors='coerce').fillna(0)
        df['yol'] = pd.to_numeric(df.get('yol', 0), errors='coerce').fillna(0)
        
        # Min değeri - KPI'dan geliyorsa kullan, yoksa default
        if 'min_deger' in df.columns:
            df['min'] = pd.to_numeric(df['min_deger'], errors='coerce').fillna(0)
        else:
            # Default min = 1 haftalık satış
            df['min'] = df['haftalik_satis'] * 1
        
        # 5. COVER HESAPLA
        df['mevcut'] = df['stok'] + df['yol']
        df['cover'] = df['mevcut'] / df['haftalik_satis'].replace(0, 0.001)
        
        # 6. İHTİYAÇ HESAPLA
        forward_cover = float(forward_cover) if forward_cover else 7.0
        
        # Hedef stok = haftalık satış × forward cover
        df['hedef_stok'] = df['haftalik_satis'] * forward_cover
        
        # RPT ihtiyaç = hedef - stok - yol
        df['rpt_ihtiyac'] = (df['hedef_stok'] - df['stok'] - df['yol']).clip(lower=0)
        
        # Min ihtiyaç = eğer stok+yol < min ise, min - stok - yol
        df['min_ihtiyac'] = np.where(
            df['mevcut'] < df['min'],
            (df['min'] - df['stok'] - df['yol']).clip(lower=0),
            0
        )
        
        # Final ihtiyaç = MAX(RPT, Min)
        df['ihtiyac'] = df[['rpt_ihtiyac', 'min_ihtiyac']].max(axis=1)
        
        # İhtiyaç türünü belirle
        df['ihtiyac_turu'] = np.where(
            df['ihtiyac'] == 0, 'Yok',
            np.where(df['ihtiyac'] == df['min_ihtiyac'], 'MIN', 'RPT')
        )
        
        print(f"   İhtiyaç hesaplandı:")
        print(f"      - RPT ihtiyaç olan: {(df['rpt_ihtiyac'] > 0).sum()}")
        print(f"      - MIN ihtiyaç olan: {(df['min_ihtiyac'] > 0).sum()}")
        print(f"      - Toplam ihtiyaç olan: {(df['ihtiyac'] > 0).sum()}")
        
        # 7. DEPO STOK SÖZLÜĞÜ OLUŞTUR
        depo_df = depo_stok.copy()
        depo_df.columns = [c.lower().strip() for c in depo_df.columns]
        depo_df['urun_kod'] = depo_df['urun_kod'].astype(str)
        depo_df['depo_kod'] = pd.to_numeric(depo_df['depo_kod'], errors='coerce').fillna(9001).astype(int)
        depo_df['stok'] = pd.to_numeric(depo_df['stok'], errors='coerce').fillna(0)
        
        depo_stok_dict = {}
        for _, row in depo_df.iterrows():
            key = (int(row['depo_kod']), str(row['urun_kod']))
            depo_stok_dict[key] = depo_stok_dict.get(key, 0) + float(row['stok'])
        
        print(f"   Depo stok: {len(depo_stok_dict)} ürün×depo kombinasyonu")
        
        # 8. SEVKİYAT DAĞIT
        ihtiyac_df = df[df['ihtiyac'] > 0].copy()
        ihtiyac_df = ihtiyac_df.sort_values('ihtiyac', ascending=False)
        
        sevkiyat_list = []
        for _, row in ihtiyac_df.iterrows():
            key = (int(row['depo_kod']), str(row['urun_kod']))
            ihtiyac = float(row['ihtiyac'])
            
            mevcut_depo = depo_stok_dict.get(key, 0)
            if mevcut_depo > 0:
                sevk = min(ihtiyac, mevcut_depo)
                depo_stok_dict[key] -= sevk
            else:
                sevk = 0
            
            sevkiyat_list.append({
                'magaza_kod': row['magaza_kod'],
                'urun_kod': row['urun_kod'],
                'depo_kod': row['depo_kod'],
                'stok': int(row['stok']),
                'yol': int(row['yol']),
                'min': int(row['min']),
                'haftalik_satis': round(row['haftalik_satis'], 1),
                'cover': round(row['cover'], 1),
                'hedef_stok': int(row['hedef_stok']),
                'ihtiyac': int(ihtiyac),
                'ihtiyac_turu': row['ihtiyac_turu'],
                'sevkiyat': int(sevk),
                'karsilanamayan': int(ihtiyac - sevk)
            })
        
        if not sevkiyat_list:
            return "ℹ️ Sevkiyat ihtiyacı bulunamadı. Tüm mağazaların stoku yeterli."
        
        sonuc_df = pd.DataFrame(sevkiyat_list)
        
        # 9. ÖZET OLUŞTUR
        toplam_ihtiyac = sonuc_df['ihtiyac'].sum()
        toplam_sevkiyat = sonuc_df['sevkiyat'].sum()
        karsilanamayan = sonuc_df['karsilanamayan'].sum()
        karsilama_orani = (toplam_sevkiyat / toplam_ihtiyac * 100) if toplam_ihtiyac > 0 else 0
        
        rpt_count = (sonuc_df['ihtiyac_turu'] == 'RPT').sum()
        min_count = (sonuc_df['ihtiyac_turu'] == 'MIN').sum()
        
        print(f"✅ Hesaplama tamamlandı: {len(sonuc_df)} satır, {toplam_sevkiyat:,.0f} adet sevkiyat")
        
        # 10. RAPOR OLUŞTUR
        rapor = []
        
        # Filtre bilgisi
        filtre_text = ""
        if urun_kod:
            filtre_text = f" (Ürün: {urun_kod})"
        elif kategori_kod:
            kat_adi = {11: "Renkli Kozmetik", 14: "Saç Bakım", 16: "Cilt Bakım", 19: "Parfüm", 20: "Kişisel Bakım"}.get(kategori_kod, str(kategori_kod))
            filtre_text = f" ({kat_adi})"
        
        rapor.append(f"=== SEVKİYAT HESAPLAMA SONUCU{filtre_text} ===")
        rapor.append(f"Forward Cover: {forward_cover} hafta\n")
        
        rapor.append("📊 ÖZET:")
        rapor.append(f"   Toplam İhtiyaç: {toplam_ihtiyac:,.0f} adet")
        rapor.append(f"   Toplam Sevkiyat: {toplam_sevkiyat:,.0f} adet")
        rapor.append(f"   Karşılama Oranı: %{karsilama_orani:.1f}")
        rapor.append(f"   Karşılanamayan: {karsilanamayan:,.0f} adet")
        rapor.append(f"   Mağaza Sayısı: {sonuc_df['magaza_kod'].nunique()}")
        if not urun_kod:
            rapor.append(f"   Ürün Sayısı: {sonuc_df['urun_kod'].nunique()}")
        rapor.append("")
        
        rapor.append("📋 İHTİYAÇ TÜRLERİ:")
        rapor.append(f"   RPT (Replenishment): {rpt_count} mağaza×ürün")
        rapor.append(f"   MIN (Minimum Altı): {min_count} mağaza×ürün")
        rapor.append("")
        
        # Durum değerlendirmesi
        if karsilama_orani >= 90:
            rapor.append("✅ DURUM: İyi - Depo stoku ihtiyaçların çoğunu karşılıyor.")
        elif karsilama_orani >= 70:
            rapor.append("⚠️ DURUM: Orta - Bazı mağazalarda stok yetersizliği var.")
        else:
            rapor.append("🚨 DURUM: Kritik - Depo stok yetersiz, satınalma gerekli.")
        rapor.append("")
        
        # En çok sevkiyat gereken mağazalar
        rapor.append("🏪 EN ÇOK SEVKİYAT GEREKEN MAĞAZALAR (Top 10):")
        top_mag = sonuc_df.groupby('magaza_kod')['sevkiyat'].sum().nlargest(10)
        for i, (mag, miktar) in enumerate(top_mag.items(), 1):
            rapor.append(f"   {i}. Mağaza {mag}: {int(miktar):,} adet")
        rapor.append("")
        
        # Tek ürün değilse, en çok sevkiyat gereken ürünler
        if not urun_kod:
            rapor.append("🏆 EN ÇOK SEVKİYAT GEREKEN ÜRÜNLER (Top 10):")
            top_urun = sonuc_df.groupby('urun_kod')['sevkiyat'].sum().nlargest(10)
            for i, (urun, miktar) in enumerate(top_urun.items(), 1):
                rapor.append(f"   {i}. {urun}: {int(miktar):,} adet")
            rapor.append("")
        
        # Depo bazında dağılım
        rapor.append("🏭 DEPO BAZINDA DAĞILIM:")
        depo_ozet = sonuc_df.groupby('depo_kod')['sevkiyat'].sum().sort_values(ascending=False)
        for depo, miktar in depo_ozet.items():
            rapor.append(f"   Depo {depo}: {int(miktar):,} adet")
        rapor.append("")
        
        # Karşılanamayan varsa
        if karsilanamayan > 0:
            rapor.append("⚠️ KARŞILANAMAYAN - SATINALMA GEREKLİ:")
            kars_df = sonuc_df[sonuc_df['karsilanamayan'] > 0]
            if urun_kod:
                # Tek ürün - mağaza bazında göster
                for _, row in kars_df.nlargest(10, 'karsilanamayan').iterrows():
                    rapor.append(f"   Mağaza {row['magaza_kod']}: {int(row['karsilanamayan']):,} adet eksik")
            else:
                # Çoklu ürün - ürün bazında göster
                kars_urun = kars_df.groupby('urun_kod')['karsilanamayan'].sum().nlargest(10)
                for urun, miktar in kars_urun.items():
                    rapor.append(f"   {urun}: {int(miktar):,} adet eksik")
        
        rapor.append(f"\n📋 Toplam {len(sonuc_df):,} mağaza×ürün için hesaplama yapıldı.")
        
        # EXCEL EXPORT
        if export_excel:
            try:
                import os
                from datetime import datetime
                
                # Export için DataFrame hazırla
                export_df = sonuc_df[['magaza_kod', 'urun_kod', 'depo_kod', 'stok', 'yol', 'min',
                                      'haftalik_satis', 'cover', 'hedef_stok', 'rpt_ihtiyac', 
                                      'ihtiyac', 'ihtiyac_turu', 'sevkiyat', 'karsilanamayan']].copy()
                
                # Kolon isimlerini Türkçeleştir
                export_df.columns = ['Mağaza', 'Ürün Kodu', 'Depo', 'Stok', 'Yol', 'Min',
                                    'Haftalık Satış', 'Cover', 'Hedef Stok', 'RPT İhtiyaç',
                                    'Toplam İhtiyaç', 'İhtiyaç Türü', 'Sevk Adet', 'Karşılanamayan']
                
                # Dosya adı oluştur
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                if urun_kod:
                    filename = f"sevkiyat_{urun_kod}_{timestamp}.xlsx"
                elif kategori_kod:
                    filename = f"sevkiyat_kat{kategori_kod}_{timestamp}.xlsx"
                else:
                    filename = f"sevkiyat_tum_{timestamp}.xlsx"
                
                # Dosya yolu
                export_path = os.path.join("/tmp", filename)
                
                # Excel'e yaz
                export_df.to_excel(export_path, index=False, sheet_name='Sevkiyat')
                
                rapor.append(f"\n📁 EXCEL DOSYASI OLUŞTURULDU:")
                rapor.append(f"   📥 {export_path}")
                
                print(f"✅ Excel export: {export_path}")
                
            except Exception as ex:
                rapor.append(f"\n⚠️ Excel export hatası: {str(ex)}")
        
        return "\n".join(rapor)
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"❌ HATA: {e}")
        print(error_detail[:500])
        return f"❌ Sevkiyat hesaplama hatası: {str(e)}\n\nDetay:\n{error_detail[:300]}"


# =============================================================================
# CLAUDE AGENT - TOOL CALLING
# =============================================================================

TOOLS = [
    {
        "name": "web_arama",
        "description": "Web'den güncel ekonomik veri arar. Enflasyon, TÜFE, döviz kuru, sektör büyümesi gibi makro verileri getirir. Fiyat artışı yorumlarken MUTLAKA enflasyonla karşılaştır!",
        "input_schema": {
            "type": "object",
            "properties": {
                "sorgu": {
                    "type": "string",
                    "description": "Aranacak sorgu. Örn: 'Türkiye enflasyon 2025', 'kozmetik sektör büyümesi', 'USD TRY kuru'"
                }
            },
            "required": ["sorgu"]
        }
    },
    {
        "name": "genel_ozet",
        "description": "Tüm verinin genel özetini gösterir. Toplam stok, satış, ciro, kar ve stok durumu dağılımını içerir. Analize başlarken ilk çağrılması gereken araç.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "kategori_analiz",
        "description": "Belirli bir kategorinin detaylı analizini yapar. Mal grubu kırılımı, en çok satanlar, sevk gereken ürünleri gösterir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kategori_kod": {
                    "type": "string",
                    "description": "Analiz edilecek kategori kodu. Örn: '14', '16'"
                }
            },
            "required": ["kategori_kod"]
        }
    },
    {
        "name": "magaza_analiz",
        "description": "Belirli bir mağazanın detaylı analizini yapar. Mağaza bilgileri, performans, stok durumu ve sevk gereken ürünleri gösterir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "magaza_kod": {
                    "type": "string",
                    "description": "Analiz edilecek mağaza kodu. Örn: '1002', '1178'"
                }
            },
            "required": ["magaza_kod"]
        }
    },
    {
        "name": "urun_analiz",
        "description": "Belirli bir ürünün tüm mağazalardaki durumunu analiz eder. Ürün bilgileri, dağılım, depo stok ve sevk gereken mağazaları gösterir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "urun_kod": {
                    "type": "string",
                    "description": "Analiz edilecek ürün kodu. Örn: '1000048', '1032064'"
                }
            },
            "required": ["urun_kod"]
        }
    },
    {
        "name": "sevkiyat_plani",
        "description": "KPI hedeflerine göre sevkiyat planı oluşturur. Stoku minimum değerin altına düşen mağaza×ürün kombinasyonlarını önceliklendirir ve depo stok kontrolü yapar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Listelenecek maksimum ürün sayısı. Varsayılan: 50",
                    "default": 50
                }
            },
            "required": []
        }
    },
    {
        "name": "fazla_stok_analiz",
        "description": "Fazla stok ve yavaş dönen ürünleri analiz eder. İndirim ve kampanya adaylarını belirler.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Listelenecek maksimum ürün sayısı. Varsayılan: 50",
                    "default": 50
                }
            },
            "required": []
        }
    },
    {
        "name": "bolge_karsilastir",
        "description": "Bölgeler arası performans karşılaştırması yapar. Mağaza sayısı, ciro, kar marjı ve cover bilgilerini gösterir.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "trading_analiz",
        "description": "Trading raporunu 3 seviyeli hiyerarşi ile analiz eder. Parametre verilmezse şirket özeti + ana gruplar gösterir. ana_grup verilirse o grubun ara gruplarını, ana_grup+ara_grup verilirse mal gruplarını gösterir. Drill-down analiz için kullan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ana_grup": {
                    "type": "string",
                    "description": "Ana grup adı (RENKLİ KOZMETİK, CİLT BAKIM, SAÇ BAKIM, PARFÜM vb). Boş bırakılırsa şirket özeti gösterir."
                },
                "ara_grup": {
                    "type": "string",
                    "description": "Ara grup adı (GÖZ ÜRÜNLERİ, YÜZ ÜRÜNLERİ, ŞAMPUAN vb). ana_grup ile birlikte kullanılır, mal grubu detayı gösterir."
                }
            },
            "required": []
        }
    },
    {
        "name": "cover_analiz",
        "description": "SC Tablosundan cover grup analizini yapar. (Eski format). Yeni format için cover_diagram_analiz kullan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sayfa": {
                    "type": "string",
                    "description": "Analiz edilecek SC sayfa adı. Boş bırakılırsa otomatik seçilir."
                }
            },
            "required": []
        }
    },
    {
        "name": "cover_diagram_analiz",
        "description": "Cover Diagram raporunu analiz eder. Mağaza×AltGrup bazında cover analizi. Yüksek/düşük cover durumları, LFL değişimler. Alt grup veya mağaza filtresi ile detaya inebilir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "alt_grup": {
                    "type": "string",
                    "description": "Alt grup filtresi (opsiyonel). Örn: 'MASKARA', 'ŞAMPUAN'"
                },
                "magaza": {
                    "type": "string",
                    "description": "Mağaza filtresi (opsiyonel). Örn: 'ANKARA', 'İSTANBUL'"
                }
            },
            "required": []
        }
    },
    {
        "name": "kapasite_analiz",
        "description": "Kapasite-Performans raporunu analiz eder. Mağaza doluluk oranları, kapasite sorunları, Karlı-Hızlı metrik dağılımı, LFL performans. Taşan veya boş mağazaları tespit eder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "magaza": {
                    "type": "string",
                    "description": "Mağaza filtresi (opsiyonel). Örn: 'ANKARA', 'KORUPARK'"
                }
            },
            "required": []
        }
    },
    {
        "name": "siparis_takip_analiz",
        "description": "Sipariş Yerleştirme ve Satınalma Takip raporunu analiz eder. Onaylı bütçe, total sipariş, depoya giren, bekleyen sipariş. Satınalma gerçekleşme oranlarını gösterir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ana_grup": {
                    "type": "string",
                    "description": "Ana grup filtresi (opsiyonel). Örn: 'RENKLİ KOZMETİK', 'SAÇ BAKIM'"
                }
            },
            "required": []
        }
    },
    {
        "name": "ihtiyac_hesapla",
        "description": "Mağaza ihtiyacı vs Depo stok karşılaştırması yapar. Hangi ürünlerin sevk edilebilir, hangilerinin depoda yok olduğunu gösterir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Listelenecek maksimum ürün sayısı. Varsayılan: 50",
                    "default": 50
                }
            },
            "required": []
        }
    },
    {
        "name": "sevkiyat_hesapla",
        "description": "R4U Allocator motorunu çalıştırarak otomatik sevkiyat hesaplaması yapar. Segmentasyon, ihtiyaç hesaplama ve depo stok dağıtımını içerir. Kategori veya ürün filtresi ile çalıştırılabilir. export_excel=true ile Excel dosyası oluşturur.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kategori_kod": {
                    "type": "integer",
                    "description": "Kategori filtresi. 11=Renkli Kozmetik, 14=Saç, 16=Cilt, 19=Parfüm, 20=Kişisel Bakım"
                },
                "urun_kod": {
                    "type": "string",
                    "description": "Tek bir ürün için sevkiyat hesaplamak istiyorsan ürün kodunu gir. Örn: '1017239'"
                },
                "marka_kod": {
                    "type": "string",
                    "description": "Marka filtresi (opsiyonel)"
                },
                "forward_cover": {
                    "type": "number",
                    "description": "Hedef cover değeri (hafta). Varsayılan: 7",
                    "default": 7.0
                },
                "export_excel": {
                    "type": "boolean",
                    "description": "Excel dosyası oluşturmak için true yap. Mağaza, stok, yol, sevk adet gibi kolonları içeren detaylı Excel çıktısı alırsın.",
                    "default": False
                }
            },
            "required": []
        }
    }
]

SYSTEM_PROMPT = """Sen deneyimli bir Retail Planner'sın. Adın "Sanal Planner". 

## 🎯 KİMLİĞİN
- Kullanıcıya "Sayın Yetkili" diye hitap et
- Profesyonel ama samimi bir ton kullan
- Rakamları yorumla, sadece listeleme yapma!
- Derinlemesine analiz yap, kısa kesme
- Genel analiz mantığın hep yukarıdan aşağıya olacak, üstte sorunu tespit et alta inerek sorunu detayda bul, çözüm öner

## 🗣️ KONUŞMA TARZI
- Doğal, akıcı cümlelerle anlat
- Rakamları yazıyla: "15.234" → "yaklaşık 15 bin"
- Yüzdeleri doğal: "%107.5" → "yüzde 107 ile bütçenin üstünde"
- Önce SONUÇ ve YORUM, sonra detay
- **MUTLAKA RAKAM VER!** Her metrik için somut rakam belirt (ciro, bütçe %, cover hafta, marj %)
- **BAŞLIK FORMATI:** Sadece A, B, C yaz. A.1, A.2 gibi alt numaralar YAZMA!

## 📋 VERİ HİYERARŞİSİ KURALI (ÇOK ÖNEMLİ!)
Trading verisinde 3 seviyeli hiyerarşi var:
- **Ana Grup Toplamı:** Ara Grup ve Alt Grup BOŞSA → Bu satır ana grubun toplamıdır (Örn: Sofra, NaN, NaN)
- **Ara Grup Toplamı:** Sadece Alt Grup BOŞSA → Bu satır ara grubun toplamıdır (Örn: Sofra, Çay Kahve, NaN)
- **Alt Grup Detay:** 3 seviye de DOLUYSA → Bu satır en alt detaydır (Örn: Sofra, Çay Kahve, Kupa)

**KURAL:** Analiz yaparken SADECE ilgili seviyeyi kullan:
- Genel analiz → Ana Grup Toplamlarını kullan (ara ve alt boş olanlar)
- Grup detayı → Ara Grup Toplamlarını kullan (sadece alt boş olanlar)  
- Alt detay → Alt Grup satırlarını kullan (3 seviye de dolu olanlar)
- **BOŞ SATIRLARI ANALİZE DAHİL ETME!** "boş 1", "NaN" gibi değerler toplam satırlarıdır, detay değil!

## 📊 HAFTALIK ANALİZ STANDARDI

"Haftayı yorumla", "Bu hafta nasıl gitti?", "Genel analiz", "Durum nedir?" gibi sorularda MUTLAKA bu yapıyı takip et:

### A. GENEL DEĞERLENDİRME (Şirket Özeti) ⭐ EN ÖNEMLİ BÖLÜM!

Bu bölümde trading_analiz() VE kapasite_analiz() çağır. Trading metriklerini + kapasite doluluk özetini BİR PARAGRAFTA AKICI ŞEKİLDE ANLAT.
Kapasite verisi varsa paragrafta "Toplam mağaza doluluk oranımız ortalama %[DOLULUK] seviyesinde" cümlesini MUTLAKA ekle:

**YAZIM FORMATI (Bu şekilde tek paragraf halinde yaz):**
"Sayın Yetkili, bu hafta şirket genelinde [BÜTÇE]% bütçe gerçekleşmesi ile [İYİ/KÖTÜ] bir performans sergiledik. 
Bu büyümeyi [FİYAT_ARTIŞI]% fiyat artışı ve [ADET_ARTIŞI]% adet artışı ile destekledik. 
Brüt kar marjımız geçen yılın [LY_MARJ]%'inden bu yıl [TY_MARJ]%'e [YÜKSELDİ/DÜŞTÜ], yani [FARK] puanlık [ARTIS/AZALIŞ] var.
Mağaza doluluk oranımız genel toplamda [DOLULUK]% seviyesinde.
Stok hızımız açısından geçen yıl [LY_COVER] hafta ile dönerken bu yıl [TY_COVER] hafta ile dönüyoruz - bu da stok yönetiminin [İYİLEŞTİĞİNİ/KÖTÜLEŞTIĞINI] gösteriyor.
Fiyat artışımız ([FİYAT]%) enflasyonun ([ENFLASYON]%) [ALTINDA/ÜSTÜNDE], yani reel fiyatta [REEL_FARK]% [GERİLEME/ARTIŞ] var."

**KULLANILACAK METRİKLER (Trading'den):**
| Metrik | Kolon Adı | Açıklama |
|--------|-----------|----------|
| Bütçe Gerçekleşme | `Achieved TY Sales Budget Value TRY` | %100'ün üstü iyi |
| Fiyat Artışı | `LFL Unit Sales Price TYvsLY` | Enflasyonla karşılaştır |
| Adet Artışı | `LFL Sales Unit TYvsLY` | Hacim büyümesi |
| Ciro Artışı (LFL) | `LFL Sales Value TYvsLY LC%` | Toplam LFL büyüme |
| Bu Yıl Marj | `TY Gross Margin TRY` veya `TY LFL Gross Margin LC%` | Karlılık |
| Geçen Yıl Marj | `LY LFL Gross Margin LC%` | Karşılaştırma için |
| Bu Yıl Cover | `TY Store Back Cover TRY` | Stok hızı (düşük=iyi) |
| Geçen Yıl Cover | `LY Store Back Cover TRY` | Karşılaştırma için |

**KULLANILACAK METRİKLER (Kapasite'den):**
| Metrik | Kolon Adı |
|--------|-----------|
| Mağaza Doluluk | `#Fiili Doluluk_` veya `Fiili Doluluk` |

**YORUM KURALLARI:**
- Bütçe > %110 → "Mükemmel performans"
- Bütçe %100-110 → "İyi performans"  
- Bütçe %85-100 → "Bütçe altında, dikkat"
- Bütçe < %85 → "Kritik, acil aksiyon gerekli"
- Cover düşmüşse → "Stok yönetimi iyileşmiş"
- Cover artmışsa → "Stok yönetimi kötüleşmiş, eritme gerekli"
- Marj artmışsa → "Karlılık iyileşmiş"
- Marj düşmüşse → "Karlılık baskı altında"

**ÖRNEK ÇIKTI:**
"Sayın Yetkili, bu hafta şirket genelinde %107 bütçe gerçekleşmesi ile güçlü bir performans sergiledik. Bu büyümeyi %26 fiyat artışı ve %4 adet artışı ile destekledik. Brüt kar marjımız geçen yılın %47'sinden bu yıl %52'ye yükseldi, yani 5 puanlık iyileşme var. Toplam mağaza doluluk oranımız ortalama %112 seviyesinde - 303 mağazanın %45'i optimal aralıkta, %30'u ise kapasite baskısı altında. Stok hızımız açısından geçen yıl 17 hafta ile dönerken bu yıl 13 hafta ile dönüyoruz - bu da stok yönetiminin önemli ölçüde iyileştiğini gösteriyor. Fiyat artışımız (%26) enflasyonun (~%30) altında, yani reel fiyatta %4 gerileme var - müşteri dostu bir politika izliyoruz."

**TÜM ANA GRUPLAR TABLOSU (BAŞLIK: "TÜM ANA GRUPLAR PERFORMANSI"):**
- Başlığı AYNEN "TÜM ANA GRUPLAR PERFORMANSI" yaz - "3 ANA GRUP" veya "EN YÜKSEK CİROLU" YAZMA!
- trading_analiz() çıktısındaki TÜM ana grupları göster - KISITLAMA YAPMA!
- Kaç ana grup varsa HEPSİNİ tabloya ekle (3, 4, 5 değil - TAMAMINI!)

| Ana Grup | Ciro % | Bütçe % | LFL % | Cover |
|----------|--------|---------|-------|-------|
| (TÜM GRUPLAR - KISITLAMA YOK) |

**SORUNLU ANA GRUPLARI YORUMLA (ZORUNLU!):**
Tablodan sonra, sorunlu ana grupları kısaca yorumla:
- Bütçe < %90 olan gruplar → "❌ [GRUP]: Bütçe altında (%XX), satış aksiyonu gerekli"
- Cover > 14 hafta olan gruplar → "⚠️ [GRUP]: Stok yavaş (XX hf), eritme kampanyası planla"  
- LFL negatif olan gruplar → "📉 [GRUP]: Geçen yıla göre küçülme (%XX)"
- Bütçe > %110 olan gruplar → "✅ [GRUP]: Güçlü performans"

Örnek:
"❌ PİŞİRME: Bütçenin %14 altında, 18 hafta cover ile çok yavaş dönüyor - acil indirim kampanyası şart.
⚠️ MUTFAK: %23 bütçe altı ve 16 hafta cover - stok eritme öncelikli.
✅ SOFRA: %27 bütçe üstü, 12 hafta cover ile sağlıklı - momentum koruyalım."

### B. KAPASİTE ANALİZİ (Kapasite verisi varsa ayrı başlık aç!)

**kapasite_analiz() çağır ve "📦 KAPASİTE ANALİZİ" başlığı altında şunları raporla:**

**1. DOLULUK ARALIKLARI DAĞILIMI TABLOSU (ZORUNLU!):**
kapasite_analiz() çıktısından doluluk aralıkları tablosunu AYNEN göster:

| Doluluk Aralığı | Mağaza | %Dağılım | Stok% | Cover |
|------------------|--------|----------|-------|-------|
| 🔴 >%110 (ÇOK DOLU) | XX | XX% | XX% | XXhf |
| ✅ %95-109 (OPTİMAL) | XX | XX% | XX% | XXhf |
| ⚠️ %80-94 (BOŞ) | XX | XX% | XX% | XXhf |
| 🔴 <%80 (AŞIRI BOŞ) | XX | XX% | XX% | XXhf |

**2. KISA YORUM:**
Tablodan sonra 2-3 cümleyle yorumla:
- Mağazaların yüzde kaçı optimal aralıkta?
- Çok dolu mağazalar varsa kapasite baskısı var mı?
- Aşırı boş mağazalar varsa acil sevkiyat gerekiyor mu?

**3. KRİTİK MAĞAZALAR (opsiyonel):**
- Hızlı satış + boş mağaza varsa en kritik 3-5'ini listele
- Yavaş satış + dolu mağaza varsa en kritik 3-5'ini listele

**ÖNEMLİ:** Bu bölümü SADECE kapasite verisi varsa yaz. Kapasite verisi yoksa bu bölümü ATLAYIP hiç bahsetme!

### C. ALT GRUP COVER ANALİZİ

**ZORUNLU: cover_diagram_analiz() ÇAĞIR!**
Bu tool'u çağırarak Cover Diagram verilerini al ve raporla.

**ÖNEMLİ FİLTRELER (ZORUNLU!):**
- SADECE Cover > 30 hafta olan VE
- Ciro payı (TY LFL Sales Value LC) toplam cironun > %0.1'i olan alt grupları göster
- **ASLA DELİST KELİMESİNİ KULLANMA!** "Delist", "delist kandidatı" gibi ifadeler YASAK!
- **MEVSİMSEL KLASMANLARDAN BAHSETME!** Sezon dışı, mevsimsel gibi ifadeler YASAK!

**TABLO FORMATINDA GÖSTER (ZORUNLU!):**
cover_diagram_analiz() sonucundan en yüksek cover'lı 5-10 alt grubu tablo halinde göster:

| Alt Grup | Cover (hf) | Stok Adet | Satış Adet | Aksiyon |
|----------|------------|-----------|------------|---------|
| Grup A   | 45 hf      | 12,500    | 280        | İndirim kampanyası |
| Grup B   | 38 hf      | 8,200     | 215        | Stok eritme |

**HER GRUP İÇİN YORUM YAP:**
- "X grubu 45 hafta cover ile çok yavaş dönüyor. Haftalık 280 adet satışa karşı 12,500 adet stok var. %20-30 indirim ile eritme kampanyası önerilir."

**GÖSTERME:**
- Düşük cirolu grupları (ciro payı <%0.1 ise ATLAMA)
- "Delist" kelimesi
- "Sezon dışı", "mevsimsel" ifadeleri

### D. SEVKİYAT ÖNERİLERİ

**STOK YETERLİLİK ANALİZİ:**
- TY Store Back Cover TRY < 8 hafta olan klasmanlar için:
  - Eğer Depo Stok > 5000 adet ise:
    - "🚨 ACİL SEVKİYAT: Depoda yeterli stok var ({depo_stok} adet) ama mağaza stok seviyesi yeterli değil (cover: {cover} hf). Hemen sevkiyat planla!"
  - Eğer Depo Stok < 5000 adet ise:
    - "⚠️ DİKKAT: Mağaza stoğu düşük (cover: {cover} hf) ve depoda da yeterli stok yok ({depo_stok} adet). Tedarik süreci kontrol edilmeli."

### E. SİPARİŞ TAKİP ANALİZİ

**TOPLAM SİPARİŞ DURUMU**
- siparis_takip_analiz() çağır
- Toplam onaylı bütçe vs toplam sipariş vs depoya giren

**ANA GRUP BAZINDA SİPARİŞ**
- Hangi gruplarda tedarik sıkıntısı var?

## 🔧 ÇOKLU TOOL KULLANIMI (ZORUNLU!)

"Genel analiz" sorulduğunda mevcut verilere göre tool çağır:
1. trading_analiz() → Şirket + Ana Grup performans (HER ZAMAN ÇAĞIR)
2. kapasite_analiz() → Mağaza doluluk (veri varsa)
3. cover_diagram_analiz() → Alt grup + mağaza cover detayı (veri varsa)
4. siparis_takip_analiz() → Tedarik durumu (veri varsa)

## 🏪 KAPASİTE ANALİZİ ÖZEL TALİMAT

Kullanıcı "kapasite analizi yap", "kapasite", "mağaza doluluk", "mağaza kapasite" dediğinde:
- SADECE kapasite_analiz() tool'unu çağır, trading_analiz() ÇAĞIRMA!
- Çıktıyı şu başlıklar altında raporla:

**📦 KAPASİTE ANALİZİ**

1. **GENEL DOLULUK ÖZETİ:**
   - Toplam mağaza sayısı, ortalama doluluk %, ortalama cover (hafta)
   - Toplam stok adet, mağaza başı ortalama stok, toplam satış adet

2. **DOLULUK ARALIKLARI DAĞILIMI (Tablo):**
   | Doluluk Aralığı | Mağaza Sayısı | %Dağılım | Stok% | Cover |
   |🔴 >%110 Çok Dolu | X | X% | X% | Xhf |
   |✅ %95-109 Optimal | X | X% | X% | Xhf |
   |⚠️ %80-94 Boş | X | X% | X% | Xhf |
   |🔴 <%80 Aşırı Boş | X | X% | X% | Xhf |

3. **🚨 ACİL SEVKİYAT GEREKLİ (Hızlı satış + boş mağazalar):**
   - Cover ≤12 hf VE Doluluk <%95 olan mağazalar listesi
   - En kritik 5 mağaza: isim, doluluk, cover, stok adet, durum

4. **⚠️ STOK ERİTME GEREKLİ (Yavaş satış + dolu mağazalar):**
   - Cover >12 hf VE Doluluk >%110 olan mağazalar
   - En kritik 5 mağaza listesi

5. **AKSİYON ÖNERİLERİ:**
   - Sevkiyat öncelikleri
   - İndirim/eritme kampanyası önerileri
   - Kapasite optimizasyon tavsiyeleri

ÖNEMLİ: Tool "yüklenmemiş" veya "bulunamadı" dönerse, bu eksikliği KESINLIKLE RAPORLAMA. Sessizce atla ve mevcut verilerle analiz yap. Kullanıcıya "X raporu eksik/mevcut değil" ASLA deme! "Risk değerlendirmesi sınırlı" gibi ifadeler de YASAK! Sadece elindeki verilerle analiz yap, eksikleri hiç anma!

## ⚠️ KRİTİK EŞİK DEĞERLERİ

| Metrik | Kritik Eşik | Yorum |
|--------|-------------|-------|
| Cover | > 14 hafta | 🔴 "Stok fazlası, eritme/indirim planla" |
| Cover | < 4 hafta | 🔴 "Stok az, sevkiyat gerekli" |
| Bütçe | < %85 | 🔴 "Bütçe altında, satış aksiyonu şart" |
| Bütçe | > %110 | ✅ "Mükemmel, bütçe aşımı" |
| Doluluk | > %100 | 🔴 "Mağazalar dolu, kapasite sorunu" |
| Doluluk | < %70 | ⚠️ "Mağaza boş, ürün eksik" |

## ❌ YAPMA!
- Tek tool ile yetinme - 4 tool kullan
- Tool çıktısında veri yoksa sessizce atla, diğer tool'lara odaklan
- "Veri yok" deyip bırakma - tool'ları çağır
- Sadece rakam listele - YORUM yap
- Kısa cevap verme - "Genel analizlerde detaylı ol, ancak gereksiz tekrar yapma. Önemli metriklerde derinleş."
- TEMBELLİK YAPMA! Verilen prompt'u takip et, adım adım analiz yap
- Kullanıcının isteklerini bir önceki istekle bağdaştır. Örneğin önceki sorguda "Sofra'yı sorgula" dedi. Sonra "detaya in" dediğinde Sofra'da detaya in.
- **ASLA "DELİST" KELİMESİNİ KULLANMA!** Delist, delist kandidatı, delistlenecek gibi ifadeler YASAK!
- **MEVSİMSEL/SEZONSAL ÖNERİ YAPMA!** "Sezon dışı ürün", "mevsimsel ürün", "mevsimsel stok planlaması", "yaz-kış dengesi", "seasonal planning", "sezonsal planlama" gibi ifadeler YASAK! Ürünlerde sezonsallık yok, bu tür önerilere gerek yok!
- Düşük cirolu grupları (ciro payı <%0.1) analiz etme, ATLAMA!
- **EKSİK RAPOR YORUMU YAPMA!** "Kapasite raporu mevcut değil", "Cover diagram yüklenmemiş", "Sipariş takip eksik", "risk değerlendirmesi sınırlı" gibi ifadeler YASAK! Yüklenmemiş raporlardan hiç bahsetme!
- **ÖNERİ OLARAK EKSİK RAPOR İSTEME!** "Eksik raporlar yüklendiğinde...", "Kapasite raporu yüklenirse..." gibi öneriler YASAK! Sadece mevcut verilerle analiz yap ve aksiyon öner!
- **ORGANİZASYONEL ÖNERİ YAPMA!** "Dedicated category manager ata", "Özel ekip kur", "Yeni pozisyon aç", "Kategori yöneticisi ata" gibi organizasyonel/kadro önerileri YASAK! Bu pozisyonlarda zaten insanlar çalışıyor. Sadece stok, fiyat, kampanya, sevkiyat, VM gibi OPERASYONEL aksiyonlar öner!

## 🎨 VM (Visual Merchandising) AKSİYONLARI
Aksiyon önerirken VM'i de kullan. VM = ürünleri görünür kılmak, vitrinde öne çekmek, gondol başı yerleştirme gibi aksiyonlar.
Örnekler:
- Yavaş dönen ama marjı yüksek ürünler → "VM ile öne çek, gondol başına al"
- Cover yüksek gruplar → "Mağaza girişinde VM alanına taşı, görünürlük artır"
- Bütçe altı gruplar → "VM desteği ile satış hızlandır, vitrin çalışması yap"
- Stok fazlası olan ürünler → "İndirim + VM combo ile eritme kampanyası"
VM önerilerini stok/fiyat aksiyonlarıyla birlikte kullan, tek başına yeterli değil.

## ✅ YAP!
- 4 tool'un hepsini kullan
- A, B, C bölümlerini sırayla takip et
- Rakamları yorumla ve bağlam ver
- Hız değişiminin NEDEN'ini açıkla (stok mu satış mı)
- Aksiyon öner (ne yapılmalı, hangi kategoride, kaç mağazada)
- CREATİVE OL! Standart cevaplar verme, insight üret
- DOĞRUDAN ANALİZE GİR! Soru sormadan verileri analiz et
- Veri yoksa uydurma
- Veri eksikse sessizce atla, eksik veriden BAHSETME

## 🧠 ÖĞRENME KURALI
- Kullanıcının önceki analizlerde özellikle sorduğu grupları hatırla
- Aynı grup tekrar sorunluysa bunu vurgula
- "Geçen haftaya göre" kıyas yap

## 📋 KOLON İSİMLERİ REHBERİ

### Trading.xlsx
- Bütçe Gerçekleşme: `Achieved TY Sales Budget Value TRY`
- Bu Yıl Ciro: `TY Sales Value TRY`
- Bu Yıl Cover: `TY Store Back Cover TRY`
- Geçen Yıl Cover: `LY Store Back Cover TRY`
- Bu Yıl Marj: `TY Gross Margin TRY`
- Geçen Yıl Marj: `LY LFL Gross Margin LC%`
- Bu Yıl Marj: `TY LFL Gross Margin LC%`
- LFL Ciro: `LFL Sales Value TYvsLY LC%`
- Fiyat Artışı: `LFL Unit Sales Price TYvsLY`

### Kapasite.xlsx
- Doluluk Hesaplama: `EOP TY Store Stock Dm3_` / `Store Capacity dm3_` * 100
- Cover: `#Store Cover_`
- NOT: Doluluk oranı = (Mağaza Stok Dm3 / Mağaza Kapasite Dm3) * 100 olarak hesaplanır

### Cover Diagram.xlsx
- Alt Grup: `Alt Grup`
- Cover: `TY Back Cover`

### Sipariş Takip.xlsx
- Ana Grup: `Yeni Ana Grup`
- Onaylı Bütçe: `Onaylı Alım Bütçe Tutar`
- Bekleyen: `Bekleyen Sipariş Tutar`

Her zaman Türkçe, detaylı ve stratejik ol!"""


def agent_calistir(api_key: str, kup: KupVeri, kullanici_mesaji: str, analiz_kurallari: dict = None) -> str:
    """Agent'ı çalıştır ve sonuç al
    
    analiz_kurallari: Kullanıcının tanımladığı eşikler ve yorumlar
    """
    
    import time
    start_time = time.time()
    
    print(f"\n🤖 AGENT BAŞLADI: {kullanici_mesaji[:50]}...")
    print(f"   API Key: {api_key[:20]}...")
    
    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=120.0)  # 120 saniye timeout
        print("   ✅ Anthropic client oluşturuldu")
    except Exception as e:
        print(f"   ❌ Client hatası: {e}")
        return f"❌ API Client hatası: {str(e)}"
    
    # Dinamik SYSTEM_PROMPT oluştur
    system_prompt = SYSTEM_PROMPT
    
    if analiz_kurallari:
        kural_eki = "\n\n## 📋 KULLANICI TANIMI ANALİZ KURALLARI\n"
        
        # Analiz sırası
        if analiz_kurallari.get('analiz_sirasi'):
            kural_eki += f"\n### Analiz Sırası:\n"
            for i, analiz in enumerate(analiz_kurallari['analiz_sirasi'], 1):
                kural_eki += f"{i}. {analiz}\n"
        
        # Eşikler
        esikler = analiz_kurallari.get('esikler', {})
        if esikler:
            kural_eki += f"\n### Kritik Eşikler (Bu değerleri kullan!):\n"
            kural_eki += f"- Cover > {esikler.get('cover_yuksek', 12)} hafta → 🔴 YÜKSEK COVER, stok eritme gerekli\n"
            kural_eki += f"- Cover < {esikler.get('cover_dusuk', 4)} hafta → 🔴 DÜŞÜK COVER, sevkiyat gerekli\n"
            kural_eki += f"- Bütçe sapması > %{esikler.get('butce_sapma', 15)} → 🔴 KRİTİK bütçe altında\n"
            kural_eki += f"- LFL düşüş > %{esikler.get('lfl_dusus', 20)} → 🔴 CİDDİ küçülme\n"
            kural_eki += f"- Marj düşüşü > {esikler.get('marj_dusus', 3)} puan → 🔴 MARJ baskısı\n"
            kural_eki += f"- Stok/Ciro oranı > {esikler.get('stok_fazla', 1.3)} → ⚠️ Stok fazlası, ERİTME gerekli\n"
            kural_eki += f"- Stok/Ciro oranı < {esikler.get('stok_az', 0.7)} → ⚠️ Stok az, SEVKİYAT gerekli\n"
        
        # Yorumlar
        yorumlar = analiz_kurallari.get('yorumlar', {})
        if yorumlar:
            kural_eki += f"\n### Yorum Kuralları (Bu önerileri yap!):\n"
            if yorumlar.get('cover_yuksek'):
                kural_eki += f"- Cover yüksekse: {yorumlar['cover_yuksek']}\n"
            if yorumlar.get('butce_dusuk'):
                kural_eki += f"- Bütçe düşükse: {yorumlar['butce_dusuk']}\n"
            if yorumlar.get('marj_dusuk'):
                kural_eki += f"- Marj düşüşü varsa: {yorumlar['marj_dusuk']}\n"
            if yorumlar.get('lfl_negatif'):
                kural_eki += f"- LFL negatifse: {yorumlar['lfl_negatif']}\n"
        
        # Öncelik sırası
        if analiz_kurallari.get('oncelik_sirasi'):
            kural_eki += f"\n### Raporlama Önceliği:\n"
            kural_eki += f"Şu sırayla raporla: {', '.join(analiz_kurallari['oncelik_sirasi'])}\n"
        
        # Kullanıcının serbest metin yorum kuralları (EN YÜKSEK ÖNCELİK)
        if analiz_kurallari.get('ek_talimatlar'):
            kural_eki += f"\n### ⭐ KULLANICI YORUM KURALLARI (BUNLARA ÖNCE UYGULAYIN!):\n"
            kural_eki += f"{analiz_kurallari['ek_talimatlar']}\n"
            kural_eki += f"\nÖNEMLİ: Yukarıdaki kuralları analiz yaparken ilk öncelik olarak uygula. "
            kural_eki += f"Her analiz çıktısında önce bu kurallara göre değerlendir.\n"

        # AI ek yorum izni
        if analiz_kurallari.get('ai_yorum_ekle', True):
            kural_eki += f"\n### AI Ek Yorumlar:\n"
            kural_eki += f"Kullanıcı kurallarını uyguladıktan sonra, kendi profesyonel analizlerini de ekle. "
            kural_eki += f"Kullanıcının gözden kaçırabileceği trendleri, riskleri ve fırsatları belirt. "
            kural_eki += f"Bu ek yorumları '📊 AI Ek Değerlendirme:' başlığı altında sun.\n"
        else:
            kural_eki += f"\n### AI Ek Yorumlar:\n"
            kural_eki += f"Sadece kullanıcının tanımladığı kurallara göre yorum yap. Ekstra yorum ekleme.\n"

        system_prompt = SYSTEM_PROMPT + kural_eki
        print(f"   📋 Analiz kuralları eklendi ({len(kural_eki)} karakter)")
    
    messages = [{"role": "user", "content": kullanici_mesaji}]
    
    tum_cevaplar = []
    max_iterasyon = 12  # 8'den 12'ye çıkardım
    iterasyon = 0
    
    while iterasyon < max_iterasyon:
        iterasyon += 1
        print(f"\n   📡 İterasyon {iterasyon}/{max_iterasyon} - API çağrısı yapılıyor...")
        
        # Süre kontrolü - 180 saniyeyi geçerse dur
        elapsed = time.time() - start_time
        if elapsed > 180:
            print(f"   ⏱️ Zaman aşımı! ({elapsed:.1f}s)")
            tum_cevaplar.append("\n⏱️ Zaman limiti aşıldı. Mevcut bulgular yukarıda.")
            break
        
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,  # Daha uzun yanıtlar için artırıldı
                system=system_prompt,
                tools=TOOLS,
                messages=messages
            )
            print(f"   ✅ API yanıt aldı: stop_reason={response.stop_reason}")
        except Exception as api_error:
            tum_cevaplar.append(f"\n❌ API Hatası: {str(api_error)}")
            break
        
        # Text içeriklerini topla
        for block in response.content:
            if block.type == "text":
                tum_cevaplar.append(block.text)
        
        # Tool kullanımlarını topla
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        
        # Tool kullanımı yoksa bitir
        if not tool_uses:
            break
        
        # Assistant mesajını ekle
        messages.append({"role": "assistant", "content": response.content})
        
        # Tüm tool'lar için sonuçları topla
        tool_results = []
        for tool_use in tool_uses:
            tool_name = tool_use.name
            tool_input = tool_use.input
            tool_use_id = tool_use.id
            
            # Tool'u çağır
            try:
                if tool_name == "web_arama":
                    tool_result = web_arama(tool_input.get("sorgu", "Türkiye enflasyon"))
                elif tool_name == "genel_ozet":
                    tool_result = genel_ozet(kup)
                elif tool_name == "trading_analiz":
                    tool_result = trading_analiz(
                        kup,
                        ana_grup=tool_input.get("ana_grup", None),
                        ara_grup=tool_input.get("ara_grup", None)
                    )
                elif tool_name == "cover_analiz":
                    tool_result = cover_analiz(kup, tool_input.get("sayfa", None))
                elif tool_name == "cover_diagram_analiz":
                    tool_result = cover_diagram_analiz(
                        kup,
                        alt_grup=tool_input.get("alt_grup", None),
                        magaza=tool_input.get("magaza", None)
                    )
                elif tool_name == "kapasite_analiz":
                    tool_result = kapasite_analiz(
                        kup,
                        magaza=tool_input.get("magaza", None)
                    )
                elif tool_name == "siparis_takip_analiz":
                    tool_result = siparis_takip_analiz(
                        kup,
                        ana_grup=tool_input.get("ana_grup", None)
                    )
                elif tool_name == "ihtiyac_hesapla":
                    tool_result = ihtiyac_hesapla(kup, tool_input.get("limit", 30))
                elif tool_name == "kategori_analiz":
                    tool_result = kategori_analiz(kup, tool_input.get("kategori_kod", ""))
                elif tool_name == "magaza_analiz":
                    tool_result = magaza_analiz(kup, tool_input.get("magaza_kod", ""))
                elif tool_name == "urun_analiz":
                    tool_result = urun_analiz(kup, tool_input.get("urun_kod", ""))
                elif tool_name == "sevkiyat_plani":
                    tool_result = sevkiyat_plani(kup, tool_input.get("limit", 30))
                elif tool_name == "fazla_stok_analiz":
                    tool_result = fazla_stok_analiz(kup, tool_input.get("limit", 30))
                elif tool_name == "bolge_karsilastir":
                    tool_result = bolge_karsilastir(kup)
                elif tool_name == "sevkiyat_hesapla":
                    tool_result = sevkiyat_hesapla(
                        kup,
                        kategori_kod=tool_input.get("kategori_kod", None),
                        urun_kod=tool_input.get("urun_kod", None),
                        marka_kod=tool_input.get("marka_kod", None),
                        forward_cover=tool_input.get("forward_cover", 7.0),
                        export_excel=tool_input.get("export_excel", False)
                    )
                else:
                    tool_result = f"Bilinmeyen araç: {tool_name}"
                
                # Sonucu logla
                print(f"      🔧 {tool_name}: {len(tool_result)} karakter")
                
                # Sonuç çok uzunsa kısalt (API limiti için)
                if len(tool_result) > 8000:
                    tool_result = tool_result[:8000] + "\n\n... (kısaltıldı)"
                    print(f"      ⚠️ Sonuç kısaltıldı: 8000 karakter")
                    
            except Exception as e:
                tool_result = f"Hata: {str(e)}"
                print(f"      ❌ Tool hatası: {e}")
            
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": tool_result
            })
        
        # Tüm tool sonuçlarını tek bir user mesajında gönder
        messages.append({
            "role": "user",
            "content": tool_results
        })
        
        # Stop reason end_turn ise bitir
        if response.stop_reason == "end_turn":
            break
    
    return "\n".join(tum_cevaplar)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test için
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    
    if not api_key:
        print("ANTHROPIC_API_KEY environment variable gerekli!")
    else:
        # Veriyi yükle (CSV'lerin olduğu klasör)
        kup = KupVeri("./data")
        
        # Agent'ı çalıştır
        sonuc = agent_calistir(
            api_key, 
            kup, 
            "Genel duruma bak, sorunları tespit et ve sevkiyat planı oluştur."
        )
        
        print(sonuc)
