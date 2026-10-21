"""Milli takımlar: uluslararası turnuvaların fikstürü ve grup tabloları (FotMob), milli takım Elo'su ve maç tahmini.

Elo, World Football Elo (eloratings.net) yöntemiyle 2008'den bu yana bütün resmi milli maçlardan hesaplanır:
  - maçın önemi (K): Dünya Kupası 60, kıta şampiyonaları 50, elemeler ve Uluslar Ligi 40, bölgesel kupalar 30, hazırlık 20
  - gol farkı çarpanı: 1 farkla 1, 2 farkla 1,5, 3+ farkla (11 + fark) / 8
  - ev sahibine +60 (turnuva finallerinde saha tarafsız sayılır; ama MEZBAN'daki ev sahibi ülke kendi turnuvasında ev sahibi sayılır)
Gol beklentisi Elo farkından Poisson regresyonuyla öğrenilir; skor ve sonuç olasılıkları kulüp tahminiyle aynı yoldan hesaplanır.

Yeni turnuva eklemek: TURNUVALAR'a (FotMob kimliği, Türkçe ad, tür, tarafsız saha mı) ekle.
"""
import json
import logging
import math
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import sema
from .logo import LIG_LOGO as LOGO  # noqa: F401  (eski ad)
from .modeller import sonuc_olasiliklari
from .ulkeler import turkce
from .veri import fotmob_url, json_getir

logger = logging.getLogger(__name__)

# (FotMob kimliği, ad, tür, finaller tarafsız sahada mı). Yaş grubu ve kadın turnuvaları kapsam dışı.
TURNUVALAR = [
    (77, 'Dünya Kupası', 'dunya', True),
    (50, 'EURO', 'kita', True),
    (44, 'Copa América', 'kita', True),
    (289, 'Afrika Uluslar Kupası', 'kita', True),
    (290, 'Asya Kupası', 'kita', True),
    (298, 'CONCACAF Gold Cup', 'kita', True),
    (9806, 'UEFA Uluslar Ligi A', 'eleme', False),
    (9807, 'UEFA Uluslar Ligi B', 'eleme', False),
    (9808, 'UEFA Uluslar Ligi C', 'eleme', False),
    (9809, 'UEFA Uluslar Ligi D', 'eleme', False),
    (9821, 'CONCACAF Uluslar Ligi', 'eleme', False),
    (10195, 'Dünya Kupası Elemeleri (Avrupa)', 'eleme', False),
    (10199, 'Dünya Kupası Elemeleri (Güney Amerika)', 'eleme', False),
    (10196, 'Dünya Kupası Elemeleri (Afrika)', 'eleme', False),
    (10197, 'Dünya Kupası Elemeleri (Asya)', 'eleme', False),
    (10198, 'Dünya Kupası Elemeleri (Kuzey ve Orta Amerika)', 'eleme', False),
    (10200, 'Dünya Kupası Elemeleri (Okyanusya)', 'eleme', False),
    (10201, 'Dünya Kupası Kıtalararası Play-off', 'eleme', True),
    (10607, 'EURO Elemeleri', 'eleme', False),
    (10608, 'Afrika Uluslar Kupası Elemeleri', 'eleme', False),
    (10609, 'Asya Kupası Elemeleri', 'eleme', False),
    (329, 'Körfez Kupası', 'bolge', True),
    (13287, 'FIFA ASEAN Kupası', 'bolge', False),
    (114, 'Hazırlık maçları', 'hazirlik', False),
]
K = {'dunya': 60, 'kita': 50, 'eleme': 40, 'bolge': 30, 'hazirlik': 20}
ILK_YIL = 2008  # Elo bu yıldan başlar; herkes 1500'den başladığı için uzun geçmiş sıralamayı oturtur
EV_AVANTAJI = 60  # 2022+ maçlarda ölçüldü: +50…+75 en düşük log-loss (eloratings'in +100'ü bu veride ev sahibini abartıyor)
# turnuva finallerinin tek ev sahibi ülkesi: (FotMob turnuva kimliği, turnuva yılı) -> FotMob'daki (İngilizce) ad. Ortak ev
# sahipliği olanlar (EURO 2008/2012/2020, Afrika 2012, Gold Cup'ın yan ev sahipleri, Körfez Kupası) maç yeri verisi
# olmadığından yok sayılır. 2026 Dünya Kupası'nda üç ev sahibi de kendi ülkesinde oynar (rakip ev sahibi değilse).
MEZBAN = {(77, 2010): ('South Africa',), (77, 2014): ('Brazil',), (77, 2018): ('Russia',), (77, 2022): ('Qatar',),
          (77, 2026): ('USA', 'Mexico', 'Canada'), (50, 2016): ('France',), (50, 2024): ('Germany',),
          (44, 2011): ('Argentina',), (44, 2015): ('Chile',), (44, 2016): ('USA',), (44, 2019): ('Brazil',),
          (44, 2021): ('Brazil',), (44, 2024): ('USA',),
          (289, 2013): ('South Africa',), (289, 2015): ('Equatorial Guinea',), (289, 2017): ('Gabon',),
          (289, 2019): ('Egypt',), (289, 2021): ('Cameroon',), (289, 2023): ('Ivory Coast',), (289, 2025): ('Morocco',),
          (290, 2011): ('Qatar',), (290, 2015): ('Australia',), (290, 2019): ('UAE',), (290, 2023): ('Qatar',),
          (298, 2011): ('USA',), (298, 2013): ('USA',), (298, 2015): ('USA',), (298, 2017): ('USA',),
          (298, 2019): ('USA',), (298, 2021): ('USA',), (298, 2023): ('USA',), (298, 2025): ('USA',)}
