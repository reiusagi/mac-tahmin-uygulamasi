"""Avrupa kupaları: Şampiyonlar Ligi, Avrupa Ligi ve Konferans Ligi (FotMob). Fikstür, lig aşaması puan durumu, eleme
ağacı, kulüp Elo'su ve sezon sonu simülasyonu.

Kulüp Elo'su 2016'dan bu yana iki tür maçtan hesaplanır:
  - uygulamadaki liglerin maçları (FotMob lig sayfaları): ligin içindeki güç farkı
  - üç kupanın ve elemelerinin bütün maçları: ligler ve ülkeler arası güç farkı
Takım ilk görüldüğünde ligine göre bir başlangıç puanı alır (LIG_BASLANGIC; uygulamada ligi olmayan küçük ülke
takımları KUPA_BASLANGIC); lige sonradan katılan (yükselen) takım ligin alt dilimden başlar. Gol beklentisi Elo
farkından Poisson regresyonuyla (kupa maçları) öğrenilir.

Sezon simülasyonu (2024/25'ten beri geçerli biçim): 36 takımlı lig aşamasının kalan maçları oynatılır; ilk 8 son 16'ya,
9-24 play-off turuna kalır, 25-36 elenir. Eleme turları iki maçlı (eşitlikte uzatma, sonra penaltı), final tek maç ve
tarafsız sahada. Kura UEFA'nın sabit ağacına göre çekilir: seri başı çiftleri (1-2, 3-4, 5-6, 7-8) ağacın iki yarısına
dağılır, play-off'ta 9-10 ile 23-24, 11-12 ile 21-22, 13-14 ile 19-20, 15-16 ile 17-18 eşleşir. Gerçekleşmiş kura ve
maçlar (FotMob'un eleme ağacı) olduğu gibi kullanılır.

Yeni kupa eklemek: KUPALAR'a (FotMob kimliği, Türkçe ad) ekle; biçimi farklıysa simülasyonu uyarla."""
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import sema
from .logo import LIG_LOGO as LOGO, TAKIM_LOGO  # noqa: F401  (eski adlar)
from .milli import DosyaOnbellegi, MilliElo, _getir, _yil, _yol
from .modeller import sonuc_olasiliklari
from .sezon import FOTMOB_ID, LIGLER, SON_SEZON, TAKVIM_YILI
from .veri import fotmob_url, onbellekli

logger = logging.getLogger(__name__)

KUPALAR = [(42, 'Şampiyonlar Ligi'), (73, 'Avrupa Ligi'), (10216, 'Konferans Ligi')]
ELEMELER = [(10611, 'Şampiyonlar Ligi Elemeleri'), (10613, 'Avrupa Ligi Elemeleri'), (10615, 'Konferans Ligi Elemeleri')]
# yerel kupalar: fikstür, gruplar ve eleme ağacı (simülasyon ve Elo yok); süren ve geçen sezon
YEREL_KUPALAR = [(151, 'Türkiye Kupası'), (132, 'FA Cup'), (133, 'Lig Kupası (İngiltere)'), (138, 'Copa del Rey'),
                 (141, 'Coppa Italia'), (209, 'DFB Pokal'), (134, 'Fransa Kupası'), (186, 'Portekiz Kupası'),
                 (235, 'Hollanda Kupası'), (137, 'İskoçya Kupası')]
YEREL = {k for k, _ in YEREL_KUPALAR}
KUPA = dict(KUPALAR + YEREL_KUPALAR)
ILK_YIL = 2016
GUNCEL_YENILE_SAAT = 6

# son altı sezonun kupa maçlarındaki log-kayba göre seçildi (K 20/30/40, ev avantajı 50-100 denendi; fark küçük)
K_LIG, K_KUPA = 20, 30
EV_LIG, EV_KUPA = 80, 80
KUPA_BASLANGIC = 1380  # uygulamada ligi olmayan (küçük ülke) takımların başlangıcı
BELIRSIZ_MAC = 60  # ligi uygulamada olmayan takımın bundan az maçı varsa "tahmin çok belirsiz" uyarısı (KulupElo.belirsizlik)
LIG_BASLANGIC = {47: 1720, 87: 1700, 55: 1690, 54: 1690, 53: 1660, 61: 1600, 57: 1590, 40: 1560, 71: 1550, 48: 1560,
                 64: 1500, 38: 1520, 69: 1500, 135: 1510, 59: 1460, 536: 1450, 268: 1500, 112: 1500}
