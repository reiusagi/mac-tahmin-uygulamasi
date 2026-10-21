"""Takım sayfası verisi (FotMob takım sayfası): bütün maçlar (lig, Avrupa kupaları, yerel kupa, hazırlık), güncel kadro
ve sakatlar, son maçın ilk 11'i; uygulamanın lig verisinden de "en çok oynayan 11" (dakikalara göre, takımın dizilişine
yerleştirilir). FotMob yanıtı bir saat önbellekte tutulur."""
import difflib
import json
import logging
import time
from pathlib import Path

from .avrupa import ELEMELER, KUPA, KUPALAR
from .milli import TURNUVA
from .sezon import FOTMOB_ID, LIG_ADI as LIG_ANAHTAR_ADI, sadelestir
from .ulkeler import turkce
from .veri import fotmob_url, json_getir, kimlik

logger = logging.getLogger(__name__)

MILLI_ADI = {k: t[1] for k, t in TURNUVA.items()}

ONBELLEK_SN = 3600
AVRUPA = {kid for kid, _ in KUPALAR + ELEMELER}
AVRUPA_ADI = {**KUPA, **dict(ELEMELER)}
HAZIRLIK = {489}  # FotMob "Club Friendlies"
LIG_ADI = {FOTMOB_ID[k]: ad for k, ad in LIG_ANAHTAR_ADI.items() if k in FOTMOB_ID}
KATEGORI = [('lig', 'Lig'), ('avrupa', 'Avrupa'), ('kupa', 'Kupa'), ('hazirlik', 'Hazırlık')]


def _getir(tid, ham):
    tid = kimlik(tid)  # dosya adına ve adrese girer
    yol = Path(ham) / 'takim' / f'{tid}.json'
    if yol.exists() and time.time() - yol.stat().st_mtime < ONBELLEK_SN:
        return json.loads(yol.read_text(encoding='utf-8'))
    j = json_getir(fotmob_url('teams', id=tid))
    # yalnızca takim_sayfasi'nın okuduğu bölümler saklanır (tam yanıt ~0,5 MB; istatistik tabloları, haberler… gereksiz)
    ozet = j.get('overview') or {}
    j = {'details': j.get('details') or {}, 'fixtures': {'allFixtures': {'fixtures':
         ((j.get('fixtures') or {}).get('allFixtures') or {}).get('fixtures') or []}},
         'squad': {'squad': (j.get('squad') or {}).get('squad') or []},
         'overview': {k: ozet.get(k) for k in ('topPlayers', 'lastLineupStats', 'lastMatch')}}
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(j, ensure_ascii=False), encoding='utf-8')
    return j


def _mac(f, tid, ana_lig):
    st = f.get('status') or {}
    lid = (f.get('tournament') or {}).get('leagueId')
    ad = (f.get('tournament') or {}).get('name') or ''
    kat = 'lig' if lid == ana_lig else 'avrupa' if lid in AVRUPA else 'hazirlik' if lid in HAZIRLIK or 'riendl' in ad else 'kupa'
    skor = None
    if st.get('finished') and st.get('scoreStr'):
        try:
            skor = tuple(int(x) for x in st['scoreStr'].replace(' ', '').split('-')[:2])
        except ValueError:
            pass
    ev, dep = f.get('home') or {}, f.get('away') or {}
    sonuc = None
    if skor:
        biz, onlar = (skor[0], skor[1]) if ev.get('id') == tid else (skor[1], skor[0])
        pen = (st.get('reason') or {}).get('shortKey') == 'penalties_short'
        sonuc = 'B' if biz == onlar else 'G' if biz > onlar else 'M'
        if pen and f.get('result') in (1, -1):  # penaltılarla: FotMob'un sonucu (tur atlama) değil, maç skoru esas
            sonuc = 'B'
    return {'id': f.get('id'), 'zaman': st.get('utcTime') or '', 'turnuva_id': lid,
            'turnuva': AVRUPA_ADI.get(lid) or LIG_ADI.get(lid) or ('Hazırlık maçı' if kat == 'hazirlik' else ad),
            'kategori': kat, 'ev': ev.get('name') or '', 'dep': dep.get('name') or '', 'evId': ev.get('id'), 'depId': dep.get('id'),
            'skor': skor, 'sonuc': sonuc, 'bitti': bool(st.get('finished')),
            'canli': bool(st.get('started')) and not st.get('finished') and not st.get('cancelled'),
            'iptal': bool(st.get('cancelled')), 'pen': (st.get('reason') or {}).get('shortKey') == 'penalties_short'}