GUNCEL_YENILE_SAAT = 6  # süren turnuva sezonlarının verisi bu kadar eskiyince yeniden indirilir
TURNUVA = {t[0]: t for t in TURNUVALAR}
LIG_HARFI = {9806: 'A', 9807: 'B', 9808: 'C', 9809: 'D'}  # Uluslar Ligi'nin ligleri (grubun hangi ligde olduğu)


def mezban_yonu(tid, zaman, ev, dep, sezon=None):
    """Turnuva finalinde ev sahibi ülkenin oynadığı maçta saha avantajı: +1 (ev yazılan takım mezban), -1 (deplasman yazılan
    mezban), 0 (mezban yok, ikisi de mezban ya da bilinmiyor). ev, dep: FotMob'daki ya da Türkçe takım adı. sezon: turnuvanın
    sezonu ('2023'); yıl aşan turnuvalarda (Afrika 2023 → Ocak 2024) anahtar sezondur. Verilmezse maçın takvim yılı."""
    yil = str(sezon or zaman)[:4]
    mez = {turkce(x) for x in MEZBAN.get((tid, int(yil)) if yil.isdigit() else None, ())}
    return (turkce(ev) in mez) - (turkce(dep) in mez)


def grup_adi(tid, grup, lig_harfi=None):
    """FotMob'un grup yazısını ('1', 'Grp. 1', 'A', 'Group A') okunur hâle getirir: '1. Grup', 'A Grubu'. Uluslar
    Ligi gibi lig katmanı olan turnuvalarda lig de yazılır: 'A Ligi · 1. Grup'. Grup yoksa ''."""
    g = re.sub(r'^(Grp\.|Group|Grupo|Grup)\s*', '', str(grup or '').strip(), flags=re.I).strip()
    if not g:
        return ''
    ad = f'{g}. Grup' if g.isdigit() else f'{g} Grubu' if len(g) <= 2 else g
    harf = LIG_HARFI.get(tid) or lig_harfi
    return f'{harf} Ligi · {ad}' if harf else ad


def _yol(ham, tid, sezon=None, klasor='milli'):
    return Path(ham) / klasor / f'fm-{tid}-{(sezon or "guncel").replace("/", "-")}.json'


