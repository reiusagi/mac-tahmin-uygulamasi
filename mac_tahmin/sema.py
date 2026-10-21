"""Dış kaynakların (FotMob, Understat) yanıt biçimi denetimi. FotMob resmi olmayan bir API'dir: alanları yeniden adlandırırsa
ayrıştırma sessizce boş sonuç verir. Burada her yanıt türü için beklenen alan yolları yazılır; ayrıştırma yerlerinde
kontrol(tur, veri) çağrılır, eksik alanlar günlüğe WARNING olarak yazılır ve sorunlar() ile arayüze (alt bilgi) taşınır.

Yol dili (noktayla ayrılır; yalnızca ilk öğe örneklenir, bu yüzden yanıt boyutundan bağımsız ucuzdur):
  ad          sözlükte 'ad' anahtarı bulunmalı (değeri boş/None olabilir)
  ad[]        değer liste olmalı; boş değilse ilk öğesine inilir
  ad{}        değer sözlük olmalı; boş değilse ilk değerine inilir
  yol:tip     değer ayrıca boş olmamalı ve türü tutmalı: s yazı, n sayı (Understat sayıları yazı olarak da verir),
              l liste, d sözlük, b mantıksal
  ?yol        isteğe bağlı: yolun aradaki bir halkası yoksa ya da None ise sessizce geçilir (son anahtar yine zorunlu)
"""
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# yanıt türü -> (kaynak, arayüzde görünen ad, [yollar])
_MAC_YAPISI = [  # allMatches öğesinin alanları
    'fixtures.allMatches[].id', 'fixtures.allMatches[].home.id', 'fixtures.allMatches[].home.name:s',
    'fixtures.allMatches[].away.id', 'fixtures.allMatches[].away.name:s',
    'fixtures.allMatches[].status.utcTime:s', 'fixtures.allMatches[].status.finished:b']
_TRANSFER = ['?transfers.data[].playerId', '?transfers.data[].transferDate', '?transfers.data[].toClubId']
_LIG = ['details.selectedSeason:s', 'fixtures.allMatches:l'] + _MAC_YAPISI + _TRANSFER
# eski turnuva sezonlarında (ör. 2010) FotMob maç listesini hiç vermez: orada maç alanları isteğe bağlı
_KUPA = ['details.selectedSeason:s', 'fixtures:d'] + ['?' + y for y in _MAC_YAPISI] + _TRANSFER
_OYUNCU_LISTE = ['TopLists:l', 'TopLists[].StatList:l', '?TopLists[].StatList[].ParticiantId',
                 '?TopLists[].StatList[].StatValue', '?TopLists[].StatList[].TeamId']