def onbellekteki_uyruklar(tid, ham):
    """Önbellekteki takım sayfasından (ağ isteği yok): (takımın ülke kodu, {oyuncu FotMob id (metin): (ülke kodu, ülke
    adı)}). Sayfa önbellekte yoksa (None, {})."""
    try:
        tid = kimlik(tid)
    except ValueError:
        return None, {}
    yol = Path(ham) / 'takim' / f'{tid}.json'
    if not yol.exists():
        return None, {}
    try:
        j = json.loads(yol.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None, {}
    return ((j.get('details') or {}).get('country'),
            {str(m['id']): (m.get('ccode'), m.get('cname')) for g in (j.get('squad') or {}).get('squad') or []
             for m in g.get('members') or [] if m.get('id') is not None and g.get('title') != 'coach'})


def takim_sayfasi(tid, ham):
    """Sadeleştirilmiş takım sayfası."""
    j = _getir(tid, ham)
    d = j.get('details') or {}
    ana = d.get('primaryLeagueId')
    maclar = sorted((_mac(f, tid, ana) for f in ((j.get('fixtures') or {}).get('allFixtures') or {}).get('fixtures') or []),
                    key=lambda m: m['zaman'])
    kadro, teknik = [], ''
    for g in (j.get('squad') or {}).get('squad') or []:
        if g.get('title') == 'coach':
            teknik = ((g.get('members') or [{}])[0]).get('name', '')
            continue
        for m in g.get('members') or []:
            kadro.append({'id': m.get('id'), 'ad': m.get('name', ''), 'no': m.get('shirtNumber'), 'grup': g.get('title'),
                          'mevki': m.get('positionIdsDesc') or '', 'yas': m.get('age'), 'gol': m.get('goals'),
                          'asist': m.get('assists'), 'puan': m.get('rating'), 'deger': m.get('transferValue'),
                          'sakat': (m.get('injury') or {}).get('expectedReturn') if m.get('injury') else None})
    # FotMob'un takım için ligdeki en iyileri (uygulamanın ligi olmayan takımlarda kullanılır): [(ad, FotMob id, değer)]
    tp = (j.get('overview') or {}).get('topPlayers') or {}
    en_iyiler = {ad: [(p.get('name', ''), p.get('id'), p.get('value')) for p in (tp.get(k) or {}).get('players') or []][:3]
                 for ad, k in (('gol', 'byGoals'), ('asist', 'byAssists'), ('puan', 'byRating'))}
    son = (j.get('overview') or {}).get('lastLineupStats') or {}
    son_mac = (j.get('overview') or {}).get('lastMatch') or {}
    return {'id': tid, 'ad': d.get('name', ''), 'ulke': d.get('country'), 'lig_id': ana, 'lig': d.get('primaryLeagueName', ''),
            'teknik': teknik, 'maclar': maclar, 'kadro': kadro, 'en_iyiler': en_iyiler,
            'son_ilk11': {'dizilis': son.get('formation') or '',
                          'rakip': (son_mac.get('opponent') or {}).get('name', ''), 'zaman': (son_mac.get('status') or {}).get('utcTime', ''),
                          'oyuncular': [{'ad': p.get('name', ''), 'no': p.get('shirtNumber') or '', 'id': p.get('id'),
                                         'x': (p.get('verticalLayout') or {}).get('x'), 'y': (p.get('verticalLayout') or {}).get('y')}
                                        for p in son.get('starters') or []]} if son.get('starters') else None}


OYUNCU_ONBELLEK_SN = 6 * 3600


def _oyuncu_sayfasi(fm_id, ham):
    """FotMob oyuncu sayfasının kullanılan kısımları (son maçlar, kariyer, sözleşme bitişi); altı saat önbellekte."""
    fm_id = kimlik(fm_id)
    yol = Path(ham) / 'oyuncu' / f'{fm_id}.json'
    if yol.exists() and time.time() - yol.stat().st_mtime < OYUNCU_ONBELLEK_SN:
        j = json.loads(yol.read_text(encoding='utf-8'))
        if 'careerHistory' in j and 'contractEnd' in j and 'degerler' in j:
            return j
    j = json_getir(fotmob_url('playerData', id=fm_id))
    sutlar = ((j.get('firstSeasonStats') or {}).get('shotmap')) or []
    j = {'recentMatches': j.get('recentMatches') or [], 'careerHistory': j.get('careerHistory') or {},
         'contractEnd': ((j.get('contractEnd') or {}).get('utcTime') or '')[:10] or None,
         # piyasa değeri geçmişi (FotMob; aylık): [tarih, €, takım]
         'degerler': [[(v.get('date') or '')[:10], v.get('value'), v.get('teamName') or '']
                      for v in (j.get('marketValues') or {}).get('values') or [] if v.get('value')],
         # bu sezonki şutlar (FotMob şut haritası): x 0-105 (rakip kale 105'te), y 0-68
         'sutlar': [{'x': s.get('x'), 'y': s.get('y'), 'xg': s.get('expectedGoals'), 'sonuc': s.get('eventType'),
                     'durum': s.get('situation'), 'dk': s.get('min'), 'kk': bool(s.get('isOwnGoal')),
                     'rakip': s.get('awayTeamName') if s.get('teamId') == s.get('homeTeamId') else s.get('homeTeamName')}
                    for s in sutlar if s.get('x') is not None and s.get('y') is not None]}
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(j, ensure_ascii=False), encoding='utf-8')
    return j