def _getir(ham, tid, sezon=None, yenile=False, klasor='milli'):
    """Turnuvanın bir sezonu (FotMob lig sayfası verisi); önbellekten ya da ağdan. klasor: ham altındaki önbellek
    klasörü (avrupa.py de kullanır)."""
    yol = _yol(ham, tid, sezon, klasor)
    if yol.exists() and not yenile:
        return json.loads(yol.read_text(encoding='utf-8'))
    j = json_getir(fotmob_url('leagues', id=tid, season=sezon or None))
    sema.kontrol('kupa', j)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(j, ensure_ascii=False), encoding='utf-8')
    time.sleep(0.3)
    return j


def _yil(sezon):
    return int(str(sezon)[:4])


def indir(ham, cikti, yenile_guncel=False, yaz=None, zorla=()):
    """Bütün turnuvaların ILK_YIL'dan bu yana sezonlarını indirir (önbellekte olanlar atlanır) ve uygulamanın okuduğu
    derlenmiş dosyayı (cikti/milli.json) yazar. yenile_guncel: süren sezonlar (her turnuvanın en yeni sezonu) belli
    bir süreden eskiyse yeniden indirilir. zorla: süren sezonu yaşına bakmadan yenilenecek turnuvalar (True: hepsi;
    maç bitince ya da "şimdi güncelle"). Hata sayısını döner."""
    hata, indirilen = 0, 0
    for tid, ad, *_ in TURNUVALAR:
        try:
            guncel_yol = _yol(ham, tid)
            eski = not guncel_yol.exists() or time.time() - guncel_yol.stat().st_mtime > GUNCEL_YENILE_SAAT * 3600 \
                or zorla is True or tid in zorla
            indirilen += eski and (yenile_guncel or not guncel_yol.exists())
            j = _getir(ham, tid, yenile=yenile_guncel and eski)
            secili = (j.get('details') or {}).get('selectedSeason')
            for s in j.get('allAvailableSeasons') or []:
                if _yil(s) < ILK_YIL or s == secili:
                    continue
                indirilen += not _yol(ham, tid, s).exists()
                _getir(ham, tid, s)
            if yaz:
                yaz(f'{ad}: tamam')
        except Exception as ex:
            hata += 1
            if yaz:
                yaz(f'{ad}: indirilemedi ({ex})')
    if indirilen or not (Path(cikti) / 'milli.json').exists():
        derle(ham, cikti)
    return hata


def _ham_sezonlar(ham, tid):
    """İndirilmiş ham sezonlar: {sezon adı: FotMob verisi}."""
    out = {}
    for f in (Path(ham) / 'milli').glob(f'fm-{tid}-*.json'):
        try:
            j = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            logger.warning('ham milli dosya okunamadı: %s', f.name, exc_info=True)
            continue
        s = (j.get('details') or {}).get('selectedSeason')
        if s and _yil(s) >= ILK_YIL:
            out[s] = j
    return out


def derle(ham, cikti):
    """Ham veriden küçük derlenmiş dosya: cikti/milli.json = {'turnuvalar': {kimlik: {sezon: {'maclar', 'gruplar'}}}}.
    Maç: [id, zaman (UTC), ev id, dep id, ev, dep, ev golü, dep golü, grup, tur, başladı mı]; oynanmamışsa goller None."""
    out = {'guncellendi': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'turnuvalar': {}}
    for tid, *_ in TURNUVALAR:
        out['turnuvalar'][str(tid)] = {
            s: {'maclar': [[m['id'], m['zaman'], m['evId'], m['depId'], m['ev'], m['dep'],
                            *(m['skor'] or (None, None)), m['grup'], m['tur'], m['basladi']] for m in _maclar(j, tid)],
                'gruplar': gruplar(j)}
            for s, j in _ham_sezonlar(ham, tid).items()}
    yol = Path(cikti) / 'milli.json'
    gecici = yol.with_suffix('.tmp')
    gecici.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    gecici.replace(yol)