YUKSELEN_DILIM = 0.2  # lige yeni katılan takım, ligdeki takımların bu dilimindeki puandan başlar
# Elo'yu besleyen ek ligler: Avrupa kupalarına takım gönderen, uygulamanın tahmin sekmelerinde olmayan ülkelerin üst ligi
# (FotMob kimliği: ülke). Yalnızca kulüp Elo'suna girer: bu takımların gücü lig sonuçlarıyla güncel kalır. Karne
# düzeninde iki yönlü sınandı (8.174 kupa maçı, tek / çift sezonlar): iki yönde de log-kayıp ~0,004, ek ligli takımların
# maçlarında ~0,007 düştü; iki yön de aynı ayarı seçti (K 10; başlangıç 1350 / 1400 → 1375).
EK_LIGLER = {122: 'Çekya', 46: 'Danimarka', 196: 'Polonya', 252: 'Hırvatistan', 182: 'Sırbistan', 127: 'İsrail',
             136: 'Kıbrıs', 441: 'Ukrayna', 67: 'İsveç', 212: 'Macaristan', 189: 'Romanya', 262: 'Azerbaycan',
             270: 'Bulgaristan', 176: 'Slovakya', 173: 'Slovenya', 225: 'Kazakistan', 51: 'Finlandiya', 126: 'İrlanda',
             267: 'Bosna-Hersek', 439: 'Gürcistan', 118: 'Ermenistan', 260: 'Arnavutluk', 231: 'Moldova',
             249: 'Kuzey Makedonya'}
K_EK = 10  # ek liglerin maçlarında Elo katsayısı (uygulamadaki liglerde K_LIG)
EK_BASLANGIC = 1375  # ek ligin takımlarının başlangıç puanı
EK_YENILE_SAAT = 24  # ek liglerin süren sezonu bu kadar saatte bir yeniden indirilir

ELEME_TURLARI = ['playoff', '1/8', '1/4', '1/2', 'final']  # simülasyondaki turlar (yeni biçim)
GOSTERIM_TURLARI = ['1/64', '1/32', '1/16', 'playoff', '1/8', '1/4', '1/2', 'final']  # eski sezonlar ve yerel kupalar
TUR_ADI = {'1/64': 'Son 128', '1/32': 'Son 64', '1/16': 'Son 32', 'playoff': 'Play-off turu', '1/8': 'Son 16',
           '1/4': 'Çeyrek final', '1/2': 'Yarı final', 'final': 'Final'}
TUR_SAYISI = {'playoff': 8, '1/8': 8, '1/4': 4, '1/2': 2, 'final': 1}
# son 16 ağacı: sıra k'deki eşleşmede seri başı çiftinden biri, sıra k'deki play-off eşleşmesinin galibiyle oynar
# (ağacın iki yarısı aynı sırada: 0-3 ve 4-7). Her öğe: (seri başı çifti, play-off'ta ikinci maçı evinde oynayan çift,
# play-off'ta ilk maçı evinde oynayan çift)
AGAC = [((5, 6), (11, 12), (21, 22)), ((3, 4), (13, 14), (19, 20)), ((7, 8), (9, 10), (23, 24)), ((1, 2), (15, 16), (17, 18))]


def tur_adi(tur, yerel=False):
    """'3' → 'Lig aşaması · 3. hafta' (yerel kupada '3. tur'), 'playoff' → 'Play-off turu'."""
    tur = str(tur)
    if tur in ('None', ''):
        return 'Maçlar'
    if tur.isdigit():
        return f'{tur}. tur' if yerel else f'Lig aşaması · {tur}. hafta'
    return TUR_ADI.get(tur, tur)


# ---------------------------------------------------------------- indirme ve derleme

def _sezon_adi(lid, y):
    takvim = any(FOTMOB_ID[k] == lid for k in TAKVIM_YILI)
    return str(y) if takvim else f'{y}/{y + 1}'


