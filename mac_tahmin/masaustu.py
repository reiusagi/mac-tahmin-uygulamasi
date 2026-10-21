"""Masaüstü uygulaması: arayüzü kendi penceresinde (Edge WebView2) açar.

Veriler kullanıcının yerel uygulama klasörüne (%LOCALAPPDATA%\\MacTahmin) kopyalanır; uygulama canlı skorları ve süren
sezonun verisini oraya yazarak kendini günceller.
Çalıştırma: python -m mac_tahmin.masaustu  (paketlenmiş hâli: MacTahmin.exe)
"""
import json
import logging
import logging.handlers
import multiprocessing
import os
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

from .arayuz.erisim import AnahtarMaskeleme

GUNLUK_EN_BUYUK = 2 * 1024 * 1024  # uygulama.log bu boyuta gelince yenisine geçilir
GUNLUK_YEDEK = 3  # uygulama.log.1 … .3 saklanır, daha eskisi silinir


def kaynak_klasoru():
    """Paketlenmiş uygulamada PyInstaller'ın açtığı klasör, geliştirmede proje klasörü."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def kullanici_klasoru():
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'MacTahmin'


def hazirla(kaynak, hedef):
    """Veri dosyalarını yalnızca eksikse ya da paketteki daha yeniyse kopyalar (uygulamanın kendi güncellediği
    dosyalar ezilmez). Doğum tarihleri paketteki listeyle birleştirilir; yoksa güncellemede binlerce oyuncu yeniden
    sorulurdu."""
    (hedef / 'd').mkdir(parents=True, exist_ok=True)
    (hedef / 'ham').mkdir(parents=True, exist_ok=True)
    for f in (kaynak / 'd').glob('*.json'):
        t = hedef / 'd' / f.name
        if not t.exists() or f.stat().st_mtime > t.stat().st_mtime:
            shutil.copy2(f, t)
    baslangic_kopyala(kaynak / 'ham_baslangic', hedef / 'ham')
    paket = kaynak / 'dogum.json'
    if paket.exists():
        yol = hedef / 'ham' / 'dogum.json'
        d = json.loads(paket.read_text(encoding='utf-8'))
        if yol.exists():
            d.update({k: v for k, v in json.loads(yol.read_text(encoding='utf-8')).items() if v or k not in d})
        yol.write_text(json.dumps(d, separators=(',', ':')), encoding='utf-8')
    # eski sürümün (HTML arayüzlü) dosyaları artık kullanılmıyor
    for eski in ('mac-tahmin.html', 'canli.json'):
        (hedef / eski).unlink(missing_ok=True)
    shutil.rmtree(hedef / 'vendor', ignore_errors=True)


def baslangic_kopyala(kaynak, hedef):
    """Paketin başlangıç önbelleği (masaustu_paketle.baslangic_onbellegi): biten maçların ve takımların sayfaları, piyasa
    değerleri, scout havuzu, sözleşme tarihleri, süren sezonun lig dosyaları. Yalnızca eksik dosyalar kopyalanır
    (uygulamanın kendi indirdikleri ezilmez): yeni bir bilgisayarda ilk açılışta binlerce sayfa tek tek inmez. Paketin her
    sürümü bir kez işlenir."""
    surum = kaynak / 'surum.txt'
    isaret = hedef / 'baslangic_surum.txt'
    if not surum.exists() or (isaret.exists() and isaret.read_text(encoding='utf-8') == surum.read_text(encoding='utf-8')):
        return
    n = 0
    for f in kaynak.rglob('*'):
        if f.is_file() and f != surum:
            t = hedef / f.relative_to(kaynak)
            if not t.exists():
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
                n += 1
    isaret.write_text(surum.read_text(encoding='utf-8'), encoding='utf-8')
    print(f'başlangıç önbelleği: {n} dosya kopyalandı')


class _Bicim(logging.Formatter):
    """print çıktısı (uygulama.cikti) olduğu gibi yazılır, logging kayıtları tarih ve düzeyle."""

    def format(self, kayit):
        return kayit.getMessage() if kayit.name == 'uygulama.cikti' else super().format(kayit)


class _CiktiAkisi:
    """sys.stdout / sys.stderr yerine geçer: yazılan satırlar günlük dosyasına (dönen işleyiciyle) gider."""
    encoding = 'utf-8'

    def __init__(self):
        self._log, self._tampon, self._kilit = logging.getLogger('uygulama.cikti'), '', threading.Lock()
        self._yerel = threading.local()  # günlük yazarken oluşan hata stderr'e (buraya) dönüp sonsuz döngü yapmasın
        self._log.setLevel(logging.INFO)

    def write(self, metin):
        if getattr(self._yerel, 'icinde', False):
            return len(metin)
        self._yerel.icinde = True
        try:
            with self._kilit:
                *satirlar, self._tampon = (self._tampon + metin).split('\n')
            for s in satirlar:
                self._log.info(s.rstrip('\r'))
        finally:
            self._yerel.icinde = False
        return len(metin)

    def flush(self):
        pass

    def isatty(self):
        return False


def gunluk_kur(yol, en_buyuk=GUNLUK_EN_BUYUK, yedek=GUNLUK_YEDEK):
    """Günlük dosyasını döndürerek kurar (sınırsız büyümesin). Döner: (print için akış, işleyici); işleyici
    logging.getLogger().removeHandler ile kaldırılır."""
    isleyici = logging.handlers.RotatingFileHandler(yol, maxBytes=en_buyuk, backupCount=yedek, encoding='utf-8')
    isleyici.setFormatter(_Bicim('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    isleyici.addFilter(AnahtarMaskeleme())  # istek adresindeki ?anahtar=… günlük dosyasına yazılmaz
    kok = logging.getLogger()
    kok.addHandler(isleyici)
    if kok.level == logging.NOTSET or kok.level > logging.WARNING:
        kok.setLevel(logging.WARNING)  # kendi kayıtlarımızdan uyarılar ve hatalar da günlüğe düşer
    return _CiktiAkisi(), isleyici


def main():
    hedef = kullanici_klasoru()
    hedef.mkdir(parents=True, exist_ok=True)
    # pencereli uygulamada konsol yok: mesajlar ve hatalar günlük dosyasına yazılır
    sys.stdout = sys.stderr = gunluk_kur(hedef / 'uygulama.log')[0]
    print(f'\n{datetime.now():%Y-%m-%d %H:%M} uygulama açılıyor')
    hazirla(kaynak_klasoru(), hedef)
    from .arayuz import calistir
    calistir(hedef / 'd', hedef / 'ham', pencere=True, port=None, depolama=hedef / 'ayarlar')


if __name__ == '__main__':
    multiprocessing.freeze_support()  # pencere ayrı bir süreçte açılır
    main()