class DosyaOnbellegi:
    """Tek JSON dosyasının bellek önbelleği (avrupa.py de kullanır): dosya değişmedikçe bellekten okunur; ondan türetilen
    değer (Elo) de dosya değişince atılmak üzere burada tutulur. Arka plan iş parçacıklarıyla yarışmasın diye kilitli;
    saniyeler süren Elo hesabı kilit dışında yapılır (arayüz iş parçacıklarının oku çağrıları beklemesin)."""

    def __init__(self):
        self._kilit = threading.RLock()
        self._hesap_kilidi = threading.Lock()  # aynı anda tek Elo hesabı; oku bunu beklemez
        self._d = {}

    def oku(self, yol):
        zaman = yol.stat().st_mtime
        with self._kilit:
            if self._d.get('yol') != yol or self._d.get('zaman') != zaman:
                self._d = dict(yol=yol, zaman=zaman, veri=json.loads(yol.read_text(encoding='utf-8')), elo=None)
            return self._d['veri']

    def elo(self, kur):
        """Önbellekteki veriden kur(veri) ile hesaplanan Elo; veri değişene kadar bir kez hesaplanır. Hesap sürerken dosya
        yenilendiyse sonuç eski veriye aittir: çağırana döner ama yeni verinin önbelleğine yazılmaz."""
        with self._hesap_kilidi:
            with self._kilit:
                d = self._d
                if d.get('elo') is not None:
                    return d['elo']
                veri = d['veri']
            sonuc = kur(veri)
            with self._kilit:
                if self._d is d:
                    d['elo'] = sonuc
            return sonuc


_OKUNAN = DosyaOnbellegi()


def oku(veri_klasoru):
    """Derlenmiş milli takım verisi (dosya değişmedikçe bellekten). Dosya yoksa None."""
    yol = Path(veri_klasoru) / 'milli.json'
    return _OKUNAN.oku(yol) if yol.exists() else None


def elo(veri_klasoru):
    """Milli takım Elo'su (dosya değişmedikçe bir kez hesaplanır). Veri yoksa None."""
    v = oku(veri_klasoru)
    if v is None:
        return None
    return _OKUNAN.elo(MilliElo)


def sezonlar(v, tid):
    """Turnuvanın sezonları, yeniden eskiye: [sezon adı]."""
    return sorted((v['turnuvalar'].get(str(tid)) or {}), key=lambda s: (_yil(s), s), reverse=True)


def mac_sozlugu(r, tid, sezon=None):
    """Derlenmiş maç satırı → sözlük; takım adları Türkçe (ulkeler.turkce)."""
    return {'id': r[0], 'tid': tid, 'zaman': r[1], 'evId': r[2], 'depId': r[3], 'ev': turkce(r[4]), 'dep': turkce(r[5]),
            'skor': (r[6], r[7]) if r[6] is not None else None, 'grup': r[8], 'tur': r[9], 'basladi': r[10], 'sezon': sezon}


def sezon_maclari(v, tid, sezon):
    return [mac_sozlugu(r, tid, sezon) for r in ((v['turnuvalar'].get(str(tid)) or {}).get(sezon) or {}).get('maclar', [])]


def sezon_gruplari(v, tid, sezon):
    """[(grup adı, [satır], [(renk, anlamı)])]; takım adları Türkçe."""
    return [(g[0], [{**r, 'ad': turkce(r['ad'])} for r in g[1]], g[2] if len(g) > 2 else [])
            for g in ((v['turnuvalar'].get(str(tid)) or {}).get(sezon) or {}).get('gruplar', [])]


def gelecek_maclar(v, takim):
    """Takımın oynanmamış maçları (bütün turnuvalardan, tarih sırasıyla)."""
    out = []
    for tid, *_ in TURNUVALAR:
        for s in sezonlar(v, tid):
            out += [m for m in sezon_maclari(v, tid, s) if m['skor'] is None and takim in (m['evId'], m['depId'])]
    return sorted({m['id']: m for m in out}.values(), key=lambda m: m['zaman'])