def indir(ham, cikti, yenile_guncel=False, yaz=None, zorla=()):
    """Kupaların ve elemelerinin ILK_YIL'dan bu yana sezonlarını, Elo için de uygulamadaki liglerin eksik eski
    sezonlarını indirir (önbellekte olanlar atlanır); bir şey indirildiyse cikti/avrupa.json'u yeniden derler.
    zorla: süren sezonu yaşına bakmadan yenilenecek kupalar (True: hepsi)."""
    hata, indirilen = 0, 0
    for kid, ad in KUPALAR + ELEMELER + YEREL_KUPALAR:
        try:
            guncel = _yol(ham, kid, klasor='avrupa')
            eski = not guncel.exists() or time.time() - guncel.stat().st_mtime > GUNCEL_YENILE_SAAT * 3600 \
                or zorla is True or kid in zorla
            indirilen += eski and (yenile_guncel or not guncel.exists())
            j = _getir(ham, kid, yenile=yenile_guncel and eski, klasor='avrupa')
            secili = (j.get('details') or {}).get('selectedSeason')
            ilk = SON_SEZON - 1 if kid in YEREL else ILK_YIL  # yerel kupalarda yalnızca süren ve geçen sezon
            for s in j.get('allAvailableSeasons') or []:
                if _yil(s) < ilk or s == secili:
                    continue
                indirilen += not _yol(ham, kid, s, 'avrupa').exists()
                _getir(ham, kid, s, klasor='avrupa')
            if yaz:
                yaz(f'{ad}: tamam')
        except Exception as ex:
            hata += 1
            if yaz:
                yaz(f'{ad}: indirilemedi ({ex})')
    # Elo için ligin eski sezonları (uygulama bazı ligleri daha geç bir yıldan başlatıyor); alınamayan bir daha denenmez
    eksik_yol = Path(ham) / 'avrupa' / 'alinamayan.json'
    alinamayan = set(json.loads(eksik_yol.read_text(encoding='utf-8'))) if eksik_yol.exists() else set()
    yurtici_yol = Path(cikti) / 'avrupa_yurtici.json'
    var = set()  # derlenmiş dosyada zaten bulunan (lig, yıl): masaüstü uygulaması bunları yeniden indirmez
    if yurtici_yol.exists():
        var = {(r[6], int(r[1][:4])) for r in json.loads(yurtici_yol.read_text(encoding='utf-8'))}
    # ek ligler (EK_LIGLER): süren sezon EK_YENILE_SAAT'te bir; eski sezonlar yalnızca derlenmiş dosyada yoksa
    for lid, ad in EK_LIGLER.items():
        try:
            guncel = _yol(ham, lid, klasor='ek_lig')
            eski = not guncel.exists() or time.time() - guncel.stat().st_mtime > EK_YENILE_SAAT * 3600 or zorla is True
            indirilen += eski and (yenile_guncel or not guncel.exists())
            j = _getir(ham, lid, yenile=yenile_guncel and eski, klasor='ek_lig')
            secili = (j.get('details') or {}).get('selectedSeason')
            for s in j.get('allAvailableSeasons') or []:
                y = _yil(s)
                if y < ILK_YIL or s == secili or ((lid, y) in var and (lid, y + 1) in var):
                    continue
                indirilen += not _yol(ham, lid, s, 'ek_lig').exists()
                _getir(ham, lid, s, klasor='ek_lig')
        except Exception as ex:
            hata += 1
            if yaz:
                yaz(f'{ad} ligi: indirilemedi ({ex})')
    for lid in FOTMOB_ID.values():
        for y in range(ILK_YIL, SON_SEZON):
            yol = Path(ham) / f'fm-{lid}-{y}.json'
            if yol.exists() or yol.name in alinamayan or ((lid, y) in var and (lid, y + 1) in var):
                continue
            sezon = _sezon_adi(lid, y)
            try:
                sema.kontrol('kupa', onbellekli(yol, fotmob_url('leagues', id=lid, season=sezon)))
                indirilen += 1
            except Exception:
                logger.warning('FotMob sezonu alınamadı: %s', yol.name, exc_info=True)
                alinamayan.add(yol.name)
    eksik_yol.parent.mkdir(parents=True, exist_ok=True)
    eksik_yol.write_text(json.dumps(sorted(alinamayan)), encoding='utf-8')
    if indirilen or not (Path(cikti) / 'avrupa.json').exists():
        derle(ham, cikti)
    return hata


def _skor(st):
    if not (st.get('finished') and st.get('scoreStr')):
        return None
    try:
        return tuple(int(x) for x in st['scoreStr'].replace(' ', '').split('-')[:2])
    except ValueError:
        return None


def _maclar(j):
    """[id, zaman, ev id, dep id, ev, dep, ev golü, dep golü, tur, başladı mı, penaltıyla mı]; iptaller hariç."""
    out = []
    for m in (j.get('fixtures') or {}).get('allMatches') or []:
        st = m.get('status') or {}
        if st.get('cancelled') or st.get('awarded'):
            continue
        s = _skor(st)
        out.append([int(m['id']), st.get('utcTime') or '', int(m['home']['id']), int(m['away']['id']), m['home']['name'],
                    m['away']['name'], *(s or (None, None)), str(m.get('round')), bool(st.get('started')) and not st.get('finished'),
                    (st.get('reason') or {}).get('shortKey') == 'penalties_short'])
    return sorted(out, key=lambda r: r[1])


def _tablo(j):
    """Puan durumları: [(grup adı, [[id, ad, O, G, B, M, gol, averaj, P]])]. 2024/25'ten beri tek tablo (36 takımlı lig
    aşaması, adı ''); önceki sezonlarda 4'er takımlı gruplar."""
    out = []
    for t in j.get('table') or []:
        veri = t.get('data') or {}
        for p in veri.get('tables') or ([veri] if veri.get('table') else []):
            satirlar = (p.get('table') or {}).get('all') or []
            if satirlar:
                ad = (p.get('leagueName') or '').split('Grp.')[-1].strip() if 'Grp.' in (p.get('leagueName') or '') else ''
                out.append((ad, [[r['id'], r['name'], r['played'], r['wins'], r['draws'], r['losses'], r.get('scoresStr', ''),
                                  r.get('goalConDiff', 0), r['pts']] for r in satirlar]))
    return out


def lig_asamasi(S):
    """Sezonun 36 takımlı lig aşaması tablosu (yeni biçim); eski grup biçiminde None."""
    return S['tablo'][0][1] if S and len(S['tablo']) == 1 and len(S['tablo'][0][1]) >= 24 else None


