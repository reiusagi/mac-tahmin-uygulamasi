"""Oyuncu doğum tarihleri (yaş filtresi için). FotMob oyuncu id -> 'YYYY-MM-DD'.

Önce önbellekteki takım kadrolarından (fm-takim-*.json) okunur; eksikler FotMob'un oyuncu sayfasından tek tek
çekilir. Sonuç ham/dogum.json'da tutulur; oyuncu sayfasının tamamı saklanmaz (çok yer kaplar).
Bulunamayan oyuncular "" olarak yazılır ki tekrar tekrar sorulmasın.
"""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .veri import fotmob_url, json_getir, kimlik

logger = logging.getLogger(__name__)

_KILIT = threading.Lock()
_ONBELLEK = {}  # ham klasörü -> sözlük


def gecerli(tarih):
    """FotMob doğum tarihini bilmediğinde '0001-01-01' gibi yer tutucu verir: bunlar bilinmiyor ('') sayılır."""
    tarih = (tarih or '')[:10]
    return tarih if len(tarih) == 10 and tarih[:4].isdigit() and int(tarih[:4]) >= 1900 else ''


def dogum_oku(ham):
    ham = str(Path(ham))
    if ham not in _ONBELLEK:
        yol = Path(ham) / 'dogum.json'
        d = json.loads(yol.read_text(encoding='utf-8')) if yol.exists() else {}
        d = {k: gecerli(v) for k, v in d.items()}
        for f in Path(ham).glob('fm-takim-*.json'):  # kadrolar: ek istek gerektirmez
            try:
                t = json.loads(f.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                logger.debug('takım kadrosu okunamadı: %s', f.name, exc_info=True)
                continue
            # kadrosu olmayan takımda (alt lig, yeni kulüp) FotMob 'squad': null verir: o takım atlanır
            for g in (t.get('squad') or {}).get('squad') or []:
                for m in (g or {}).get('members') or []:
                    if m.get('id') is not None and gecerli(m.get('dateOfBirth')) and not d.get(str(m['id'])):
                        d[str(m['id'])] = gecerli(m['dateOfBirth'])
        _ONBELLEK[ham] = d
    return _ONBELLEK[ham]


def _kaydet(ham, d):
    yol = Path(ham) / 'dogum.json'
    gecici = yol.with_suffix('.tmp')
    with _KILIT:
        gecici.write_text(json.dumps(d, separators=(',', ':')), encoding='utf-8')
        gecici.replace(yol)


def _cek(pid):
    try:
        pid = kimlik(pid)  # adrese girer
    except ValueError:
        return None
    for deneme in range(3):
        try:
            p = json_getir(fotmob_url('playerData', id=pid))
            return gecerli((p.get('birthDate') or {}).get('utcTime'))
        except Exception:
            logger.debug('doğum tarihi alınamadı: %s (deneme %d)', pid, deneme + 1, exc_info=True)
            time.sleep(2 * (deneme + 1))
    return None  # ağ hatası: bir dahaki sefere yeniden denensin


def tamamla(ids, ham, es_zamanli=3, yaz=None):
    """Doğum tarihi bilinmeyen oyuncuları FotMob'dan çeker. Yeni çekilen sayısını döndürür."""
    d = dogum_oku(ham)
    eksik = sorted({str(i) for i in ids if i is not None} - set(d))
    if not eksik:
        return 0
    sayac = [0]

    def is_(pid):
        sonuc = _cek(pid)
        time.sleep(0.3)  # siteye yük bindirmemek için
        if sonuc is None:
            return
        with _KILIT:
            d[pid] = sonuc
            sayac[0] += 1
            n = sayac[0]
        if n % 200 == 0:
            _kaydet(ham, d)
            if yaz:
                yaz(f'doğum tarihi: {n}/{len(eksik)}')

    with ThreadPoolExecutor(es_zamanli) as ex:
        list(ex.map(is_, eksik))
    _kaydet(ham, d)
    return sayac[0]


if __name__ == '__main__':  # toplu doldurma: python -m mac_tahmin.dogum
    import glob
    import sys
    ham = sys.argv[1] if len(sys.argv) > 1 else 'ham'
    ids = set()
    for f in glob.glob(str(Path(ham) / 'fm-*-mins_played.json')):
        for it in json.loads(Path(f).read_text(encoding='utf-8'))['TopLists'][0]['StatList']:
            ids.add(it['ParticiantId'])
    print(f'{len(ids)} oyuncu, {len(set(map(str, ids)) - set(dogum_oku(ham)))} eksik', flush=True)
    print('yeni:', tamamla(ids, ham, es_zamanli=6, yaz=lambda s: print(s, flush=True)), flush=True)
