"""Canlı skorlar: FotMob'un günlük maç listesinden uygulamadaki liglerin ve milli turnuvaların maçları.
İsteğe bağlı olarak maç detayından hakem ve maçın stadyumu eklenir (hakem.py)."""
import logging
import re
from datetime import datetime, timedelta, timezone

from .avrupa import KUPALAR, YEREL_KUPALAR, tur_adi
from .milli import TURNUVALAR, grup_adi
from .ulkeler import turkce
from .sezon import FOTMOB_ID, LIG_ADI, LIGLER
from .veri import fotmob_url, json_getir

logger = logging.getLogger(__name__)

# FotMob lig kimliği -> uygulamadaki lig anahtarı
FOTMOB_LIGLER = {v: k for k, v in FOTMOB_ID.items()}
# milli turnuvalar 'milli-<FotMob kimliği>' anahtarıyla, liglerden sonra
MILLI = {tid: (f'milli-{tid}', ad) for tid, ad, *_ in TURNUVALAR}
# Avrupa kupaları 'avrupa-<FotMob kimliği>' anahtarıyla; sırada liglerin önünde
AVRUPA = {kid: (f'avrupa-{kid}', ad) for kid, ad in KUPALAR}
# yerel kupalar 'kupa-<FotMob kimliği>' anahtarıyla, liglerden sonra
YEREL = {kid: (f'kupa-{kid}', ad) for kid, ad in YEREL_KUPALAR}
SIRA = {**{k: -10 + i for i, (k, _) in enumerate(AVRUPA.values())}, **{l[0]: i for i, l in enumerate(LIGLER)},
        **{k: 50 + i for i, (k, _) in enumerate(YEREL.values())}, **{k: 100 + i for i, (k, _) in enumerate(MILLI.values())}}


def _grup(tid, ad):
    """FotMob'un 'UEFA Nations League A Grp. 2' gibi adından grup: 'A Ligi · 2. Grup' (yoksa '')."""
    if 'Grp.' not in ad:
        return ''
    lig = re.search(r'League ([A-D])\b', ad)
    return grup_adi(tid, ad.split('Grp.')[-1], lig.group(1) if lig else None)


def _dakika(st):
    """FotMob'un "87’" gibi dakika yazısını sadeleştirir; devre arası gibi durumları olduğu gibi bırakır."""
    kisa = re.sub(r'[‎‏’\']', '', (st.get('liveTime') or {}).get('short', '')).strip()
    if re.fullmatch(r'\d+(\+\d+)?', kisa):
        return kisa + "'"
    return kisa or (st.get('reason') or {}).get('short') or 'Canlı'


def gunun_maclari(tarih, saat_dilimi='Europe/Istanbul', stadyumlar=None, ham=None):
    """Bir günün maçları. ham (önbellek klasörü) verilirse her maça hakem ve maçın stadyumu eklenir;
    stadyum bilinmiyorsa ev sahibinin iç sahası (stadyumlar) kullanılır."""
    from .hakem import mac_detay
    fm = (stadyumlar or {}).get('fotmob') or {}
    j = json_getir(fotmob_url('matches', date=tarih, timezone=saat_dilimi))
    maclar = []
    for lig in j.get('leagues', []):
        anahtar = FOTMOB_LIGLER.get(lig.get('primaryId'))
        if anahtar:
            baslik, grup = LIG_ADI[anahtar], ''
        elif lig.get('primaryId') in AVRUPA or lig.get('primaryId') in YEREL:
            anahtar, baslik = AVRUPA.get(lig['primaryId']) or YEREL[lig['primaryId']]
            grup = None  # maç maç: hangi tur (lig aşaması haftası, son 16…)
        elif lig.get('primaryId') in MILLI:
            anahtar, baslik = MILLI[lig['primaryId']]
            grup = _grup(lig['primaryId'], lig.get('name') or '')
            for m in lig.get('matches', []):  # milli takım adları Türkçe
                m['home']['name'], m['away']['name'] = turkce(m['home']['name']), turkce(m['away']['name'])
        else:
            continue
        for m in lig.get('matches', []):
            st = m.get('status') or {}
            if st.get('cancelled'):
                durum = 'iptal'
            elif st.get('finished'):
                durum = 'bitti'
            elif st.get('started'):
                durum = 'canli'
            else:
                durum = 'baslamadi'
            oynandi = durum in ('canli', 'bitti')
            try:  # FotMob'un "time" alanı saat dilimini her zaman uygulamıyor; UTC başlangıçtan yerel saate çevir
                saat = datetime.fromisoformat(st['utcTime'].replace('Z', '+00:00')).astimezone().strftime('%H:%M')
            except (KeyError, ValueError, AttributeError):
                saat = (m.get('time') or '')[-5:]
            ev_std = fm.get(str(m['home'].get('id'))) or {}
            detay = mac_detay(m['id'], ham) if ham and m.get('id') else {}
            std = detay.get('stadyum') or ev_std
            maclar.append({
                'id': m.get('id'), 'lig': anahtar, 'baslik': baslik, 'saat': saat,
                'grup': grup if grup is not None else (tur_adi(m['tournamentStage'], anahtar.startswith('kupa-'))
                                                       if m.get('tournamentStage') else ''),
                'ev': m['home']['name'], 'dep': m['away']['name'],
                'evId': m['home'].get('id'), 'depId': m['away'].get('id'),
                'evGol': m['home'].get('score') if oynandi else None,
                'depGol': m['away'].get('score') if oynandi else None,
                'durum': durum, 'dakika': _dakika(st) if durum == 'canli' else None,
                'baslangic': st.get('utcTime'),
                'stadyum': std.get('ad'), 'sehir': std.get('sehir'),
                # eski önbellekteki maç detayında konum yok: stadyum ev sahibininkiyse onun konumu
                'konum': std.get('konum') or (ev_std.get('konum') if std.get('ad') == ev_std.get('ad') else None),
                'hakem': detay.get('hakem'),
            })
    maclar.sort(key=lambda x: (SIRA[x['lig']], x['baslangic'] or '', x['ev']))
    return maclar


def canli_skorlar(tarih=None, saat_dilimi='Europe/Istanbul', stadyumlar=None, ham=None, yakin_gun=0):
    """Bugünün (ya da verilen günün) maçları; yakin_gun > 0 ise sonraki günlerin henüz başlamamış
    maçları da 'yakinda' altında döner (hakemleri atandıkça dolar)."""
    gun = datetime.strptime(tarih, '%Y%m%d') if tarih else datetime.now()
    v = {'tarih': gun.strftime('%Y%m%d'), 'guncellendi': datetime.now(timezone.utc).isoformat(timespec='seconds'),
         'kaynak': 'fotmob.com', 'maclar': gunun_maclari(gun.strftime('%Y%m%d'), saat_dilimi, stadyumlar, ham), 'yakinda': []}
    for i in range(1, yakin_gun + 1):
        try:
            sonraki = gunun_maclari((gun + timedelta(days=i)).strftime('%Y%m%d'), saat_dilimi, stadyumlar, ham)
        except Exception:  # ileri günlerden biri alınamazsa bugünün skorları yine yazılsın
            logger.debug('ileri günün maçları alınamadı: +%d gün', i, exc_info=True)
            continue
        v['yakinda'] += [{k: m[k] for k in ('id', 'lig', 'baslik', 'grup', 'ev', 'dep', 'evId', 'depId', 'baslangic',
                                            'stadyum', 'sehir', 'konum', 'hakem')}
                         for m in sonraki if m['durum'] == 'baslamadi']
    return v