def _eleme(j):
    """Eleme ağacı: [tur, kura sırası, ev (ilk maçın ev sahibi), dep, kazanan, [[maç id, ev, dep, ev golü, dep golü]]]."""
    out = []
    for r in (j.get('playoff') or {}).get('rounds') or []:
        for m in r.get('matchups') or []:
            ayaklar = []
            for x in m.get('matches') or []:
                st = x.get('status') or {}
                bitti = st.get('finished') and not st.get('cancelled')
                ayaklar.append([x.get('matchId'), (x.get('home') or {}).get('id'), (x.get('away') or {}).get('id'),
                                (x.get('home') or {}).get('score') if bitti else None,
                                (x.get('away') or {}).get('score') if bitti else None])
            # kura çekilmeden FotMob o anki sıralamaya göre iki olası eşleşme gösterir (hasTwoPossibleMatchups; bir önceki
            # turun galibi eksi id'yle): kura çekilene kadar takımlar belli değil sayılır
            olasi = m.get('hasTwoPossibleMatchups')
            ev = None if m.get('tbdTeam1') or olasi or (m.get('homeTeamId') or 0) < 0 else m.get('homeTeamId')
            dep = None if m.get('tbdTeam2') or olasi or (m.get('awayTeamId') or 0) < 0 else m.get('awayTeamId')
            out.append([r.get('stage'), m.get('drawOrder') or 1, ev, dep, m.get('aggregatedWinner') or m.get('winner'), ayaklar])
    return out


def _ham_sezonlar(ham, kid):
    out = {}
    for f in (Path(ham) / 'avrupa').glob(f'fm-{kid}-*.json'):
        try:
            j = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            logger.warning('ham kupa dosyası okunamadı: %s', f.name, exc_info=True)
            continue
        s = (j.get('details') or {}).get('selectedSeason')
        if s and _yil(s) >= ILK_YIL:
            out[s] = j
    return out