def _maclar(j, tid):
    """Ham FotMob verisinden bir turnuva sezonunun maçları (tarih sırasıyla)."""
    out = []
    for m in (j.get('fixtures') or {}).get('allMatches') or []:
        st = m.get('status') or {}
        if st.get('cancelled') or st.get('awarded'):
            continue
        skor = None
        if st.get('finished') and st.get('scoreStr'):
            try:
                skor = tuple(int(x) for x in st['scoreStr'].replace(' ', '').split('-')[:2])
            except ValueError:
                skor = None
        out.append({'id': m.get('id'), 'tid': tid, 'zaman': st.get('utcTime') or '', 'tur': m.get('roundName'),
                    'grup': m.get('group'), 'ev': m['home']['name'], 'dep': m['away']['name'],
                    'evId': int(m['home']['id']), 'depId': int(m['away']['id']), 'skor': skor,
                    'basladi': bool(st.get('started')) and not st.get('finished')})
    return sorted(out, key=lambda m: m['zaman'])


# grup tablolarındaki renklerin anlamı (FotMob'un açıklama anahtarına göre)
LEJANT = {
    'qualification_next_stage': 'Bir sonraki tura çıkar',
    'possible_qualification_next_stage': 'Sonraki tura çıkabilir (play-off ya da en iyi üçüncüler arasında)',
    'world_cup': 'Dünya Kupası\'na katılır',
    'championship_playoff': 'Şampiyonluk aşamasına (çeyrek final / final dörtlüsü) kalır',
    'promotion': 'Üst lige yükselir',
    'promotionqual': 'Yükselme play-off\'u oynar',
    'relegationqual': 'Düşme play-off\'u oynar',
    'possiblerelegation': 'Alt lige düşebilir',
    'relegation': 'Alt lige düşer',
}


def gruplar(j):
    """Grup tabloları: [(grup adı, [satır], [(renk, anlamı)])]; satır: ad, id, O, G, B, M, gol (ör. '6-0'), averaj, P,
    renk. Son liste, o grupta kullanılan renklerin açıklaması."""
    out = []
    for t in j.get('table') or []:
        veri = t.get('data') or {}
        parcalar = veri.get('tables') or ([veri] if veri.get('table') else [])
        for p in parcalar:
            satirlar = [{'ad': r['name'], 'id': r['id'], 'O': r['played'], 'G': r['wins'], 'B': r['draws'], 'M': r['losses'],
                         'gol': r.get('scoresStr', ''), 'av': r.get('goalConDiff', 0), 'P': r['pts'], 'renk': r.get('qualColor')}
                        for r in ((p.get('table') or {}).get('all') or [])]
            kullanilan = {r['renk'] for r in satirlar if r['renk']}
            lejant = []
            for l in p.get('legend') or veri.get('legend') or []:
                if l.get('color') in kullanilan and l.get('color') not in [x[0] for x in lejant]:
                    lejant.append((l['color'], LEJANT.get(l.get('tKey'), l.get('title') or '')))
            if satirlar:
                out.append((p.get('leagueName') or veri.get('leagueName') or '', satirlar, lejant))
    return out


