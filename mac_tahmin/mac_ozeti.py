"""Tek bir maçın ayrıntısı (FotMob maç sayfası): skor ve durum, olaylar (gol, kart, değişiklik), takım istatistikleri ve
ilk 11'ler (maç başlamadıysa FotMob'un tahmini kadrosu). Maç bittiyse sonuç değişmeyeceği için diske kaydedilir; canlı ve
başlamamış maçlar her istendiğinde yeniden alınır (canlı istatistikler, açıklanan kadrolar)."""
import json
import re
import threading
from pathlib import Path

from . import sema
from .ulkeler import turkce
from .veri import fotmob_url, json_getir, kimlik

# FotMob istatistik başlıklarının Türkçesi; listede olmayan başlık olduğu gibi kalır
ISTATISTIK = {
    'Top stats': 'Öne çıkanlar', 'Shots': 'Şutlar', 'Expected goals (xG)': 'Beklenen gol (xG)', 'Passes': 'Paslar',
    'Defence': 'Savunma', 'Duels': 'İkili mücadeleler', 'Discipline': 'Disiplin',
    'Ball possession': 'Topa sahip olma', 'Total shots': 'Toplam şut', 'Shots on target': 'İsabetli şut',
    'Shots off target': 'İsabetsiz şut', 'Blocked shots': 'Engellenen şut', 'Hit woodwork': 'Direkten dönen',
    'Shots inside box': 'Ceza sahası içinden şut', 'Shots outside box': 'Ceza sahası dışından şut',
    'Touches in opposition box': 'Rakip ceza sahasında topla buluşma', 'Big chances': 'Net pozisyon',
    'Big chances missed': 'Kaçan net pozisyon', 'Accurate passes': 'İsabetli pas', 'Yellow cards': 'Sarı kart',
    'Red cards': 'Kırmızı kart', 'Corners': 'Korner', 'xG open play': 'xG (açık oyun)', 'xG set play': 'xG (duran top)',
    'xG non-penalty': 'Penaltısız xG', 'xG on target (xGOT)': 'İsabetli şut xG (xGOT)', 'Own half': 'Kendi yarı sahasında',
    'Opposition half': 'Rakip yarı sahada', 'Accurate long balls': 'İsabetli uzun top', 'Accurate crosses': 'İsabetli orta',
    'Throws': 'Taç', 'Offsides': 'Ofsayt', 'Tackles': 'Top çalma', 'Interceptions': 'Pas arası', 'Blocks': 'Blok',
    'Clearances': 'Uzaklaştırma', 'Keeper saves': 'Kurtarış', 'Duels won': 'Kazanılan ikili mücadele',
    'Ground duels won': 'Kazanılan yerde mücadele', 'Aerial duels won': 'Kazanılan hava topu',
    'Successful dribbles': 'Başarılı çalım', 'Fouls committed': 'Faul', 'Passes ': 'Pas', 'Expected assists (xA)': 'Beklenen asist (xA)',
}


SURUM = 5  # önbellekteki bitmiş maç kaydının biçimi (2: oyuncu olayları, 3: maç istatistikleri, 4: maçtaki mevkileri,
#            5: fiziksel veriler ayrı alanda; 4. sürüm kayıtlar indirmeden yükseltilir: _yukselt)

# fiziksel veriler (FotMob şimdilik yalnızca Premier League'de verir): FotMob adı → (alan, Türkçe ad)
FIZIKSEL = {'Top speed': ('hiz', 'En yüksek hız'), 'Distance covered': ('mesafe', 'Koşu mesafesi'),
            'Running': ('kosu', 'Tempolu koşu mesafesi'), 'Sprinting': ('sprint_m', 'Sprint mesafesi'),
            'Number of sprints': ('sprint', 'Sprint sayısı')}
FIZIKSEL_GRUP = 'Fiziksel (koşu ve sprint)'


def fiziksel_yazi(alan, v):
    """Fiziksel değer → metin: hız km/sa, mesafe km ya da m, sprint sayısı."""
    if v is None:
        return None
    if alan == 'hiz':
        return f'{v:.1f} km/sa'.replace('.', ',')
    if alan == 'sprint':
        return str(int(v))
    return f'{v / 1000:.2f} km'.replace('.', ',') if v >= 1000 else f'{round(v)} m'