def _yurtici(ham, cikti):
    """Uygulamadaki liglerin 2016'dan bu yana oynanmış maçları: [id, zaman, ev, dep, ev golü, dep golü, lig]. Önceki
    derlemeler cikti/avrupa_yurtici.json'da birikir (masaüstü uygulaması eski sezonların ham verisi olmadan da kullanır)."""
    yol = Path(cikti) / 'avrupa_yurtici.json'
    maclar = {}
    if yol.exists():
        maclar = {r[0]: r for r in json.loads(yol.read_text(encoding='utf-8'))}
    for lid in FOTMOB_ID.values():
        for f in Path(ham).glob(f'fm-{lid}-*.json'):
            parca = f.stem.split('-')
            if len(parca) != 3 or not parca[2].isdigit() or int(parca[2]) < ILK_YIL:
                continue
            try:
                j = json.loads(f.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                logger.warning('ham lig dosyası okunamadı: %s', f.name, exc_info=True)
                continue
            for r in _maclar(j):
                if r[6] is not None:
                    maclar[r[0]] = [r[0], r[1], r[2], r[3], r[6], r[7], lid]
    for f in (Path(ham) / 'ek_lig').glob('fm-*.json'):  # Elo'yu besleyen ek ligler (EK_LIGLER)
        parca = f.stem.split('-')
        if len(parca) < 3 or not parca[1].isdigit() or int(parca[1]) not in EK_LIGLER:
            continue
        try:
            j = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            logger.warning('ek lig dosyası okunamadı: %s', f.name, exc_info=True)
            continue
        for r in _maclar(j):
            if r[6] is not None and r[1][:4] >= str(ILK_YIL):
                maclar[r[0]] = [r[0], r[1], r[2], r[3], r[6], r[7], int(parca[1])]
    liste = sorted(maclar.values(), key=lambda r: r[1])
    gecici = yol.with_suffix('.tmp')
    gecici.write_text(json.dumps(liste, separators=(',', ':')), encoding='utf-8')
    gecici.replace(yol)
    return liste


def derle(ham, cikti):
    """cikti/avrupa.json: {'kupalar': {kimlik: {sezon: {'maclar', 'tablo', 'eleme'}}}, 'elemeler': [maç], 'takimlar'}
    ve cikti/avrupa_yurtici.json (Elo için lig maçları)."""
    out = {'guncellendi': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'kupalar': {}, 'elemeler': [], 'takimlar': {}}
    for kid, _ in KUPALAR + YEREL_KUPALAR:
        out['kupalar'][str(kid)] = {}
        for s, j in _ham_sezonlar(ham, kid).items():
            if kid in YEREL and _yil(s) < SON_SEZON - 1:
                continue
            maclar = _maclar(j)
            out['kupalar'][str(kid)][s] = {'maclar': maclar, 'tablo': _tablo(j), 'eleme': _eleme(j)}
            for r in maclar:
                out['takimlar'][str(r[2])], out['takimlar'][str(r[3])] = r[4], r[5]
    goruldu = set()
    for kid, _ in ELEMELER:
        for j in _ham_sezonlar(ham, kid).values():
            for r in _maclar(j):
                if r[6] is not None and r[0] not in goruldu:
                    goruldu.add(r[0])
                    out['elemeler'].append([r[0], r[1], r[2], r[3], r[6], r[7]])
                    out['takimlar'].setdefault(str(r[2]), r[4])
                    out['takimlar'].setdefault(str(r[3]), r[5])
    _yurtici(ham, cikti)
    yol = Path(cikti) / 'avrupa.json'
    gecici = yol.with_suffix('.tmp')
    gecici.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    gecici.replace(yol)


_OKUNAN = DosyaOnbellegi()


def oku(veri_klasoru):
    """Derlenmiş kupa verisi (dosya değişmedikçe bellekten). Dosya yoksa None."""
    yol = Path(veri_klasoru) / 'avrupa.json'
    return _OKUNAN.oku(yol) if yol.exists() else None


def elo(veri_klasoru):
    """Kulüp Elo'su (veri değişmedikçe bir kez hesaplanır). Veri yoksa None."""
    v = oku(veri_klasoru)
    if v is None:
        return None
    def kur(veri):
        yol = Path(veri_klasoru) / 'avrupa_yurtici.json'
        yurtici = json.loads(yol.read_text(encoding='utf-8')) if yol.exists() else []
        return KulupElo(veri, yurtici)
    return _OKUNAN.elo(kur)


def sezonlar(v, kid):
    return sorted(v['kupalar'].get(str(kid)) or {}, key=lambda s: (_yil(s), s), reverse=True)


def sezon(v, kid, s):
    return (v['kupalar'].get(str(kid)) or {}).get(s)


# ---------------------------------------------------------------- kulüp Elo'su

_GECMIS_ALAN = ('zaman', 'rakip', 'ev', 'atilan', 'yenilen', 'turnuva')


class _Gecmis(dict):
    """Takım → maç maç kayıtlar (eskiden yeniye). Bellekte demet olarak tutulur (ek liglerle 230 binden çok kayıt:
    sözlük olarak ~100 MB tutardı), get() sözlük listesi döndürür: {'zaman', 'rakip', 'ev', 'atilan', 'yenilen', 'turnuva'}."""

    def get(self, t, varsayilan=None):
        v = super().get(t)
        return varsayilan if v is None else [dict(zip(_GECMIS_ALAN, x)) for x in v]


class KulupElo:
    def __init__(self, v, yurtici):
        self.ad = {int(k): a for k, a in v['takimlar'].items()}
        # olay: (zaman, ev, dep, ev golü, dep golü, K, ev avantajı, lig id (lig maçıysa), kupa mı, turnuva adı)
        lig_adi = {FOTMOB_ID[l[0]]: l[1] for l in LIGLER if l[0] in FOTMOB_ID}
        lig_adi.update({lid: f'{ulke} ligi' for lid, ulke in EK_LIGLER.items()})
        olaylar = [(r[1], r[2], r[3], r[4], r[5], K_EK if r[6] in EK_LIGLER else K_LIG, EV_LIG, r[6], False,
                    lig_adi.get(r[6], 'Lig')) for r in yurtici]
        goruldu = set()
        for kid, kupa_adi in KUPALAR:
            for s in (v['kupalar'].get(str(kid)) or {}).values():
                for r in s['maclar']:
                    if r[6] is not None and r[0] not in goruldu:
                        goruldu.add(r[0])
                        final = r[8] == 'final'
                        olaylar.append((r[1], r[2], r[3], r[6], r[7], K_KUPA, 0 if final else EV_KUPA, None, True, kupa_adi))
        for r in v['elemeler']:
            if r[0] not in goruldu:
                olaylar.append((r[1], r[2], r[3], r[4], r[5], K_KUPA, EV_KUPA, None, True, 'Avrupa elemeleri'))
        olaylar.sort(key=lambda o: o[0])
        ilk_lig = {}
        for o in olaylar:
            if o[7] is not None:
                ilk_lig.setdefault(o[1], o[7])
                ilk_lig.setdefault(o[2], o[7])
        self.R, self.lig, self.mac_sayisi, self.son_mac = {}, {}, {}, {}
        self.gecmis = _Gecmis()  # takım -> maç maç kayıt (eskiden yeniye): rakip, skor, turnuva (lig maçları ve kupalar)
        egitim, sinir = [], f'{SON_SEZON - 6}-07'

        def baslangic(t, lid):
            lid = lid if lid is not None else ilk_lig.get(t)
            if lid is None:
                return KUPA_BASLANGIC
            ligdekiler = sorted(r for u, r in self.R.items() if self.lig.get(u) == lid)
            if len(ligdekiler) >= 10:  # lige yeni katılan (yükselen) takım
                return ligdekiler[int(len(ligdekiler) * YUKSELEN_DILIM)]
            return LIG_BASLANGIC.get(lid, EK_BASLANGIC if lid in EK_LIGLER else 1500)

        for zaman, h, a, hg, ag, k, ev, lid, kupa, turnuva in olaylar:
            for t in (h, a):
                if t not in self.R:
                    self.R[t] = baslangic(t, lid)
                if lid is not None:
                    self.lig[t] = lid
            rh, ra = self.R[h], self.R[a]
            dr = rh - ra + ev
            if kupa and zaman >= sinir:
                egitim.append((dr, hg, ag))
            beklenen = 1 / (10 ** (-dr / 400) + 1)
            sonuc = 1 if hg > ag else 0.5 if hg == ag else 0
            fark = abs(hg - ag)
            G = 1 if fark <= 1 else 1.5 if fark == 2 else (11 + fark) / 8
            P = k * G * (sonuc - beklenen)
            self.R[h], self.R[a] = rh + P, ra - P
            for t, rakip, evde, ats, yen in ((h, a, True, hg, ag), (a, h, False, ag, hg)):
                self.gecmis.setdefault(t, []).append((zaman, rakip, evde, ats, yen, turnuva))  # alanlar: _GECMIS_ALAN
            for t in (h, a):
                self.mac_sayisi[t] = self.mac_sayisi.get(t, 0) + 1
                self.son_mac[t] = zaman[:10]
        self.n_mac = len(olaylar)
        self.a, self.b = MilliElo._gol_modeli(egitim)
        # gol modelinin kupa maçlarındaki başarısı (son iki sezon; maç öncesi Elo ile)
        son = egitim[-600:]
        self.log_kayip = (sum(-math.log(max(1e-9, self._olasilik(dr)[0 if hg > ag else 1 if hg == ag else 2]))
                              for dr, hg, ag in son) / len(son)) if son else None

    def puan(self, t):
        return self.R.get(t, KUPA_BASLANGIC)

    def belirsizlik(self, t, ad):
        """Model takımı az tanıyorsa uyarı metni, tanıyorsa None. Ligi uygulamada olmayan takımın puanı yalnızca Avrupa
        maçlarından gelir: o sezonki lig formu, kadrosu bilinmez; BELIRSIZ_MAC'tan az maçta puan da henüz oturmamıştır."""
        if t in self.lig:
            return None
        n = self.mac_sayisi.get(t, 0)
        if n == 0:
            return f'{ad}: modelde hiç maçı yok, başlangıç puanıyla tahmin edildi; tahmin çok belirsiz.'
        return (f'{ad}: ligi uygulamada değil, yalnızca {n} Avrupa maçından tanınıyor (bu sezonki lig formu ve kadrosu '
                'bilinmiyor)' + ('; puanı henüz oturmadı, tahmin çok belirsiz.' if n < BELIRSIZ_MAC else '; tahmin daha belirsiz.'))

    def _olasilik(self, dr):
        p, _ = sonuc_olasiliklari(math.exp(self.a + self.b * dr / 400), math.exp(self.a - self.b * dr / 400))
        return p

    def beklenen_gol(self, h, a, tarafsiz=False):
        dr = self.puan(h) - self.puan(a) + (0 if tarafsiz else EV_KUPA)
        return math.exp(self.a + self.b * dr / 400), math.exp(self.a - self.b * dr / 400)

    def tahmin(self, h, a, tarafsiz=False):
        lh, la = self.beklenen_gol(h, a, tarafsiz)
        p, hucreler = sonuc_olasiliklari(lh, la)
        return {'lh': lh, 'la': la, 'p': p, 'skorlar': sorted(hucreler, key=lambda c: -c[2])[:5]}


# ---------------------------------------------------------------- sezon sonu simülasyonu

def lig_sirasi(pts, av, gf, gf_dep, gal, gal_dep, kura):
    """36 takımlı lig aşamasının sırası (simülasyon başına satır, her satırda 0. sütun birinci takım). UEFA eşitlik sırası
    (verinin elverdiği kadar): puan, averaj, atılan gol, deplasmanda atılan gol, galibiyet, deplasman galibiyeti; rakiplerin
    puanı, disiplin ve katsayı verisi yok, kalan eşitlik kurayla. Ölçütler ayrı anahtar olduğundan büyük gol sayıları
    birbirini ezmez (np.lexsort'ta son anahtar öncelikli)."""
    return np.lexsort((kura, -gal_dep, -gal, -gf_dep, -gf, -av, -pts), axis=1)


def simulasyon(v, E, kid, s, N=10000, tohum=None):
    """Kupanın bu sezonunu N kez sonuna kadar oynatır. Döner: takım listesi ve olasılıklar (lig aşaması sırası, tur
    tur ilerleme, şampiyonluk), tur tur rakip olasılıkları, final eşleşmeleri ve ilk simülasyonun ayrıntılı ağacı
    (örnek senaryo). Lig aşaması verisi (36 takım) yoksa None."""
    S = sezon(v, kid, s)
    tablo = lig_asamasi(S)
    if not tablo:
        return None
    rng = np.random.default_rng(tohum)
    takimlar = [r[0] for r in tablo]
    n = len(takimlar)
    ix = {t: i for i, t in enumerate(takimlar)}
    R = np.array([E.puan(t) for t in takimlar])

    def lam(ev, dep, tarafsiz=False):
        dr = R[ev] - R[dep] + (0 if tarafsiz else EV_KUPA)
        return np.exp(E.a + E.b * dr / 400), np.exp(E.a - E.b * dr / 400)

    # ---- lig aşaması
    pts, av, ag_, dep_gol, gal, dep_gal = (np.zeros((N, n)) for _ in range(6))  # puan, averaj, gol, dep. golü, galibiyet, dep. gal.
    kalan = []
    for r in S['maclar']:
        if not r[8].isdigit() or r[2] not in ix or r[3] not in ix:
            continue
        h, a = ix[r[2]], ix[r[3]]
        if r[6] is not None:
            pts[:, h] += 3 if r[6] > r[7] else 1 if r[6] == r[7] else 0
            pts[:, a] += 3 if r[7] > r[6] else 1 if r[6] == r[7] else 0
            av[:, h] += r[6] - r[7]
            av[:, a] += r[7] - r[6]
            ag_[:, h] += r[6]
            ag_[:, a] += r[7]
            dep_gol[:, a] += r[7]
            gal[:, h] += r[6] > r[7]
            gal[:, a] += r[7] > r[6]
            dep_gal[:, a] += r[7] > r[6]
        else:
            kalan.append((h, a))
    for h, a in kalan:
        lh, la = lam(h, a)
        gh, ga = rng.poisson(lh, N), rng.poisson(la, N)
        pts[:, h] += np.where(gh > ga, 3, np.where(gh == ga, 1, 0))
        pts[:, a] += np.where(ga > gh, 3, np.where(gh == ga, 1, 0))
        av[:, h] += gh - ga
        av[:, a] += ga - gh
        ag_[:, h] += gh
        ag_[:, a] += ga
        dep_gol[:, a] += ga
        gal[:, h] += gh > ga
        gal[:, a] += ga > gh
        dep_gal[:, a] += ga > gh
    if kalan:  # UEFA eşitlik sırası (lig_sirasi); kalan eşitlikler kurayla
        sira = lig_sirasi(pts, av, ag_, dep_gol, gal, dep_gal, rng.random((N, n)))  # sira[i, k]: k+1. sıradaki takım
    else:  # lig aşaması bitti: FotMob'un sıralaması (UEFA'nın bütün eşitlik kurallarıyla)
        sira = np.tile(np.arange(n), (N, 1))
    yer = np.empty_like(sira)
    yer[np.arange(N)[:, None], sira] = np.arange(n)  # yer[i, t]: takımın sırası (0'dan)

    # ---- eleme turları
    eleme = {}
    for tur, sira_no, ev, dep, kazanan, ayaklar in S['eleme']:
        eleme.setdefault(tur, []).append((sira_no, ev, dep, kazanan, ayaklar))
    bilinen = {tur: sorted(m) for tur, m in eleme.items()
               if len(m) == TUR_SAYISI.get(tur) and all(x[1] in ix and x[2] in ix for x in m)}
    tum = np.arange(N)
    rakip = np.zeros((len(ELEME_TURLARI), n, n))  # [tur, takım, rakip] sayısı
    ulasti = np.zeros((len(ELEME_TURLARI) + 1, n))  # turlara kalma sayısı; son satır şampiyonluk
    ornek = []  # ilk simülasyonun eşleşmeleri: (tur, ev, dep, ev toplam, dep toplam, kazanan, not)

    def iki_mac(A, B, ayaklar=None, kazanan=None, tarafsiz=False, tur=''):
        """A ilk maçın ev sahibi, B ikincinin (finalde tek maç, tarafsız). Gerçekleşmiş ayaklar sabit."""
        if tarafsiz:
            lh, la = lam(A, B, True)
            ga, gb = rng.poisson(lh), rng.poisson(la)
            uz_a, uz_b = lam(A, B, True)
        else:
            ga, gb = np.zeros(N, int), np.zeros(N, int)
            for k, (ev_, dep_) in enumerate(((A, B), (B, A))):
                sabit = ayaklar[k] if ayaklar and k < len(ayaklar) and ayaklar[k][3] is not None else None
                if sabit:
                    e_gol, d_gol = (sabit[3], sabit[4]) if sabit[1] == takimlar[ev_[0]] else (sabit[4], sabit[3])
                    g1, g2 = np.full(N, e_gol), np.full(N, d_gol)
                else:
                    l1, l2 = lam(ev_, dep_)
                    g1, g2 = rng.poisson(l1), rng.poisson(l2)
                if k == 0:
                    ga, gb = ga + g1, gb + g2
                else:
                    gb, ga = gb + g1, ga + g2
            uz_b, uz_a = lam(B, A)
        esit = ga == gb
        ua, ub = rng.poisson(uz_a / 3), rng.poisson(uz_b / 3)  # uzatma: maçın üçte biri
        pen = rng.random(N) < 0.5
        kaz = np.where(ga > gb, A, np.where(gb > ga, B, np.where(ua > ub, A, np.where(ub > ua, B, np.where(pen, A, B)))))
        if kazanan is not None and kazanan in ix:
            kaz = np.full(N, ix[kazanan])
        not_ = '' if not esit[0] else ('uzt.' if ua[0] != ub[0] else 'pen.')
        ornek.append((tur, int(A[0]), int(B[0]), int(ga[0] + (ua[0] if esit[0] else 0)), int(gb[0] + (ub[0] if esit[0] else 0)),
                      int(kaz[0]), not_))
        return kaz

    def kaydet(tur_no, A, B):
        np.add.at(rakip[tur_no], (A, B), 1)
        np.add.at(rakip[tur_no], (B, A), 1)
        np.add.at(ulasti[tur_no], A, 1)
        np.add.at(ulasti[tur_no], B, 1)

    def sabit(t):
        return np.full(N, ix[t])

    def ev_sirasi(X, Y):
        """İkinci maçı lig aşamasında üstte bitiren oynar: (ilk maçın ev sahibi, ikincinin)."""
        ust = yer[tum, X] < yer[tum, Y]
        return np.where(ust, Y, X), np.where(ust, X, Y)

    # play-off ve son 16'nın seri başları
    yarisi = [[None] * 8 for _ in range(3)]  # [seri başı, play-off ikinci maç ev sahibi, ilk maç ev sahibi] × sıra
    for g, (ust, orta, alt) in enumerate(AGAC):
        for c, cift in enumerate((ust, orta, alt)):
            yazi = rng.random(N) < 0.5  # çiftin hangi takımı ağacın hangi yarısına
            t1, t2 = sira[tum, cift[0] - 1], sira[tum, cift[1] - 1]
            yarisi[c][g], yarisi[c][g + 4] = np.where(yazi, t1, t2), np.where(yazi, t2, t1)

    # play-off
    if 'playoff' in bilinen:
        po = [(sabit(ev), sabit(dep), ayak, kaz) for _, ev, dep, kaz, ayak in bilinen['playoff']]
    else:
        po = [(yarisi[2][k], yarisi[1][k], None, None) for k in range(8)]
    po_kaz = []
    for A, B, ayak, kaz in po:
        kaydet(0, A, B)
        po_kaz.append(iki_mac(A, B, ayak, kaz, tur='playoff'))

    # son 16
    if '1/8' in bilinen:
        tur = [(sabit(ev), sabit(dep), ayak, kaz) for _, ev, dep, kaz, ayak in bilinen['1/8']]
    else:
        ust_k = []
        if 'playoff' in bilinen:  # play-off kurası belli: galibin rakibi, play-off'taki seri başının grubundaki çiftten
            for k, (A, B, _, _) in enumerate(po):
                sb = int(yer[0, B[0]]) + 1  # play-off'ta ikinci maçı evinde oynayan (9-16)
                ust_k.append(next((g for g, (_, orta, _) in enumerate(AGAC) if sb in orta), None))
        if ust_k and None not in ust_k:  # seri başı 9-16 dışında çıkarsa (veri tutarsız) ağacın kendi eşleşmeleri
            secilen = {}
            for k, g in enumerate(ust_k):  # aynı gruptan iki eşleşme: çiftin iki takımı kurayla paylaşılır
                secilen.setdefault(g, []).append(k)
            ust = [None] * 8
            for g, ks in secilen.items():
                yazi = rng.random(N) < 0.5
                t1, t2 = sira[tum, AGAC[g][0][0] - 1], sira[tum, AGAC[g][0][1] - 1]
                ust[ks[0]] = np.where(yazi, t1, t2)
                if len(ks) > 1:
                    ust[ks[1]] = np.where(yazi, t2, t1)
        else:
            ust = yarisi[0]
        tur = [(po_kaz[k], ust[k], None, None) for k in range(8)]
    onceki = []
    for A, B, ayak, kaz in tur:
        kaydet(1, A, B)
        onceki.append(iki_mac(A, B, ayak, kaz, tur='1/8'))

    # çeyrek final, yarı final, final: belli olan tur gerçek eşleşmelerle, değilse ağaçta yan yana olanlar
    for tur_no, ad in ((2, '1/4'), (3, '1/2'), (4, 'final')):
        final = ad == 'final'
        if ad in bilinen:
            eslesme = [(sabit(ev), sabit(dep), ayak, kaz) for _, ev, dep, kaz, ayak in bilinen[ad]]
        else:
            eslesme = []
            for k in range(0, len(onceki), 2):
                A, B = (onceki[k], onceki[k + 1]) if final else ev_sirasi(onceki[k], onceki[k + 1])
                eslesme.append((A, B, None, None))
        sonraki = []
        for A, B, ayak, kaz in eslesme:
            kaydet(tur_no, A, B)
            sonraki.append(iki_mac(A, B, ayak, kaz, tarafsiz=final, tur=ad))
        onceki = sonraki
    np.add.at(ulasti[5], onceki[0], 1)

    # ---- özet
    sira_say = np.zeros((n, n))  # [takım, sıra]
    np.add.at(sira_say, (sira, np.tile(np.arange(n), (N, 1))), 1)
    finaller = {}
    A_f, B_f = None, None
    sonuc = []
    for t in range(n):
        sonuc.append({
            'id': takimlar[t], 'ad': E.ad.get(takimlar[t], tablo[t][1]), 'elo': float(R[t]),
            'puan': float(pts[:, t].mean()), 'sira': float(yer[:, t].mean() + 1),
            'ilk8': float(sira_say[t, :8].sum() / N), 'playoff': float(sira_say[t, 8:24].sum() / N),
            'elendi': float(sira_say[t, 24:].sum() / N),
            'turlar': [float(x / N) for x in ulasti[1:, t]],  # son 16, çeyrek, yarı, final, şampiyon
        })
    for t in range(n):
        for u in range(t + 1, n):
            c = rakip[4, t, u]
            if c:
                finaller[(takimlar[t], takimlar[u])] = float(c / N)
    return {
        'takimlar': sonuc, 'N': N, 'kalan_mac': len(kalan),
        'rakip': {tur: rakip[i] / N for i, tur in enumerate(ELEME_TURLARI)}, 'sira_ix': ix,
        'finaller': sorted(finaller.items(), key=lambda x: -x[1])[:10],
        'ornek': [(tur, takimlar[a], takimlar[b], ga, gb, takimlar[k], not_) for tur, a, b, ga, gb, k, not_ in ornek],
        'ornek_sira': [takimlar[t] for t in sira[0]],
    }