TURLER = {
    'lig': ('FotMob', 'lig sayfası', _LIG + [
        'stats:d', '?stats.players[].name:s', '?stats.players[].fetchAllUrl:s',
        '?stats.teams[].name:s', '?stats.teams[].fetchAllUrl:s']),
    # milli takım turnuvaları ve Avrupa kupaları: aynı lig sayfası, ek olarak tablo ve eleme ağacı (istatistik yok)
    'kupa': ('FotMob', 'turnuva sayfası', _KUPA + [
        '?table[].data:d', '?playoff.rounds[].matchups[].matches[].matchId']),
    'oyuncu_liste': ('FotMob', 'istatistik listesi (oyuncu)', _OYUNCU_LISTE + [
        '?TopLists[].StatList[].ParticipantName:s']),
    'takim_liste': ('FotMob', 'istatistik listesi (takım)', _OYUNCU_LISTE),
    'canli': ('FotMob', 'canlı skorlar', [
        'leagues:l', 'leagues[].primaryId', 'leagues[].matches:l', 'leagues[].matches[].id',
        'leagues[].matches[].home.id', 'leagues[].matches[].home.name:s',
        'leagues[].matches[].away.id', 'leagues[].matches[].away.name:s',
        'leagues[].matches[].status:d', 'leagues[].matches[].status.utcTime']),
    'mac': ('FotMob', 'maç ayrıntısı', [
        'header.status:d', 'header.teams:l', 'header.teams[].name:s', 'header.teams[].id', 'content:d',
        '?content.matchFacts.infoBox.Referee.text:s', '?content.matchFacts.infoBox.Stadium.name:s',
        '?content.matchFacts.events.events[].type:s', '?content.stats.Periods.All.stats[].stats:l',
        '?content.lineup.homeTeam.starters[].id', '?content.lineup.homeTeam.starters[].name:s',
        '?content.playerStats{}.name:s']),
    'takim': ('FotMob', 'takım sayfası', [
        'details:d', 'details.name:s', 'details.primaryLeagueId', 'fixtures.allFixtures.fixtures:l',
        'fixtures.allFixtures.fixtures[].id', 'fixtures.allFixtures.fixtures[].home.id',
        'fixtures.allFixtures.fixtures[].away.id', 'fixtures.allFixtures.fixtures[].status:d',
        'fixtures.allFixtures.fixtures[].tournament.leagueId',
        '?squad.squad[].title:s', '?squad.squad[].members[].id', '?squad.squad[].members[].name:s', '?overview.topPlayers:d', '?overview.lastLineupStats.starters[].id']),
    'takim_stadyum': ('FotMob', 'takım sayfası (stadyum)', [
        'overview:d', '?overview.venue.widget.name:s', '?overview.venue.widget.city',
        '?overview.venue.widget.location', '?overview.venue.statPairs:l']),
    'oyuncu': ('FotMob', 'oyuncu sayfası', [
        '?birthDate.utcTime:s', '?recentMatches[].id', '?recentMatches[].matchDate:d', '?recentMatches[].matchDate.utcTime:s',
        '?careerHistory.careerItems:d', '?marketValues.values[].value', '?contractEnd.utcTime:s']),
    'understat': ('Understat', 'Understat lig verisi', [
        'teams:d', 'teams{}.title:s', 'dates:l', 'dates[].datetime:s', 'dates[].isResult', 'dates[].h.title:s',
        'dates[].a.title:s', 'dates[].goals.h', 'dates[].goals.a', 'dates[].xG.h', 'dates[].xG.a',
        'players:l', 'players[].id', 'players[].player_name:s', 'players[].team_title:s', 'players[].position:s',
        'players[].time:n', 'players[].games:n', 'players[].goals:n', 'players[].assists:n', 'players[].shots:n',
        'players[].key_passes:n', 'players[].yellow_cards:n', 'players[].red_cards:n', 'players[].xG:n',
        'players[].xA:n', 'players[].npg:n', 'players[].npxG:n', 'players[].xGChain:n', 'players[].xGBuildup:n']),
}

_TIPLER = {'s': (str, 'yazı'), 'l': (list, 'liste'), 'd': (dict, 'sözlük'), 'b': (bool, 'mantıksal')}
_KILIT = threading.Lock()
_SORUNLAR = {}  # tür -> (zaman, [eksik yollar])


def _derle(yol):
    """'?a.b[].c:s' -> (yol metni, parçalar, tip, isteğe bağlı mı)"""
    istege = yol.startswith('?')
    tam = yol.lstrip('?')
    govde, _, tip = tam.partition(':')
    return tam, govde.split('.'), tip, istege


_DERLENMIS = {tur: [_derle(y) for y in yollar] for tur, (_, _, yollar) in TURLER.items()}


def _tur_adi(v):
    return type(v).__name__


def _tip_uyar(deger, tip):
    if tip == 'n':
        if isinstance(deger, (int, float)) and not isinstance(deger, bool):
            return True
        try:
            float(deger)
            return isinstance(deger, str)
        except (TypeError, ValueError):
            return False
    if tip == 'b':
        return isinstance(deger, bool)
    return isinstance(deger, _TIPLER[tip][0])