# oyuncunun maç istatistikleri (FotMob playerStats): grup ve istatistik adlarının Türkçesi; listede olmayan olduğu gibi kalır
OYUNCU_GRUP = {'Top stats': 'Öne çıkanlar', 'Attack': 'Hücum', 'Defense': 'Savunma', 'Duels': 'İkili mücadeleler'}
OYUNCU_ISTATISTIK = {
    'FotMob rating': 'FotMob puanı', 'Minutes played': 'Oynadığı süre', 'Goals': 'Gol', 'Assists': 'Asist',
    'Expected goals (xG)': 'Beklenen gol (xG)', 'Expected goals on target (xGOT)': 'İsabetli şut xG (xGOT)',
    'Expected assists (xA)': 'Beklenen asist (xA)', 'xG + xA': 'xG + xA', 'xG Non-penalty': 'Penaltısız xG',
    'Total shots': 'Toplam şut', 'Shots on target': 'İsabetli şut', 'Shots off target': 'İsabetsiz şut',
    'Blocked shots': 'Engellenen şut', 'Shot accuracy': 'Şut isabeti', 'Hit woodwork': 'Direkten dönen',
    'Big chances missed': 'Kaçırdığı net pozisyon', 'Big chances created': 'Yarattığı net pozisyon',
    'Chances created': 'Yarattığı şans', 'Touches': 'Topla buluşma', 'Touches in opposition box': 'Rakip ceza sahasında topla buluşma',
    'Accurate passes': 'İsabetli pas', 'Accurate long balls': 'İsabetli uzun top', 'Accurate crosses': 'İsabetli orta',
    'Passes into final third': 'Son üçte bire pas', 'Successful dribbles': 'Başarılı çalım', 'Corners': 'Korner',
    'Dispossessed': 'Top kaybı (rakibe kaptırma)', 'Offsides': 'Ofsayt', 'Penalties won': 'Kazandırdığı penaltı',
    'Missed penalty': 'Kaçırdığı penaltı', 'Was fouled': 'Maruz kaldığı faul', 'Fouls committed': 'Yaptığı faul',
    'Tackles': 'Top çalma', 'Interceptions': 'Pas arası', 'Blocks': 'Blok', 'Clearances': 'Uzaklaştırma',
    'Headed clearance': 'Kafayla uzaklaştırma', 'Recoveries': 'Top kazanma', 'Defensive actions': 'Savunma hareketi',
    'Dribbled past': 'Çalımlandığı', 'Last man tackle': 'Son adam müdahalesi', 'Conceded penalty': 'Yaptırdığı penaltı',
    'Error led to goal': 'Gole yol açan hata', 'Duels won': 'Kazandığı ikili mücadele', 'Duels lost': 'Kaybettiği ikili mücadele',
    'Ground duels won': 'Kazandığı yerde mücadele', 'Aerial duels won': 'Kazandığı hava topu',
    'Saves': 'Kurtarış', 'Goals conceded': 'Yediği gol', 'xGOT faced': 'Karşılaştığı isabetli şut xG',
    'Goals prevented': 'Önlediği gol', 'Diving save': 'Uçarak kurtarış', 'Saves inside box': 'Ceza sahası içinden kurtarış',
    'Acted as sweeper': 'Libero gibi çıkış', 'Punches': 'Yumrukla uzaklaştırma', 'Throws': 'Elle oyun kurma',
    'High claim': 'Havada top alma',
}


def _deger(s):
    """FotMob istatistik değeri → metin: '8/12 (%67)', '0,45', '90''."""
    t, v = s.get('type'), s.get('value')
    if v is None or t == 'boolean':
        return None
    if t == 'fractionWithPercentage':
        top = s.get('total') or 0
        return f'{v}/{top}' + (f' (%{round(v / top * 100)})' if top else '')
    if t == 'double':
        return f'{v:.2f}'.replace('.', ',')
    return str(v)


