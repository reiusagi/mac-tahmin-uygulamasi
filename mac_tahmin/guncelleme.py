"""Verilerin kendini güncel tutması: canlı skorlar ve süren sezonun verisi arka planda, belli aralıklarla yenilenir.
Uygulama (NiceGUI arayüzü) bunu açılışta başlatır; komut satırı da kullanabilir."""
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from . import avrupa, karne, lig_maclari, milli, veri
from .canli import canli_skorlar
from .sezon import LIGLER, SON_SEZON
from .stadyum import stadyum_oku, stadyumlar_indir


YAKIN_GUN_DK = 30  # önümüzdeki günlerin maç listesinin yenilenme aralığı (dakika)
BITIS_BEKLE_SN = 300  # maç bitince ligin/turnuvanın verisi bu kadar sonra yenilenir (aynı aralıkta bitenler birlikte)
SON_YENILEME = 'son_yenileme.txt'  # d/ altında: süren sezonun son başarılı tam yenilemesinin işareti (zamanı)
# önbellek temizliği: ham/ altındaki bu klasörlerde, bu kadar günden eski dosyalar silinir (hepsi gerekirse yeniden
# indirilir). takim/oyuncu: 1-6 saat geçerli sayfalar; mac: hakem ve stadyum; mac_tam: bitmiş maç ayrıntıları (haftanın
# 11'i ve form endeksi yalnızca süren sezonu kullanır). Lig, kupa ve milli verisi aynı adla üzerine yazıldığı için birikmez.
ESKIME_GUN = {'takim': 7, 'oyuncu': 7, 'mac': 30, 'mac_tam': 400}
TEMIZLIK_SAAT = 24
SIMDI_ARALIK_SN = 60  # "Şimdi güncelle" en sık bu aralıkla çalışır (kaynak sitelere yük binmesin)
logger = logging.getLogger(__name__)


def onbellek_temizle(ham, yaz=None):
    """ham/ altındaki eskimiş önbellek dosyalarını siler. Döner: (silinen dosya sayısı, açılan yer, bayt)."""
    sayi = boyut = 0
    simdi = time.time()
    for klasor, gun in ESKIME_GUN.items():
        for f in (Path(ham) / klasor).glob('*.json'):
            try:
                st = f.stat()
                if simdi - st.st_mtime > gun * 86400:
                    f.unlink()
                    sayi += 1
                    boyut += st.st_size
            except OSError:
                pass  # o an başka bir iş yazıyor ya da okuyorsa sonraki temizliğe kalır
    if yaz and sayi:
        yaz(f'önbellek temizlendi: {sayi} eski dosya, {boyut / 1e6:.1f} MB')
    return sayi, boyut


