"""Ligin süren sezonda oynanmış maçlarının oyuncu verisi: her bitmiş maçın FotMob maç sayfası (mac_ozeti.ayrinti; bitmiş
maçlar diskte kalır, bir kez indirilir) → maç maç oyuncu puanı, süresi, golü, asisti ve maçtaki mevkisi. Haftanın 11'i ve
oyuncuların form endeksi bundan hesaplanır."""
import json
import logging
import re
import sys
import threading
import time
from pathlib import Path

from .mac_ozeti import ayrinti
from .sezon import FOTMOB_ID, SON_SEZON
from .takim import VARSAYILAN_MEVKI, dizilise_yerlestir
from .veri import fotmob_detay, kimlik

logger = logging.getLogger(__name__)

_kilit = threading.Lock()  # önbellekler arka plan iş parçacıklarıyla ortak; kilit yalnızca okuma/yazma anında tutulur
ILK11_DIZILIS = '4-3-3'
OLAGAN = {0: 'G', 1: 'D', 2: 'M', 3: 'F'}  # FotMob olağan mevki → ana mevki harfi


def _mac_yolu(ham, mid):
    """İndirilmiş maç sayfasının dosyası (id dosya adına girer)."""
    return Path(ham) / 'mac_tam' / f'{kimlik(mid)}.json'


def _onbellekten(onbellek, lig, anahtar):
    """Önbellekte ligin değeri, anahtar aynıysa; yoksa None."""
    with _kilit:
        kayit = onbellek.get(lig)
    return kayit[1] if kayit and kayit[0] == anahtar else None


def _onbellege(onbellek, lig, anahtar, deger):
    with _kilit:
        onbellek[lig] = (anahtar, deger)
    return deger


def mac_listesi(lig, ham):
    """Ligin süren sezonda biten maçları: [(maç id, hafta, zaman)] (FotMob lig sayfası, sezon verisiyle birlikte iner)."""
    yol = Path(ham) / f'fm-{FOTMOB_ID[lig]}-{SON_SEZON}.json'
    if not yol.exists():
        return []
    lg = json.loads(yol.read_text(encoding='utf-8'))
    out = []
    for m in (lg.get('fixtures') or {}).get('allMatches') or []:
        st = m.get('status') or {}
        if st.get('finished') and not st.get('cancelled') and not st.get('awarded'):
            out.append((int(m['id']), str(m.get('round') or ''), st.get('utcTime') or ''))
    return sorted(out, key=lambda x: x[2])


_FIKSTUR = {}  # lig -> ((dosya, değişme zamanı), maçlar): dosya değişmedikçe yeniden okunmaz


def fikstur(lig, ham):
    """Ligin süren sezondaki bütün maçları turlarıyla (FotMob lig sayfası): [{'id', 'tur' (sayı), 'zaman', 'ev_id',
    'dep_id', 'bitti', 'iptal', 'skor' ((ev, dep) ya da None)}], zamana göre. Dosya değişmedikçe bellekten (sonuç
    paylaşılır: değiştirilmez)."""
    yol = Path(ham) / f'fm-{FOTMOB_ID[lig]}-{SON_SEZON}.json'
    if not yol.exists():
        return []
    anahtar = (str(yol), yol.stat().st_mtime)
    if _FIKSTUR.get(lig, (None,))[0] == anahtar:
        return _FIKSTUR[lig][1]
    out = _fikstur_oku(yol)
    _FIKSTUR[lig] = (anahtar, out)
    return out


def _fikstur_oku(yol):
    lg = json.loads(yol.read_text(encoding='utf-8'))
    out = []
    for m in (lg.get('fixtures') or {}).get('allMatches') or []:
        st = m.get('status') or {}
        tur = str(m.get('round') or '')
        skor = None
        if st.get('finished') and st.get('scoreStr'):
            try:
                skor = tuple(int(x) for x in st['scoreStr'].replace(' ', '').split('-')[:2])
            except ValueError:
                pass
        out.append({'id': int(m['id']), 'tur': int(tur) if tur.isdigit() else None, 'zaman': st.get('utcTime') or '',
                    'ev_id': str((m.get('home') or {}).get('id')), 'dep_id': str((m.get('away') or {}).get('id')),
                    'ev_ad': (m.get('home') or {}).get('name', ''), 'dep_ad': (m.get('away') or {}).get('name', ''),
                    'bitti': bool(st.get('finished')), 'iptal': bool(st.get('cancelled')), 'skor': skor})
    return sorted(out, key=lambda x: x['zaman'])