class MilliElo:
    """Bütün turnuvaların oynanmış maçlarından milli takım Elo'su ve gol modeli."""

    def __init__(self, v):
        """v: derlenmiş milli takım verisi (oku())."""
        tum, goruldu = [], set()
        for tid, _, tur, tarafsiz in TURNUVALAR:
            for s in sezonlar(v, tid):
                for m in sezon_maclari(v, tid, s):
                    if m['skor'] is None or m['id'] in goruldu:
                        continue
                    goruldu.add(m['id'])
                    m['K'] = K[tur]
                    m['avantaj'] = mezban_yonu(tid, m['zaman'], m['ev'], m['dep'], s) if tarafsiz else 1
                    m['tarafsiz'] = bool(tarafsiz and not m['avantaj'])
                    tum.append(m)
        tum.sort(key=lambda m: m['zaman'])
        self.R, self.ad, self.mac_sayisi, self.son_mac = {}, {}, {}, {}
        self.gecmis = {}  # takım -> maç maç kayıt (eskiden yeniye): rakip, skor, turnuva, Elo öncesi/sonrası
        self.v = v
        egitim = []  # (Elo farkı, ev golü, dep golü) gol modeli için
        for m in tum:
            h, a = m['evId'], m['depId']
            rh, ra = self.R.get(h, 1500.0), self.R.get(a, 1500.0)
            dr = rh - ra + m['avantaj'] * EV_AVANTAJI
            hg, ag = m['skor']
            egitim.append((dr, hg, ag))
            beklenen = 1 / (10 ** (-dr / 400) + 1)
            sonuc = 1 if hg > ag else 0.5 if hg == ag else 0
            fark = abs(hg - ag)
            G = 1 if fark <= 1 else 1.5 if fark == 2 else (11 + fark) / 8
            P = m['K'] * G * (sonuc - beklenen)
            self.R[h], self.R[a] = rh + P, ra - P
            for t, rakip, rakip_ad, ev, ats, yen, once in ((h, a, m['dep'], True, hg, ag, rh), (a, h, m['ev'], False, ag, hg, ra)):
                self.gecmis.setdefault(t, []).append({
                    'zaman': m['zaman'], 'tid': m['tid'], 'rakip': rakip, 'rakip_ad': rakip_ad, 'ev': ev, 'tarafsiz': m['tarafsiz'],
                    'atilan': ats, 'yenilen': yen, 'once': once, 'sonra': self.R[t], 'grup': m.get('grup')})
            for t, ad in ((h, m['ev']), (a, m['dep'])):
                self.ad[t] = ad
                self.mac_sayisi[t] = self.mac_sayisi.get(t, 0) + 1
                self.son_mac[t] = m['zaman'][:10]
        self.n_mac = len(tum)
        self.a, self.b = self._gol_modeli(egitim)

    @staticmethod
    def _gol_modeli(veri):
        """Poisson regresyonu: ev golü ~ exp(a + b·dr/400), deplasman golü ~ exp(a − b·dr/400). Newton yöntemi."""
        if not veri:
            return math.log(1.3), 0.6
        a, b = math.log(1.3), 0.6
        for _ in range(30):
            ga = gb = haa = hab = hbb = 0.0
            for dr, hg, ag in veri:
                x = dr / 400
                for y, s in ((hg, 1), (ag, -1)):
                    lam = math.exp(a + s * b * x)
                    ga += y - lam
                    gb += (y - lam) * s * x
                    haa -= lam
                    hab -= lam * s * x
                    hbb -= lam * x * x
            det = haa * hbb - hab * hab
            if abs(det) < 1e-12:
                break
            da = (hbb * ga - hab * gb) / det
            db = (haa * gb - hab * ga) / det
            a, b = a - da, b - db
            if abs(da) < 1e-9 and abs(db) < 1e-9:
                break
        return a, b

    def tahmin(self, h, a, tarafsiz=False, avantaj=None):
        """avantaj: +1 ev sahibi, -1 deplasman takımı mezban, 0 tarafsız (verilirse tarafsiz'i geçersiz kılar)."""
        if avantaj is None:
            avantaj = 0 if tarafsiz else 1
        dr = self.R.get(h, 1500.0) - self.R.get(a, 1500.0) + avantaj * EV_AVANTAJI
        lh, la = math.exp(self.a + self.b * dr / 400), math.exp(self.a - self.b * dr / 400)
        p, hucreler = sonuc_olasiliklari(lh, la)
        return {'lh': lh, 'la': la, 'p': p, 'hucreler': hucreler,
                'skorlar': sorted(hucreler, key=lambda c: -c[2])[:5]}

    def siralama(self, en_az_mac=8, son_yil=4):
        """Elo sıralaması: son yıllarda maç yapmış ve yeterli maçı olan takımlar."""
        sinir = f'{datetime.now(timezone.utc).year - son_yil}'
        return sorted(({'id': t, 'ad': self.ad[t], 'elo': r, 'mac': self.mac_sayisi[t], 'son': self.son_mac[t]}
                       for t, r in self.R.items() if self.mac_sayisi[t] >= en_az_mac and self.son_mac[t] >= sinir),
                      key=lambda x: -x['elo'])