class Guncelleyici:
    """canli: son canlı skor verisi (canli_skorlar çıktısı) ya da None. veri_surum: süren sezonun verisi her
    yenilendiğinde bir artar; arayüz bunu izleyip açık sezonu yeniden yükler."""

    def __init__(self, veri_klasoru, ham, canli_aralik=60, veri_saat=6, yaz=print):
        self.veri_klasoru, self.ham = Path(veri_klasoru), Path(ham)
        self.canli_aralik, self.veri_saat, self.yaz = canli_aralik, veri_saat, yaz
        self.canli = None
        self.canli_hata = None
        self.veri_surum = 0
        self.veri_yenileniyor = False
        self.son_veri = None  # süren sezon verisinin son yenilendiği an
        self._simdi = threading.Event()  # "şimdi güncelle" isteği
        self._son_simdi, self._simdi_kilit = None, threading.Lock()  # son kabul edilen isteğin zamanı (time.monotonic)
        self.dinleyiciler = []  # her yeni canlı skor verisinde çağrılır: f(canli)
        self._bekleyen, self._bekleyen_kilit = set(), threading.Lock()  # maçı biten, yenilenecek lig/turnuvalar

    def baslat(self):
        threading.Thread(target=self._canli_dongu, daemon=True).start()
        if self.veri_saat > 0:
            threading.Thread(target=self._sezon_dongu, daemon=True).start()
        threading.Thread(target=self._temizlik_dongu, daemon=True).start()
        return self

    def _temizlik_dongu(self):
        """Açılışta ve sonra günde bir kez eskimiş önbellek dosyalarını siler (klasör şişmesin)."""
        while True:
            try:
                onbellek_temizle(self.ham, lambda s: self.yaz(f'{datetime.now():%H:%M} {s}'))
            except Exception:
                logger.warning('önbellek temizliği başarısız', exc_info=True)
            time.sleep(TEMIZLIK_SAAT * 3600)

    def simdi_guncelle(self):
        """Süren sezonun verisini beklemeden yeniler (arayüzdeki düğme). Son istekten SIMDI_ARALIK_SN geçmediyse
        istek alınmaz ve False döner (simdi_kalan_sn: ne kadar beklenecek); alındıysa True."""
        with self._simdi_kilit:
            if self.simdi_kalan_sn():
                return False
            self._son_simdi = time.monotonic()
        self._simdi.set()
        return True

    def simdi_kalan_sn(self):
        """Yeni bir "şimdi güncelle" isteğinin kabul edilmesine kalan saniye (0: şimdi yapılabilir)."""
        if self._son_simdi is None:
            return 0
        return max(0, int(SIMDI_ARALIK_SN - (time.monotonic() - self._son_simdi) + 0.999))

    def _hata(self, ne, hata):
        """Durum satırına kısa (ayrıntısız) hata yazar; ayrıntı günlüğe gider."""
        logger.warning('%s', ne, exc_info=hata)
        self.yaz(f'{datetime.now():%H:%M} {ne}: {veri.hata_ozeti(hata)}')

    def _canli_dongu(self):
        """Bugünün skorları her turda; sonraki günlerin listesi (hakem atamaları için) YAKIN_GUN_DK'da bir yenilenir,
        arada önceki liste kullanılır (her dakika beş günü indirmemek için)."""
        son_yakin = 0
        while True:
            try:
                yakin = time.time() - son_yakin >= YAKIN_GUN_DK * 60 or not self.canli
                v = canli_skorlar(stadyumlar=stadyum_oku(self.veri_klasoru), ham=self.ham, yakin_gun=4 if yakin else 0)
                if yakin:
                    son_yakin = time.time()
                else:
                    v['yakinda'] = self.canli.get('yakinda', [])
                self._bitenleri_bul(self.canli, v)
                self.canli = v
                if self.canli_hata is not None:  # kesinti bitti: günlüğe bir kez
                    self.yaz(f'{datetime.now():%H:%M} canlı skor bağlantısı geri geldi')
                self.canli_hata = None
                for f in list(self.dinleyiciler):  # ör. favori takım bildirimleri
                    try:
                        f(v)
                    except Exception as e:
                        self._hata('canlı skor dinleyicisi hata verdi', e)
            except Exception as e:  # ağ hatasında uygulama çalışmaya devam etsin
                if self.canli_hata is None:  # kesinti boyunca dakikada bir değil, başlangıcında bir kez yazılır
                    self._hata('canlı skorlar alınamadı (bağlantı gelene kadar dakikada bir yeniden denenir)', e)
                self.canli_hata = veri.hata_ozeti(e)
            time.sleep(self.canli_aralik)

    def _bitenleri_bul(self, eski, yeni):
        """Az önce biten maçların ligi/turnuvası BITIS_BEKLE_SN sonra (aynı aralıkta bitenler birlikte) yenilenir."""
        if not eski:
            return
        once = {m['id']: m.get('durum') for m in eski.get('maclar') or []}
        biten = {m['lig'] for m in yeni.get('maclar') or [] if m.get('durum') == 'bitti' and once.get(m['id']) not in (None, 'bitti')}
        if not biten:
            return
        with self._bekleyen_kilit:
            ilk = not self._bekleyen
            self._bekleyen |= biten
        if ilk:
            threading.Timer(BITIS_BEKLE_SN, self._bitenleri_yenile).start()

    def _bitenleri_yenile(self):
        with self._bekleyen_kilit:
            anahtarlar, self._bekleyen = self._bekleyen, set()
        milli_t = {int(k.split('-')[1]) for k in anahtarlar if k.startswith('milli-')}
        avrupa_k = {int(k.split('-')[1]) for k in anahtarlar if k.startswith(('avrupa-', 'kupa-'))}
        ligler = [k for k in anahtarlar if not k.startswith(('milli-', 'avrupa-', 'kupa-'))]
        self.yaz(f'{datetime.now():%H:%M} biten maçlar için yenileniyor: {", ".join(sorted(anahtarlar))}')
        try:
            if milli_t:
                milli.indir(self.ham, self.veri_klasoru, zorla=milli_t)
            if avrupa_k:
                avrupa.indir(self.ham, self.veri_klasoru, zorla=avrupa_k)
            if ligler:
                veri.indir(ligler, [SON_SEZON], str(self.veri_klasoru), str(self.ham), yenile=True, yaz=lambda s: None)
                self.veri_surum += 1  # arayüz açık sezonu (verisi değiştiyse) yeniden kurar
                karne.guncelle(self.veri_klasoru)
                # biten maçların sayfaları hemen (Öne çıkanlar, roller açılınca beklemesin)
                lig_maclari.eksikleri_indir(ligler, str(self.ham), butce=20)
        except Exception as e:
            self._hata('biten maçların verisi yenilenemedi', e)

    def _yas_saat(self, yol):
        return (time.time() - yol.stat().st_mtime) / 3600 if yol.exists() else float('inf')

    def _yenileme_yasi(self, dosyalar):
        """Süren sezonun son başarılı tam yenilemesinden bu yana geçen saat. İşaret dosyası (SON_YENILEME) yoksa lig
        dosyalarının en eskisine bakılır. Lig dosyaları değişmedikçe yeniden yazılmadığı için (veri.indir) zamanı
        onlardan okunamaz."""
        isaret = self.veri_klasoru / SON_YENILEME
        return self._yas_saat(isaret) if isaret.exists() else max(self._yas_saat(f) for f in dosyalar)

    def _sezon_dongu(self):
        """Süren sezonun verisini (sonuçlar, puan durumu, oyuncular) belli aralıkla, stadyumları ayda bir yeniler."""
        dosyalar = [self.veri_klasoru / f'{l[0]}-{SON_SEZON}.json' for l in LIGLER]
        isaret = self.veri_klasoru / SON_YENILEME
        if isaret.exists():
            self.son_veri = datetime.fromtimestamp(isaret.stat().st_mtime)
        elif all(f.exists() for f in dosyalar):
            self.son_veri = datetime.fromtimestamp(min(f.stat().st_mtime for f in dosyalar))
        while True:
            istendi = self._simdi.is_set()
            self._simdi.clear()
            if istendi or self._yenileme_yasi(dosyalar) >= self.veri_saat:
                self.veri_yenileniyor = True
                self.yaz(f'{datetime.now():%H:%M} sezon verisi yenileniyor…')
                try:
                    hata = veri.indir(None, [SON_SEZON], str(self.veri_klasoru), str(self.ham), yenile=True,
                                      yaz=lambda s: None)
                    self.son_veri = datetime.now()
                    if not hata:  # alınamayan lig varsa işaret konmaz: 10 dk sonra yeniden denenir
                        isaret.write_text(self.son_veri.isoformat(timespec='seconds'), encoding='utf-8')
                    self.veri_surum += 1
                    karne.guncelle(self.veri_klasoru)  # biten maçlar tahmin karnesine
                    self.yaz(f'{datetime.now():%H:%M} sezon verisi yenilendi' + (f' ({hata} lig alınamadı)' if hata else ''))
                except Exception as e:
                    self._hata('sezon verisi yenilenemedi', e)
                finally:
                    self.veri_yenileniyor = False
            # milli turnuvalar ve Avrupa kupaları: süren sezonlar 6 saatte bir ("şimdi güncelle"de hemen), eksik sezonlar bir kez
            zorla = True if istendi else ()
            try:
                milli.indir(self.ham, self.veri_klasoru, yenile_guncel=True, zorla=zorla)
            except Exception as e:
                self._hata('milli takım verisi alınamadı', e)
            try:
                avrupa.indir(self.ham, self.veri_klasoru, yenile_guncel=True, zorla=zorla)
            except Exception as e:
                self._hata('Avrupa kupaları verisi alınamadı', e)
            if self._yas_saat(self.veri_klasoru / 'stadyumlar.json') >= 30 * 24:
                try:
                    stadyumlar_indir(str(self.veri_klasoru), str(self.ham), yenile=True, yaz=lambda s: None)
                except Exception as e:
                    self._hata('stadyumlar alınamadı', e)
            # ön indirme: biten maçların henüz inmemiş sayfaları, her turda bir parti (en yenisinden); "şimdi güncelle"
            # istenirse yarıda bırakılır
            try:
                n = lig_maclari.eksikleri_indir([l[0] for l in LIGLER], str(self.ham), durdur=self._simdi.is_set)
                if n:
                    self.yaz(f'{datetime.now():%H:%M} {n} maç sayfası önceden indirildi')
            except Exception as e:
                self._hata('maç sayfaları önceden indirilemedi', e)
            self._simdi.wait(600)  # on dakikada bir bakar; "şimdi güncelle" beklemeyi keser