_ONBELLEK = {}
ON_INDIRME_BUTCE = 60  # arka plan ön indirmesinde bir turda en çok indirilen maç sayfası (tur 10 dk'da bir)


def eksik_maclar(lig, ham):
    """Ligin süren sezonda biten ama sayfası henüz indirilmemiş maçları: [(maç id, zaman)]."""
    return [(m[0], m[2]) for m in mac_listesi(lig, ham) if not _mac_yolu(ham, m[0]).exists()]


def eksikleri_indir(ligler, ham, butce=ON_INDIRME_BUTCE, durdur=None):
    """Arka plan ön indirmesi: liglerin biten maçlarının sayfaları, en yenisinden başlayarak en çok `butce` tane
    (Öne çıkanlar, roller ve xG gelişimi kullanıcı açınca beklemesin). durdur(): True dönerse yarıda bırakılır.
    Döner: indirilen sayı."""
    eksik = sorted(((z, mid) for lig in ligler for mid, z in eksik_maclar(lig, ham)), reverse=True)[:butce]
    n = 0
    for _, mid in eksik:
        if durdur and durdur():
            break
        try:
            ayrinti(mid, ham)
            n += 1
        except Exception:
            logger.warning('maç sayfası indirilemedi: %s', mid, exc_info=True)
            continue
        time.sleep(0.5)  # kaynağa yük bindirmemek için (arka planda acele yok)
    return n


def _hava(o):
    """Oyuncunun maçta kazandığı / girdiği hava topu: (kazanılan, toplam) ya da None ("Kazandığı hava topu: 3/5 (%60)")."""
    for _, satirlar in o.get('gruplar') or []:
        for ad, deger in satirlar:
            if ad == 'Kazandığı hava topu':
                m = re.match(r'(\d+)/(\d+)', str(deger))
                return (int(m.group(1)), int(m.group(2))) if m else None
    return None


class _OyuncuSatiri:
    """oyuncu_satirlari'nın bir satırı, sözlük gibi okunur (s['dk'], s.get('hava'), {**s}). Bütün liglerin satırları
    bellekte kalır (sezon sonunda 150 binden çok): sözlüğe göre çok daha az yer tutar."""
    __slots__ = ('mac', 'hafta', 'zaman', 'pid', 'ad', 'takim_id', 'takim', 'puan', 'dk', 'gol', 'asist', 'mevki',
                 'fiziksel', 'kaleci', 'hava')

    def __init__(self, *degerler):
        for ad, v in zip(self.__slots__, degerler):
            setattr(self, ad, v)

    def __getitem__(self, ad):
        return getattr(self, ad)

    def get(self, ad, varsayilan=None):
        return getattr(self, ad, varsayilan)

    def keys(self):
        return self.__slots__


def _ortak(metin):
    """Oyuncu ve takım adları her maçta yinelenir: tek kopya tutulur."""
    return sys.intern(metin) if isinstance(metin, str) else metin