def _yuru(veri, parcalar, tip, istege):
    """Yolu izler; sorun varsa (neden, sorunlu halkanın indeksi), yoksa None."""
    cur = veri
    for i, parca in enumerate(parcalar):
        son = i == len(parcalar) - 1
        if cur is None:
            return None  # üst halka boş (ör. kadrosu olmayan takım): bunu o halkanın kendi girdisi denetler
        if not isinstance(cur, dict):
            return f'beklenen sözlük, gelen {_tur_adi(cur)}', i - 1
        kap = parca[-2:] if parca.endswith(('[]', '{}')) else ''
        ad = parca[:-2] if kap else parca
        if ad not in cur:
            return (None if istege and not son else ('eksik', i))
        cur = cur[ad]
        if kap:
            if cur is None:
                return None
            if not isinstance(cur, list if kap == '[]' else dict):
                return f'beklenen {"liste" if kap == "[]" else "sözlük"}, gelen {_tur_adi(cur)}', i
            if not cur:
                return None
            cur = cur[0] if kap == '[]' else next(iter(cur.values()))
    if tip:
        if cur is None:
            return 'boş değer', len(parcalar) - 1
        if not _tip_uyar(cur, tip):
            return f'beklenen {"sayı" if tip == "n" else _TIPLER[tip][1]}, gelen {_tur_adi(cur)}', len(parcalar) - 1
    return None


def _yalin(parcalar):
    return tuple(p[:-2] if p.endswith(('[]', '{}')) else p for p in parcalar)


def denetle(tur, veri):
    """Yanıtta eksik ya da türü tutmayan yolların listesi (boş liste: biçim beklendiği gibi). Bilinmeyen tür KeyError."""
    if tur not in _DERLENMIS:
        raise KeyError(f'bilinmeyen yanıt türü: {tur}')
    if not isinstance(veri, dict):
        return [f'(kök) beklenen sözlük, gelen {_tur_adi(veri)}']
    out, kirik = [], []
    for tam, parcalar, tip, istege in _DERLENMIS[tur]:
        sonuc = _yuru(veri, parcalar, tip, istege)
        if not sonuc:
            continue
        neden, i = sonuc
        # bir üst halkanın kendi girdisi zaten bildirildiyse altındakiler yinelenmez (liste silinince 7 satır yazılmasın)
        if not any(_yalin(parcalar[:i + 1])[:len(k)] == k for k in kirik):
            out.append(f'{tam} ({neden})')
        kirik.append(_yalin(parcalar))
    return out


def kontrol(tur, veri):
    """Ayrıştırma yerlerinde çağrılır: denetler, sorunu günlüğe yazıp kayda geçirir (düzelince kaydı siler). Hiçbir zaman
    istisna atmaz (denetim uygulamayı bozmasın). Döner: eksik yolların listesi."""
    try:
        eksik = denetle(tur, veri)
    except Exception:
        logger.debug('şema denetimi yapılamadı: %s', tur, exc_info=True)
        return []
    with _KILIT:
        onceki = _SORUNLAR.get(tur)
        if eksik:
            _SORUNLAR[tur] = (datetime.now(), eksik)
        else:
            _SORUNLAR.pop(tur, None)
    kaynak, ad = TURLER[tur][:2]
    if eksik and (onceki is None or onceki[1] != eksik):  # aynı sorun her istekte yinelenmesin
        logger.warning('%s veri biçimi değişmiş olabilir: %s (%s): %s', kaynak, ad, tur, '; '.join(eksik))
    elif not eksik and onceki:
        logger.info('%s veri biçimi düzeldi: %s (%s)', kaynak, ad, tur)
    return eksik


def sorunlar():
    """{tur: (zaman, [eksik yollar])}: şu an biçimi bozuk görünen yanıt türleri (kopya)."""
    with _KILIT:
        return dict(_SORUNLAR)


def temizle():
    """Kayıtlı sorunların hepsini siler (testler için)."""
    with _KILIT:
        _SORUNLAR.clear()


def uyari_metni():
    """Alt bilgide gösterilecek kısa Türkçe uyarı; sorun yoksa ''."""
    kayit = sorunlar()
    parcalar = []
    for kaynak in dict.fromkeys(TURLER[t][0] for t in kayit):
        liste = ', '.join(f'{TURLER[t][1]} ({len(kayit[t][1])} alan eksik)' for t in kayit if TURLER[t][0] == kaynak)
        parcalar.append(f'{kaynak} veri biçimi değişmiş olabilir: {liste}')
    return '; '.join(parcalar) + '. Ayrıntı: uygulama.log' if parcalar else ''
