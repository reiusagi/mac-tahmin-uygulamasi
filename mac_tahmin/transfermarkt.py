"""Transfermarkt'tan YALNIZCA sözleşme bitiş tarihi (kullanıcının izniyle; başka hiçbir veri alınmaz).

Yalnızca FotMob'da sözleşme bilgisi olmayan ve Scout listesinde görünebilecek oyuncular için çağrılır. Kaynağa yük
bindirmemek için istekler arasında BEKLEME_SN saniye beklenir, sonuçlar uzun süre saklanır (ham/transfermarkt.json).
Site bir engel gösterirse (bot doğrulaması, hata yanıtı) aşılmaya çalışılmaz: ENGEL_SAAT boyunca hiç istek atılmaz.

Oyuncu bulma: Transfermarkt hızlı araması (oyuncunun adıyla); sonuçtaki oyuncu adı + kulüp (yazım farklarına toleranslı)
ya da ad + yaş tutmalı, emin olunamazsa tarih kullanılmaz. Kiralık oyuncuda ana kulübüyle sözleşmesi esas alınır."""
import difflib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .sezon import sadelestir
from .veri import UA, ac, url_guvenli_mi, yanit_oku

ACIK = True              # Transfermarkt'tan sözleşme tarihi alınsın mı (kullanıcının izni: yalnızca sözleşme tarihi)
BEKLEME_SN = 3.0         # istekler arası bekleme
GECERLI_GUN = 90         # bulunan sözleşme tarihi bu kadar gün saklanır
BULUNAMADI_GUN = 30      # bulunamayan oyuncu bu kadar gün sonra yeniden aranır
ENGEL_SAAT = 6           # site engel gösterirse bu kadar saat hiç istek atılmaz
_SITE = 'https://www.transfermarkt.com'
logger = logging.getLogger(__name__)
_son_istek = [0.0]
_engel = [0.0]
_istek_kilit = threading.Lock()  # iki iş parçacığı aynı bekleme aralığını paylaşmasın


class Engellendi(Exception):
    pass


def engelli_mi():
    return time.time() - _engel[0] < ENGEL_SAAT * 3600


def _getir(yol):
    if engelli_mi():
        raise Engellendi()
    with _istek_kilit:  # sıra alınır (bekleme kilit dışında): art arda gelen istekler BEKLEME_SN arayla çıkar
        simdi = time.time()
        bekle = BEKLEME_SN - (simdi - _son_istek[0])
        _son_istek[0] = simdi + max(bekle, 0)
    if bekle > 0:
        time.sleep(bekle)
    if not url_guvenli_mi(_SITE + yol):
        raise ValueError('izinsiz adres reddedildi')
    istek = urllib.request.Request(_SITE + yol, headers={'User-Agent': UA, 'Accept': 'text/html', 'Accept-Encoding': 'gzip',
                                                         'Accept-Language': 'en'})
    try:
        with ac(istek, timeout=30) as r:
            govde, kod = yanit_oku(r, _SITE + yol), r.status
    except urllib.error.HTTPError as ex:
        if ex.code in (403, 429, 503):  # erişim reddi ya da hız sınırı: zorlamadan bir süre bırak
            _engel[0] = time.time()
            raise Engellendi() from ex
        raise
    html = govde.decode('utf-8', 'replace')
    if kod != 200 or re.search(r'captcha|cf-chl|challenge-platform', html, re.I):
        _engel[0] = time.time()
        raise Engellendi()
    return html


def _benzer(a, b):
    a, b = sadelestir(a or ''), sadelestir(b or '')
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _ara(ad, kulup, yas):
    """Arama sonucundan oyuncunun Transfermarkt kimliği ya da None (emin olunamazsa)."""
    html = _getir('/schnellsuche/ergebnis/schnellsuche?query=' + urllib.parse.quote(ad))
    adaylar = []
    for parca in html.split('<td class="hauptlink"><a title="')[1:]:
        m = re.match(r'([^"]+)" href="/[^"]+/profil/spieler/(\d+)"', parca)
        if not m:
            continue
        k = re.search(r'/startseite/verein/\d+">([^<]+)</a>', parca)
        y = re.search(r'<td class="zentriert">(\d{1,2})</td>', parca)
        adaylar.append((m.group(1), int(m.group(2)), k.group(1) if k else '', int(y.group(1)) if y else None))
    en, en_puan = None, 0.0
    for tad, tid, tkulup, tyas in adaylar:
        ad_p = _benzer(ad, tad)
        if ad_p < 0.75:
            continue
        kulup_p = _benzer(kulup, tkulup)
        yas_tutar = yas is not None and tyas is not None and abs(yas - tyas) <= 1
        if kulup_p >= 0.6 or (ad_p >= 0.95 and yas_tutar):
            puan = ad_p + kulup_p + (0.5 if yas_tutar else 0)
            if puan > en_puan:
                en, en_puan = tid, puan
    return en


def _tarih(metin):
    m = re.search(r'(\d{2})/(\d{2})/(\d{4})', metin or '')
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else None


def _sozlesme(tm_id):
    """Profil sayfasından (bitiş 'YYYY-AA-GG' ya da None, kiralık mı). Kiralıkta ana kulübüyle sözleşme."""
    html = _getir(f'/x/profil/spieler/{tm_id}')
    duz = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))
    ana = re.search(r'Contract there expires: ([0-9/]{10})', duz)
    if ana:
        return _tarih(ana.group(1)), True
    m = re.search(r'Contract expires: ([0-9/]{10})', duz)
    return (_tarih(m.group(1)) if m else None), False


def sozlesmeler(ham, oyuncular, ilerleme=None, indir=True):
    """oyuncular: [(FotMob id, ad, kulüp, yaş)]. Döner: {FotMob id (metin): {'bitis', 'kiralik', 'tm'}} — önbellekte ya da
    yeni bulunanlar. Engel görülürse kalanlar atlanır (sonraki denemeye kalır). indir=False: yalnızca önbellek."""
    yol = Path(ham) / 'transfermarkt.json'
    kayit = json.loads(yol.read_text(encoding='utf-8')) if yol.exists() else {}
    simdi = time.time()

    def taze(r):
        return r and simdi - r['zaman'] < (GECERLI_GUN if r.get('bitis') else BULUNAMADI_GUN) * 86400
    eksik = [o for o in oyuncular if o[0] is not None and not taze(kayit.get(str(o[0])))]
    if indir and ACIK and eksik and not engelli_mi():
        for k, (fid, ad, kulup, yas) in enumerate(eksik):
            if ilerleme:
                ilerleme(k + 1, len(eksik))
            try:
                tm = _ara(ad, kulup, yas)
                bitis, kiralik = _sozlesme(tm) if tm else (None, False)
            except Engellendi:
                break
            except Exception:
                logger.debug('Transfermarkt sözleşmesi alınamadı: %s', fid, exc_info=True)
                continue
            kayit[str(fid)] = {'tm': tm, 'bitis': bitis, 'kiralik': kiralik, 'zaman': time.time()}
            if k % 10 == 9:  # yarıda kesilirse kazanılan kaybolmasın
                yol.write_text(json.dumps(kayit), encoding='utf-8')
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps(kayit), encoding='utf-8')
    simdi = time.time()  # süresi dolmuş kayıtlar dönmez (yeniden aranabilsinler)
    return {str(o[0]): kayit[str(o[0])] for o in oyuncular if o[0] is not None and taze(kayit.get(str(o[0])))}