def deger_ve_sutlar(fm_id, ham):
    """Oyuncunun piyasa değeri geçmişi [[tarih, €, takım]] ve bu sezonki şutları [{'x', 'y', 'xg', 'sonuc', 'durum',
    'dk', 'rakip'}] (FotMob oyuncu sayfası; altı saat önbellekte)."""
    j = _oyuncu_sayfasi(fm_id, ham)
    return j.get('degerler') or [], j.get('sutlar') or []


def sozlesme_bitisi(fm_id, ham):
    """Oyuncunun kulübüyle sözleşmesinin bittiği tarih ('YYYY-AA-GG') ya da None (FotMob oyuncu sayfası)."""
    return _oyuncu_sayfasi(fm_id, ham).get('contractEnd')


def _sayi(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def _puan(r):
    try:
        return float((r or {}).get('rating') or 0) or None
    except ValueError:
        return None


def turnuva_adi(lid, ad=''):
    return AVRUPA_ADI.get(lid) or LIG_ADI.get(lid) or MILLI_ADI.get(lid) or ad


def oyuncu_kariyeri(fm_id, ham):
    """Sezon sezon, takım takım bütün kulvarlar (FotMob kariyer bilgisi; uygulamada olmayan ligler dahil):
    [{'grup': 'Kulüp'|'Milli takım', 'sezon', 'takim', 'takim_id', 'mac', 'gol', 'asist', 'puan', 'kiralik',
      'turnuvalar': [{'ad', 'id', 'mac', 'gol', 'asist', 'puan', 'hazirlik'}]}], yeniden eskiye."""
    j = _oyuncu_sayfasi(fm_id, ham)
    ogeler = (j.get('careerHistory') or {}).get('careerItems') or {}
    out = []
    for anahtar, grup in (('senior', 'Kulüp'), ('national team', 'Milli takım')):
        for s in (ogeler.get(anahtar) or {}).get('seasonEntries') or []:
            out.append({'grup': grup, 'sezon': s.get('seasonName', ''), 'takim': turkce(s.get('team', '')), 'takim_id': s.get('teamId'),
                        'mac': _sayi(s.get('appearances')), 'gol': _sayi(s.get('goals')), 'asist': _sayi(s.get('assists')),
                        'puan': _puan(s.get('rating')),
                        'kiralik': ((s.get('transferType') or {}).get('localizationKey') == 'on_loan'),
                        'turnuvalar': [{'ad': turnuva_adi(t.get('leagueId'), t.get('leagueName', '')), 'id': t.get('leagueId'),
                                        'mac': _sayi(t.get('appearances')), 'gol': _sayi(t.get('goals')),
                                        'asist': _sayi(t.get('assists')), 'puan': _puan(t.get('rating')),
                                        'hazirlik': bool(t.get('isFriendly'))} for t in s.get('tournamentStats') or []]})
    return out


def oyuncu_son_maclar(fm_id, ham):
    """FotMob oyuncu sayfasındaki son maçları (eskiden yeniye; bütün kulvarlar ve milli takım): tarih, takım, rakip,
    turnuva, skor, dakika, gol, asist, kart, puan. Altı saat önbellekte."""
    j = _oyuncu_sayfasi(fm_id, ham)
    out = []
    for m in j.get('recentMatches') or []:
        if not m.get('playedInMatch') and not m.get('minutesPlayed'):
            continue
        try:
            puan = float((m.get('ratingProps') or {}).get('rating') or 0) or None
        except ValueError:
            puan = None
        ev = m.get('isHomeTeam')
        lid = m.get('leagueId')
        out.append({'id': m.get('id'), 'zaman': (m.get('matchDate') or {}).get('utcTime') or '',
                    'takim': turkce(m.get('teamName', '')), 'rakip': turkce(m.get('opponentTeamName', '')), 'ev': ev,
                    'turnuva_id': lid, 'turnuva': turnuva_adi(lid, m.get('leagueName', '')),
                    'skor': (m.get('homeScore'), m.get('awayScore')), 'dk': m.get('minutesPlayed') or 0,
                    'gol': m.get('goals') or 0, 'asist': m.get('assists') or 0, 'sari': m.get('yellowCards') or 0,
                    'kirmizi': m.get('redCards') or 0, 'puan': puan, 'yedek': bool(m.get('onBench'))})
    return sorted(out, key=lambda m: m['zaman'])


# ---------------------------------------------------------------- en çok oynayan 11

AILE = {'GK': 'G', 'CB': 'D', 'RB': 'D', 'LB': 'D', 'DM': 'M', 'CM': 'M', 'AM': 'M', 'RW': 'W', 'LW': 'W', 'ST': 'F'}
YEDEK = {'GK': ['GK'], 'RB': ['RB', 'LB', 'CB'], 'LB': ['LB', 'RB', 'CB'], 'CB': ['CB', 'RB', 'LB', 'DM'],
         'DM': ['DM', 'CM', 'CB', 'AM'], 'CM': ['CM', 'DM', 'AM'], 'AM': ['AM', 'CM', 'RW', 'LW', 'ST'],
         'RW': ['RW', 'LW', 'AM', 'ST'], 'LW': ['LW', 'RW', 'AM', 'ST'], 'ST': ['ST', 'AM', 'RW', 'LW']}
VARSAYILAN_MEVKI = {'G': 'GK', 'D': 'CB', 'M': 'CM', 'W': 'RW', 'F': 'ST'}


def _hatlar(dizilis):
    """'4-2-3-1' → hat hat mevkiler (soldan sağa değil, takımın sağından soluna): [[RB, CB, CB, LB], [DM, DM], …]."""
    try:
        sayilar = [int(x) for x in dizilis.split('-') if x]
    except ValueError:
        sayilar = []
    if len(sayilar) < 2 or sum(sayilar) != 10:
        sayilar = [4, 2, 3, 1]
    savunma = {3: ['CB'] * 3, 4: ['RB', 'CB', 'CB', 'LB'], 5: ['RB', 'CB', 'CB', 'CB', 'LB']}.get(sayilar[0], ['CB'] * sayilar[0])
    hucum = {1: ['ST'], 2: ['ST', 'ST'], 3: ['RW', 'ST', 'LW']}.get(sayilar[-1], ['ST'] * sayilar[-1])
    orta = sayilar[1:-1]
    hatlar = []
    for k, n in enumerate(orta):
        ileri = k == len(orta) - 1 and len(orta) > 1
        geri = k == 0 and len(orta) > 1
        if n == 1:
            hat = ['AM' if ileri else 'DM']
        elif n == 2:
            hat = ['AM', 'AM'] if ileri else ['DM', 'DM'] if geri else ['CM', 'CM']
        elif n == 3:
            hat = ['RW', 'AM', 'LW'] if ileri else ['CM', 'DM', 'CM']
        elif n == 4:
            hat = ['RW', 'CM', 'CM', 'LW']
        else:
            hat = ['RW'] + ['CM'] * (n - 2) + ['LW']
        hatlar.append(hat)
    return [['GK'], savunma, *hatlar, hucum]


VARSAYILAN_PUAN = 6.6  # FotMob puanı olmayan oyuncu (puan listesine girecek kadar oynamamış) için


def guc_puani(p, mac_sayisi):
    """İlk 11 seçiminde oyuncunun değeri: bu sezonki FotMob puanı × √(oynadığı dakikanın takımın toplam dakikasına oranı).
    Hem iyi oynayan hem düzenli oynayan öne çıkar; az süre almış ama puanı çok yüksek oyuncu (ör. sakatlıktan dönen)
    düzenli oynayan ama düşük puanlı birinin önüne geçebilir."""
    pay = min(1.0, p['min'] / (90 * mac_sayisi)) if mac_sayisi else 0
    puan = (p.get('ex') or {}).get('rt') or VARSAYILAN_PUAN
    return puan * pay ** 0.5


def _uyum(oyuncu_mevki, yer):
    """Oyuncunun mevkisi bu yere ne kadar uyar: aynı mevki 1, yakın mevkiler 0,85 / 0,7, diğer saha mevkileri 0,5."""
    if (oyuncu_mevki == 'GK') != (yer == 'GK'):
        return 0
    sira = YEDEK[yer].index(oyuncu_mevki) if oyuncu_mevki in YEDEK[yer] else None
    return (1.0, 0.85, 0.7, 0.7, 0.7)[sira] if sira is not None else 0.5


def dizilise_yerlestir(adaylar, dizilis):
    """Genel ilk 11 kurucu. adaylar: [{'anahtar' (tekil), 'mevki' (GK/CB/RB/…/ST), 'deger' (büyük iyi), …}].
    Bütün aday-yer eşleşmeleri (değer × mevki uyumu) büyükten küçüğe yerleştirilir; her yer ve aday bir kez.
    Döner: adayın kopyası + 'yer' (dizilişteki mevki), 'x' (takımın sağından), 'y' (kendi kalesinden)."""
    hatlar = _hatlar(dizilis)
    yuva = [(h, k, m) for h, hat in enumerate(hatlar) for k, m in enumerate(hat)]
    eslesme = sorted(((a['deger'] * _uyum(a['mevki'], y[2]), i, y, a) for i, a in enumerate(adaylar) for y in yuva
                      if _uyum(a['mevki'], y[2]) > 0), key=lambda x: (-x[0], x[1]))
    secilen, kullanilan = {}, set()
    for _, _, y, a in eslesme:
        if y not in secilen and a['anahtar'] not in kullanilan:
            secilen[y] = a
            kullanilan.add(a['anahtar'])
    return [{**a, 'yer': m, 'x': (k + 1) / (len(hatlar[h]) + 1),
             'y': 0.1 if h == 0 else 0.3 + (h - 1) * (0.57 / max(1, len(hatlar) - 2))} for (h, k, m), a in secilen.items()]


def ilk11_adaylari(S, uygulama_adi, kadro):
    """İlk 11 adayları: takımda bu sezon oynamış, ayrılmamış, güncel kadroda olan (adlar eşleşiyorsa) ve sakat olmayan
    oyuncular. kadro: takim_sayfasi()['kadro']. Döner: (adaylar, sakat oldukları için dışarıdakilerin adları, takımın bu
    sezonki maç sayısı). Şüphelilerde p['_supheli'] = True (sahada ✚ ile işaretlenir)."""
    takimdakiler = [p for p in S.PLY if uygulama_adi in p['t'].split(' / ')]
    oyuncular = [p for p in takimdakiler if not p.get('ayrildi') and p['min'] > 0]
    kayit = {p['n']: kadrodaki(p['n'], kadro, p.get('fm_id')) for p in oyuncular}
    if kadro and sum(1 for k in kayit.values() if k) >= 11:  # adlar eşleşiyorsa güncel kadroya göre süz
        oyuncular = [p for p in oyuncular if kayit[p['n']]]
    sakat = [p['n'] for p in oyuncular if kayit.get(p['n']) and kayit[p['n']]['sakat'] and kayit[p['n']]['sakat'] != 'Doubtful']
    oyuncular = [p for p in oyuncular if p['n'] not in sakat]
    for p in oyuncular:
        p['_supheli'] = bool(kayit.get(p['n']) and kayit[p['n']]['sakat'] == 'Doubtful')
    mac = next((r['O'] for r in S.tb if r['name'] == uygulama_adi), 0)
    return oyuncular, sakat, mac


def en_cok_oynayan(oyuncular, dizilis, mac_sayisi):
    """oyuncular: bu sezon oynamış, şu an oynayabilecek (sakat ya da ayrılmış olmayan) oyuncular (sezon.Sezon.PLY
    biçiminde). Dizilişin her yerine o mevkideki en yüksek güç puanlı (guc_puani) oyuncu konur.
    Döner: [{'ad', 'no', 'x', 'y', 'mevki', 'dk', 'idx', 'puan'}]."""
    adaylar = [{'anahtar': p['n'], 'deger': guc_puani(p, mac_sayisi), 'p': p,
                'mevki': p.get('detay') if p.get('detay') in AILE and AILE[p['detay']] == p['pos'] else VARSAYILAN_MEVKI.get(p['pos'])}
               for p in oyuncular if p['min'] > 0]
    return [{'ad': a['p']['n'], 'no': '', 'mevki': a['yer'], 'dk': a['p']['min'], 'idx': a['p']['idx'],
             'puan': (a['p'].get('ex') or {}).get('rt'), 'x': a['x'], 'y': a['y']}
            for a in dizilise_yerlestir(adaylar, dizilis)]


def _ayni(a, b):
    """İki sadeleştirilmiş ad aynı kişi mi (ad yazımları kaynaklar arasında az farklı olabilir)?"""
    if a == b or (a.split()[-1:] == b.split()[-1:] and difflib.SequenceMatcher(None, a, b).ratio() > 0.6):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() > 0.85


def ayni_kisi(ad, kadro_adlari):
    """Uygulamadaki oyuncu adı FotMob kadrosunda var mı? kadro_adlari: sadeleştirilmiş adlar."""
    a = sadelestir(ad)
    return any(_ayni(a, b) for b in kadro_adlari)


def kadrodaki(ad, kadro, fm_id=None):
    """Uygulamadaki oyuncunun FotMob kadrosundaki kaydı (takim_sayfasi()['kadro'] öğesi) ya da None. FotMob id'si
    biliniyorsa önce onunla, yoksa adla (yazım farklarına toleranslı) aranır."""
    if fm_id is not None:
        k = next((k for k in kadro if str(k['id']) == str(fm_id)), None)
        if k:
            return k
    a = sadelestir(ad)
    tam = next((k for k in kadro if sadelestir(k['ad']) == a), None)
    return tam or next((k for k in kadro if _ayni(a, sadelestir(k['ad']))), None)


AY = {'January': 'Ocak', 'February': 'Şubat', 'March': 'Mart', 'April': 'Nisan', 'May': 'Mayıs', 'June': 'Haziran',
      'July': 'Temmuz', 'August': 'Ağustos', 'September': 'Eylül', 'October': 'Ekim', 'November': 'Kasım', 'December': 'Aralık'}


def donus_metni(s):
    """FotMob'un tahmini dönüş yazısı → Türkçe: 'Mid December 2026' → 'Aralık 2026 ortası', 'Doubtful' → 'şüpheli'."""
    if not s:
        return ''
    if s == 'Doubtful':
        return 'şüpheli'
    parca = s.split()
    if len(parca) == 3 and parca[1] in AY:
        return f'{AY[parca[1]]} {parca[2]} {({"Early": "başı", "Mid": "ortası", "Late": "sonu"}).get(parca[0], "")}'.strip()
    if len(parca) == 2 and parca[0] in AY:
        return f'{AY[parca[0]]} {parca[1]}'
    return {'Unknown': 'belli değil', 'Out for season': 'sezon sonuna kadar yok'}.get(s, s)