def oyuncu_satirlari(lig, ham, ilerleme=None, indir=True):
    """Ligin bitmiş maçlarındaki her oyuncu için bir satır: {'mac', 'hafta', 'zaman', 'pid', 'ad', 'takim_id', 'takim',
    'puan', 'dk', 'gol', 'asist', 'mevki', 'kaleci', 'fiziksel', 'hava'}. İndirilmemiş maçlar indirilir (ilerleme(sıra,
    toplam) ile bildirilir); indir=False: yalnızca önceden indirilmiş maçlar (ağ isteği yok)."""
    maclar = mac_listesi(lig, ham)
    if not indir:
        maclar = [m for m in maclar if _mac_yolu(ham, m[0]).exists()]
    anahtar = (lig, tuple(m[0] for m in maclar))
    onceki = _onbellekten(_ONBELLEK, lig, anahtar)
    if onceki is not None:
        return onceki
    satirlar = []
    for k, (mid, hafta, zaman) in enumerate(maclar):
        if ilerleme:
            ilerleme(k + 1, len(maclar))
        yeni = not _mac_yolu(ham, mid).exists()
        try:
            a = ayrinti(mid, ham)
        except Exception:
            logger.warning('maç sayfası alınamadı: %s', mid, exc_info=True)
            continue
        if yeni:
            time.sleep(0.2)  # kaynağa yük bindirmemek için
        olay = {str(p.get('id')): p.get('olaylar') or {} for t in ('ev', 'dep') for grup in ('ilk11', 'yedek')
                for p in ((a.get('kadro') or {}).get(t) or {}).get(grup, [])}
        for pid, o in (a.get('oyuncular') or {}).items():
            if not o.get('dk'):
                continue
            mevki = fotmob_detay(o.get('mevki_kodu')) if o.get('mevki_kodu') else None
            if mevki is None:
                mevki = 'GK' if o.get('kaleci') else VARSAYILAN_MEVKI.get(OLAGAN.get(o.get('olagan')), 'CM')
            satirlar.append(_OyuncuSatiri(mid, hafta, zaman, int(pid), _ortak(o['ad']), o['takim_id'], _ortak(o['takim']),
                                          o.get('puan'), o['dk'], olay.get(pid, {}).get('gol', 0),
                                          olay.get(pid, {}).get('asist', 0), mevki, o.get('fiziksel'), bool(o.get('kaleci')),
                                          _hava(o)))
    return _onbellege(_ONBELLEK, lig, anahtar, satirlar)


ISTIKRAR_MIN_MAC = 5  # istikrar için en az bu kadar maç (her biri en az ISTIKRAR_MIN_DK oynanmış, puanı olan)
ISTIKRAR_MIN_DK = 45
ISTIKRAR_KOTU = 6.5  # bu puanın altı "kötü maç"
ISTIKRAR_ETIKET = [(70, 'Çok istikrarlı'), (40, 'İstikrarlı'), (0, 'Dalgalı')]  # ligdeki yüzdeliğe göre


def istikrar(satirlar):
    """Oyuncuların maçtan maça istikrarı (FotMob maç puanlarının dalgalanması): {FotMob oyuncu id: {'n' maç, 'ort'
    ortalama puan, 'sapma' standart sapma, 'kotu' ISTIKRAR_KOTU altı maç sayısı, 'yuzdelik' (ligde sapması kendisinden
    büyük oyuncuların payı ×100: yüksek = istikrarlı; kaleciler kendi aralarında, puanları doğası gereği daha
    oynaktır), 'etiket', 'kaleci'}}. Yalnızca en az ISTIKRAR_MIN_MAC maçı olanlar."""
    puanlar, kaleci = {}, {}
    for s in satirlar:
        if s.get('puan') and s['dk'] >= ISTIKRAR_MIN_DK:
            puanlar.setdefault(s['pid'], []).append(s['puan'])
            kaleci[s['pid']] = kaleci.get(s['pid'], 0) + (1 if s.get('kaleci') else -1)
    out = {}
    for pid, p in puanlar.items():
        if len(p) < ISTIKRAR_MIN_MAC:
            continue
        ort = sum(p) / len(p)
        sapma = (sum((x - ort) ** 2 for x in p) / (len(p) - 1)) ** 0.5
        out[pid] = {'n': len(p), 'ort': ort, 'sapma': sapma, 'kotu': sum(1 for x in p if x < ISTIKRAR_KOTU),
                    'kaleci': kaleci[pid] > 0}
    for grup in (True, False):
        sapmalar = [v['sapma'] for v in out.values() if v['kaleci'] == grup]
        for v in out.values():
            if v['kaleci'] != grup:
                continue
            buyuk = sum(1 for x in sapmalar if x > v['sapma'])
            v['yuzdelik'] = round(buyuk / len(sapmalar) * 100) if len(sapmalar) > 1 else 50
            v['etiket'] = next(ad for esik, ad in ISTIKRAR_ETIKET if v['yuzdelik'] >= esik)
    return out