def _oyuncu_istatistikleri(j):
    """{oyuncu id: {'ad', 'takim_id', 'no', 'kaleci', 'puan', 'dk', 'gruplar': [(grup, [(istatistik, değer)])],
    'sutlar': [{'dk', 'tur', 'sonuc', 'xg', 'xgot'}]}}"""
    out = {}
    for pid, p in ((j.get('content') or {}).get('playerStats') or {}).items():
        gruplar, puan, dk, fiz = [], None, None, {}
        for g in p.get('stats') or []:
            satirlar = []
            fiziksel = g.get('key') == 'physical_metrics'
            for ad, s in (g.get('stats') or {}).items():
                st = s.get('stat') or {}
                if ad == 'FotMob rating':
                    puan = st.get('value')
                if ad == 'Minutes played':
                    dk = st.get('value')
                if fiziksel and ad in FIZIKSEL:
                    alan, tr = FIZIKSEL[ad]
                    fiz[alan] = st.get('value')
                    d = fiziksel_yazi(alan, st.get('value'))
                    if d is not None:
                        satirlar.append((tr, d))
                    continue
                d = _deger(st)
                if d is not None:
                    satirlar.append((OYUNCU_ISTATISTIK.get(ad, ad), d))
            if satirlar:
                gruplar.append((FIZIKSEL_GRUP if fiziksel else OYUNCU_GRUP.get(g.get('title'), g.get('title')), satirlar))
        sutlar = [{'dk': s.get('min'), 'tur': s.get('shotType'), 'sonuc': s.get('eventType'), 'xg': s.get('expectedGoals'),
                   'xgot': s.get('expectedGoalsOnTarget')} for s in p.get('shotmap') or []]
        out[str(pid)] = {'ad': p.get('name', ''), 'takim_id': p.get('teamId'), 'takim': p.get('teamName', ''),
                         'no': p.get('shirtNumber') or '', 'kaleci': bool(p.get('isGoalkeeper')), 'puan': puan, 'dk': dk,
                         # maçtaki mevki (FotMob ızgara kodu, veri.fotmob_detay ile RB/CB/ST…) ve olağan mevki (0 kaleci … 3 forvet)
                         'mevki_kodu': p.get('positionId'), 'olagan': p.get('usualPosition'),
                         'gruplar': gruplar, 'sutlar': sutlar, 'fiziksel': fiz or None}
    return out


def _yukselt(eski):
    """4. sürüm kaydı 5. sürüme çevirir (indirmeden): ham hâliyle saklanmış 'Physical metrics' grubu Türkçe ve
    biçimli olur, sayılar 'fiziksel' alanına geçer."""
    for o in (eski.get('oyuncular') or {}).values():
        fiz, gruplar = {}, []
        for ad, satirlar in o.get('gruplar') or []:
            if ad != 'Physical metrics':
                gruplar.append((ad, satirlar))
                continue
            yeni = []
            for isim, deger in satirlar:
                if isim in FIZIKSEL:
                    alan, tr = FIZIKSEL[isim]
                    try:
                        fiz[alan] = float(deger)
                    except (TypeError, ValueError):
                        continue
                    yeni.append((tr, fiziksel_yazi(alan, fiz[alan])))
            if yeni:
                gruplar.append((FIZIKSEL_GRUP, yeni))
        o['gruplar'], o['fiziksel'] = gruplar, fiz or None
    eski['surum'] = SURUM
    return eski


def _dakika_metni(st):
    """FotMob'un canlı dakika yazısı ("39‎’‎" gibi, görünmez yön karakterleriyle) → "39'"; devre arası gibi durumlar olduğu gibi."""
    kisa = re.sub(r"[‎‏’']", '', (st.get('liveTime') or {}).get('short', '')).strip()
    return kisa + "'" if re.fullmatch(r'\d+(\+\d+)?', kisa) else (kisa or 'Canlı')


def _dakika(e):
    ek = e.get('overloadTime')
    return f"{e.get('time')}'" + (f"+{ek}" if ek else '')


def _olaylar(j):
    out = []
    for e in (((j.get('content') or {}).get('matchFacts') or {}).get('events') or {}).get('events') or []:
        tur, taraf = e.get('type'), ('ev' if e.get('isHome') else 'dep')
        if tur == 'Goal':
            asist = (e.get('assistStr') or '').replace('assist by ', '')
            aciklama = 'kendi kalesine' if e.get('ownGoal') else ('penaltı' if 'enalt' in str(e.get('goalDescription') or '') else '')
            out.append({'tur': 'gol', 'dk': _dakika(e), 'taraf': taraf, 'oyuncu': e.get('nameStr') or '', 'asist': asist,
                        'aciklama': aciklama, 'skor': e.get('newScore')})
        elif tur == 'Card':
            out.append({'tur': 'kirmizi' if e.get('card') in ('Red', 'YellowRed') else 'sari', 'dk': _dakika(e), 'taraf': taraf,
                        'oyuncu': e.get('nameStr') or '', 'aciklama': 'ikinci sarıdan' if e.get('card') == 'YellowRed' else ''})
        elif tur == 'Substitution' and e.get('swap') and len(e['swap']) == 2:
            out.append({'tur': 'degisiklik', 'dk': _dakika(e), 'taraf': taraf, 'giren': e['swap'][0].get('name', ''),
                        'cikan': e['swap'][1].get('name', '')})
        elif tur == 'Half':
            out.append({'tur': 'devre', 'dk': _dakika(e), 'skor': [e.get('homeScore'), e.get('awayScore')]})
    return out