def istikrar_yazisi(v):
    """Kısa açıklama: 'İstikrarlı (ligde yüzdelik 64; 12 maçta ort. 7,1, 1 kötü maç)'; hep düşük oynayana (ortalaması
    kötü maç sınırında ya da maçlarının en az yarısı kötü) not düşülür."""
    if not v:
        return ''
    dusuk = v['etiket'] != 'Dalgalı' and (v['ort'] < ISTIKRAR_KOTU + 0.1 or 2 * v['kotu'] >= v['n'])
    ort = f'{v["ort"]:.1f}'.replace('.', ',')
    return (f'{v["etiket"]}{" ama düşük düzeyde" if dusuk else ""} (ligde yüzdelik {v["yuzdelik"]}; {v["n"]} maçta '
            f'ortalama puan {ort}, {v["kotu"]} kötü maç)')


_YARI_ONBELLEK = {}


def yari_maclari(lig, ham):
    """Ligin süren sezonda biten, sayfası indirilmiş maçlarının devre ve maç sonu skorları (ağ isteği yok):
    [{'zaman', 'ev_id', 'dep_id', 'iy': (ev, dep), 'ms': (ev, dep)}]. İndirilmiş maçlar değişmedikçe bellekten."""
    maclar = [(mid, zaman) for mid, _, zaman in mac_listesi(lig, ham) if _mac_yolu(ham, mid).exists()]
    anahtar = tuple(m[0] for m in maclar)
    onceki = _onbellekten(_YARI_ONBELLEK, lig, anahtar)
    if onceki is not None:
        return onceki
    out = []
    for mid, zaman in maclar:
        try:
            a = json.loads(_mac_yolu(ham, mid).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            logger.warning('maç dosyası okunamadı: %s', mid, exc_info=True)
            continue
        devre = next((o for o in a.get('olaylar') or [] if o.get('tur') == 'devre'), None)
        skor = (devre or {}).get('skor') or [None, None]
        if None in skor or a['ev'].get('skor') is None or a['dep'].get('skor') is None:
            continue
        out.append({'zaman': zaman, 'ev_id': a['ev']['id'], 'dep_id': a['dep']['id'], 'iy': (skor[0], skor[1]),
                    'ms': (a['ev']['skor'], a['dep']['skor'])})
    return _onbellege(_YARI_ONBELLEK, lig, anahtar, out)


_XG_ONBELLEK = {}


def takim_xg_maclari(lig, ham):
    """Ligin süren sezonda biten ve önceden indirilmiş maçlarının takım xG'si (maç sayfasındaki takım istatistiği; ağ
    isteği yok): [{'zaman', 'ev_id', 'dep_id', 'ev_gol', 'dep_gol', 'ev_xg', 'dep_xg', 'ev_sutlar', 'dep_sutlar'}], tarih
    sırasıyla. Şutlar: maçtaki şutların xG'leri (oyuncuların şut haritasından; yoksa None), hak edilen puanın şut şut
    hesabı için. İndirilmiş maçlar değişmedikçe bellekten."""
    maclar = [(mid, zaman) for mid, _, zaman in mac_listesi(lig, ham) if _mac_yolu(ham, mid).exists()]
    anahtar = tuple(m[0] for m in maclar)
    onceki = _onbellekten(_XG_ONBELLEK, lig, anahtar)
    if onceki is not None:
        return onceki
    out = []
    for mid, zaman in maclar:
        try:
            a = json.loads(_mac_yolu(ham, mid).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            logger.warning('maç dosyası okunamadı: %s', mid, exc_info=True)
            continue
        xg = next((s for _, satirlar in a.get('istatistik') or [] for s in satirlar if s[0] == 'Beklenen gol (xG)'), None)
        try:
            ex, dx = float(xg[1]), float(xg[2])
        except (TypeError, ValueError, IndexError):
            continue
        if a['ev'].get('skor') is None or a['dep'].get('skor') is None:
            continue
        sut = {a['ev']['id']: [], a['dep']['id']: []}
        for o in (a.get('oyuncular') or {}).values():
            if o.get('takim_id') in sut:
                sut[o['takim_id']] += [float(s['xg']) for s in o.get('sutlar') or [] if s.get('xg') is not None]
        var = any(sut.values())
        out.append({'zaman': zaman, 'ev_id': a['ev']['id'], 'dep_id': a['dep']['id'], 'ev_gol': a['ev']['skor'],
                    'dep_gol': a['dep']['skor'], 'ev_xg': ex, 'dep_xg': dx,
                    'ev_sutlar': sut[a['ev']['id']] if var else None, 'dep_sutlar': sut[a['dep']['id']] if var else None})
    return _onbellege(_XG_ONBELLEK, lig, anahtar, out)


FIZIKSEL_MIN_DK = 270  # fiziksel sıralamalarda (90 dk başına) en az bu kadar dakika
HAVA_MIN_TOP = 15      # hava hâkimi için sezonda en az bu kadar hava topuna girmiş olmalı


def buyuk_mac_oyunculari(satirlar, buyukler, min_mac=3):
    """Büyük maç oyuncuları (sezon.BUYUK_MAC): büyük takımlara (buyukler: FotMob takım id'leri) karşı oynadığı maçlarda
    90 dakikada gol + asist üretimi, bu maçlarda en az 180 dakika oynamış saha oyuncularının en üst %10'unda; en az 2 gol
    ya da asist ve min_mac maç. Kendi takımı büyük olan oyuncuda, diğer büyüklere karşı oynadıkları sayılır.
    Döner: {FotMob oyuncu id: (maç, dakika, gol, asist, 90 dk'da gol + asist)}."""
    takimlar = {}
    for s in satirlar:
        takimlar.setdefault(s['mac'], set()).add(s['takim_id'])
    top = {}
    for s in satirlar:
        rakip = next((t for t in takimlar[s['mac']] if t != s['takim_id']), None)
        if s.get('kaleci') or not s['dk'] or rakip not in buyukler:
            continue
        t = top.setdefault(s['pid'], [0, 0, 0, 0])
        t[0] += 1
        t[1] += s['dk']
        t[2] += s['gol']
        t[3] += s['asist']
    havuz = {pid: t for pid, t in top.items() if t[1] >= 180}
    if len(havuz) < 30:
        return {}
    oran = {pid: (t[2] + t[3]) / t[1] * 90 for pid, t in havuz.items()}
    sirali = sorted(oran.values())
    esik = sirali[int(len(sirali) * 0.9)]
    return {pid: (*t, oran[pid]) for pid, t in havuz.items()
            if oran[pid] >= esik and oran[pid] > 0 and t[2] + t[3] >= 2 and t[0] >= min_mac}


def hava_hakimleri(satirlar, min_dk):
    """Hava hâkimleri (sezon.HAVA_HAKIMI): kazandığı hava topu 90 dakikada saha oyuncularının (en az min_dk dakika)
    en üst %10'unda ve kazanma oranı en az %55. Döner: {FotMob oyuncu id: (kazanılan, toplam, 90 dk'da kazanılan)}."""
    top = {}
    for s in satirlar:
        if s.get('kaleci') or not s['dk']:
            continue
        t = top.setdefault(s['pid'], [0, 0, 0])
        t[2] += s['dk']
        if s.get('hava'):
            t[0] += s['hava'][0]
            t[1] += s['hava'][1]
    havuz = {pid: t for pid, t in top.items() if t[2] >= min_dk}
    if len(havuz) < 40:
        return {}
    oran = {pid: t[0] / t[2] * 90 for pid, t in havuz.items()}
    sirali = sorted(oran.values())
    esik = sirali[int(len(sirali) * 0.9)]
    return {pid: (t[0], t[1], oran[pid]) for pid, t in havuz.items()
            if oran[pid] >= esik and t[1] >= HAVA_MIN_TOP and t[0] / t[1] >= 0.55}


def fiziksel_ozet(satirlar):
    """Oyuncuların sezonluk fiziksel verisi (FotMob yalnızca Premier League'de verir): {FotMob oyuncu id: {'ad', 'takim',
    'takim_id', 'mac', 'dk', 'mesafe' (m), 'kosu', 'sprint_m', 'sprint' (sayı), 'hiz' (en yüksek, km/sa), 'mesafe90',
    'sprint90'}}. Fiziksel verisi olmayan ligde boş."""
    out = {}
    for s in satirlar:
        f = s.get('fiziksel')
        if not f or not s['dk']:
            continue
        o = out.setdefault(s['pid'], {'ad': s['ad'], 'takim': s['takim'], 'takim_id': s['takim_id'], 'mac': 0, 'dk': 0,
                                      'mesafe': 0.0, 'kosu': 0.0, 'sprint_m': 0.0, 'sprint': 0, 'hiz': 0.0})
        o['mac'] += 1
        o['dk'] += s['dk']
        for k in ('mesafe', 'kosu', 'sprint_m'):
            o[k] += f.get(k) or 0
        o['sprint'] += int(f.get('sprint') or 0)
        o['hiz'] = max(o['hiz'], f.get('hiz') or 0)
        o['ad'], o['takim'], o['takim_id'] = s['ad'], s['takim'], s['takim_id']  # en son maçtaki takımı
    for o in out.values():
        o['mesafe90'] = o['mesafe'] / o['dk'] * 90
        o['sprint90'] = o['sprint'] / o['dk'] * 90
    return out


def haftanin_11i(satirlar, hafta, dizilis=ILK11_DIZILIS, en_az_dk=45):
    """Haftanın (turun) en yüksek puanlı oyuncularından ilk 11 ve haftanın oyuncusu."""
    adaylar = [{'anahtar': s['pid'], 'deger': s['puan'], 'mevki': s['mevki'], **s}
               for s in satirlar if s['hafta'] == hafta and s['puan'] and s['dk'] >= en_az_dk]
    on1 = dizilise_yerlestir(adaylar, dizilis)
    enler = max(adaylar, key=lambda a: a['puan'], default=None)
    return on1, enler


def form_tablosu(satirlar, son=5, en_az=3):
    """Oyuncuların son maçlarındaki puan ortalaması ve sezon ortalamasıyla farkı (form endeksi):
    [{'pid', 'ad', 'takim', 'takim_id', 'son_ort', 'sezon_ort', 'fark', 'mac', 'son_puanlar', 'gol', 'asist'}].
    "Son maçlar" oyuncunun değil takımının son `son` maçıdır: bunların en az en_az'ında (en az 20 dakika, puanlı) oynamış
    oyuncular. Sakatlanan ya da kadro dışı kalan oyuncu eski maçlarıyla listede kalmaz; ligin içinde takım değiştirende
    son takımı."""
    takim_maclari = {}
    for s in satirlar:
        takim_maclari.setdefault(s['takim_id'], {})[s['mac']] = s['zaman']
    takim_son = {t: set(sorted(ms, key=ms.get)[-son:]) for t, ms in takim_maclari.items()}
    oyuncu = {}
    for s in sorted(satirlar, key=lambda s: s['zaman']):
        if s['puan'] and s['dk'] >= 20:
            oyuncu.setdefault(s['pid'], []).append(s)
    out = []
    for pid, ms in oyuncu.items():
        takim = ms[-1]['takim_id']
        son_ms = [m for m in ms if m['takim_id'] == takim and m['mac'] in takim_son.get(takim, ())]
        if len(son_ms) < en_az:
            continue
        son_ort = sum(m['puan'] for m in son_ms) / len(son_ms)
        sezon_ort = sum(m['puan'] for m in ms) / len(ms)
        out.append({'pid': pid, 'ad': ms[-1]['ad'], 'takim': ms[-1]['takim'], 'takim_id': ms[-1]['takim_id'],
                    'son_ort': son_ort, 'sezon_ort': sezon_ort, 'fark': son_ort - sezon_ort, 'mac': len(ms),
                    'son_puanlar': [m['puan'] for m in son_ms], 'gol': sum(m['gol'] for m in son_ms),
                    'asist': sum(m['asist'] for m in son_ms)})
    return out