def _istatistikler(j):
    gruplar = []
    for g in ((((j.get('content') or {}).get('stats') or {}).get('Periods') or {}).get('All') or {}).get('stats') or []:
        satirlar = []
        for s in g.get('stats') or []:
            deger = s.get('stats') or []
            if s.get('type') == 'title' or len(deger) != 2 or deger == [None, None]:
                continue
            satirlar.append((ISTATISTIK.get(s.get('title'), s.get('title')), deger[0], deger[1]))
        if satirlar:
            gruplar.append((ISTATISTIK.get(g.get('title'), g.get('title')), satirlar))
    return gruplar


def _olay_sayilari(p):
    """Oyuncunun maçtaki olayları: {'gol': 2, 'asist': 1, 'sari': 1, …} (FotMob kadro verisindeki performans olayları)."""
    adlar = {'goal': 'gol', 'assist': 'asist', 'ownGoal': 'kk', 'yellowCard': 'sari', 'redCard': 'kirmizi',
             'yellowRedCard': 'kirmizi', 'missedPenalty': 'kacan_pen', 'penaltyGoal': 'gol'}
    out = {}
    for o in (p.get('performance') or {}).get('events') or []:
        k = adlar.get(o.get('type'))
        if k:
            out[k] = out.get(k, 0) + 1
    return out


def _takim(t):
    def oyuncu(p):
        konum = p.get('verticalLayout') or {}
        return {'id': p.get('id'), 'ad': p.get('name', ''), 'no': p.get('shirtNumber') or '', 'x': konum.get('x'), 'y': konum.get('y'),
                'puan': (p.get('performance') or {}).get('rating'), 'kaptan': bool(p.get('isCaptain')),
                'olaylar': _olay_sayilari(p)}
    return {'dizilis': t.get('formation') or '', 'teknik': ((t.get('coach') or {}).get('name') or ''),
            'ilk11': [oyuncu(p) for p in t.get('starters') or []], 'yedek': [oyuncu(p) for p in t.get('subs') or []],
            'puan': t.get('rating')}


def _yaz(yol, veri):
    """Önce geçici dosyaya, sonra tek hamlede yerine: arka planda indirilirken arayüz yarım dosya okumasın."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(f'.{threading.get_ident()}.tmp')
    gecici.write_text(json.dumps(veri, ensure_ascii=False), encoding='utf-8')
    gecici.replace(yol)


def ayrinti(mac_id, ham):
    """Maçın sadeleştirilmiş ayrıntısı. Bitmiş maç önbellekten gelir."""
    mac_id = kimlik(mac_id)  # dosya adına ve adrese girer
    yol = Path(ham) / 'mac_tam' / f'{mac_id}.json'
    if yol.exists():
        try:
            eski = json.loads(yol.read_text(encoding='utf-8'))
        except (OSError, ValueError):  # bozuk ya da okunamayan dosya: yeniden indirilir
            eski = {}
        if eski.get('surum') == SURUM:  # eski biçimde kaydedilmişse (oyuncu olayları yok) yeniden alınır
            return eski
        if eski.get('surum') == 4:  # yalnızca fiziksel verinin biçimi değişti: indirmeden yükseltilir
            eski = _yukselt(eski)
            _yaz(yol, eski)
            return eski
    j = json_getir(fotmob_url('matchDetails', matchId=mac_id))
    sema.kontrol('mac', j)
    h = j.get('header') or {}
    st = h.get('status') or {}
    durum = ('iptal' if st.get('cancelled') else 'bitti' if st.get('finished') else 'canli' if st.get('started') else 'baslamadi')
    takimlar = h.get('teams') or [{}, {}]
    lu = (j.get('content') or {}).get('lineup') or {}
    out = {
        'surum': SURUM, 'id': mac_id, 'durum': durum, 'dakika': _dakika_metni(st) if durum == 'canli' else None, 'baslangic': st.get('utcTime'),
        'ev': {'ad': turkce(takimlar[0].get('name', '')), 'id': takimlar[0].get('id'), 'skor': takimlar[0].get('score')},
        'dep': {'ad': turkce(takimlar[1].get('name', '')), 'id': takimlar[1].get('id'), 'skor': takimlar[1].get('score')},
        'olaylar': _olaylar(j), 'istatistik': _istatistikler(j), 'oyuncular': _oyuncu_istatistikleri(j),
        'kadro': {'tur': lu.get('lineupType'), 'ev': _takim(lu.get('homeTeam') or {}), 'dep': _takim(lu.get('awayTeam') or {})}
        if lu.get('homeTeam') else None,
    }
    if durum == 'bitti':
        _yaz(yol, out)
    return out
