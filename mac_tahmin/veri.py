"""Understat (5 büyük lig) ve FotMob (diğer ligler) verisini indirip uygulamanın okuduğu
d/<Lig>-<yıl>.json dosyalarına dönüştürür.

Dosya biçimi:
  t: takım adları, m: oynanan maçlar [tarih, ev, dep, ev golü, dep golü, ev xG, dep xG],
  u: oynanmamış maçlar [tarih, ev, dep, başlangıç (UTC, ISO 8601)], tx: (FotMob) takım başına [xG, xGA],
  x: ek istatistik anahtarları, p: oyuncular
  [ad, takım, mevki, maç, dakika, gol, xG, asist, xA, şut, kilit pas, sarı, kırmızı, [ekler], id, ülke]
"""
import html
import http.client
import json
import logging
import re
import unicodedata
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from .sezon import FOTMOB_ID, LIGLER, SON_SEZON, TAKVIM_YILI

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
BEKLEME = 0.3  # istekler arası saniye; kaynak sitelere yük bindirmemek için
logger = logging.getLogger(__name__)

# yalnızca bu siteler (ve alt alan adları) https ile çağrılır; dış JSON'dan gelen adresler de buradan geçer
IZINLI_ALANLAR = ('fotmob.com', 'understat.com', 'transfermarkt.com', 'api.open-meteo.com')
EN_BUYUK_GOVDE = 50 * 1024 * 1024  # bir yanıtın sıkıştırılmış en büyük boyutu (gerçek en büyük yanıt ~1,5 MB)
EN_BUYUK_ACILMIS = 200 * 1024 * 1024  # gzip açıldıktan sonraki en büyük boyut (sıkıştırma bombasına karşı)


def url_guvenli_mi(url):
    """Adres https ve izinli bir sitede (IZINLI_ALANLAR ya da alt alan adı) mi. Kullanıcı bilgisi, özel port ve ters
    eğik çizgi içeren adresler reddedilir."""
    if not isinstance(url, str) or any(c in url for c in '\\ \t\r\n\x00'):
        return False
    try:
        p = urllib.parse.urlsplit(url)
        host, port = p.hostname, p.port
    except ValueError:
        return False
    if p.scheme != 'https' or not host or '@' in p.netloc or port not in (None, 443):
        return False
    return any(host == a or host.endswith('.' + a) for a in IZINLI_ALANLAR)


class GuvenliYonlendirme(urllib.request.HTTPRedirectHandler):
    """İzinli bir sitenin başka bir siteye yönlendirmesini (açık yönlendirme) istek atmadan reddeder: hedef de
    url_guvenli_mi'den geçmeli."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_guvenli_mi(newurl):
            raise ValueError('istek izinsiz bir adrese yönlendirildi')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def guvenli_acici(*ek_isleyiciler):
    """Yönlendirmeleri GuvenliYonlendirme ile denetleyen urllib açıcısı (ek_isleyiciler: testler için)."""
    return urllib.request.build_opener(GuvenliYonlendirme, *ek_isleyiciler)


_ACICI = guvenli_acici()


def ac(istek, timeout=60):
    """Bütün dış istekler buradan çıkar (json_getir, transfermarkt). Testlerde ağı kesmek için tek nokta."""
    return _ACICI.open(istek, timeout=timeout)


def govde_oku(r, sinir=None):
    """Yanıtın gövdesi; sınırdan büyükse ValueError (bellek şişmesin)."""
    sinir = EN_BUYUK_GOVDE if sinir is None else sinir
    govde = r.read(sinir + 1)
    if len(govde) > sinir:
        raise ValueError('yanıt beklenenden çok büyük')
    return govde


def gzip_ac(govde, sinir=None):
    """gzip gövdeyi en çok sinir bayta açar; aşarsa ya da bozuksa ValueError."""
    sinir = EN_BUYUK_ACILMIS if sinir is None else sinir
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        cikti = d.decompress(govde, sinir + 1)
    except zlib.error as ex:
        raise ValueError('yanıt açılamadı') from ex
    if len(cikti) > sinir:
        raise ValueError('açılmış yanıt beklenenden çok büyük')
    if not d.eof:
        raise ValueError('yanıt eksik geldi')
    return cikti


def yanit_oku(r, url):
    """Açık bir yanıtın (varsa gzip açılmış) gövdesi. Yönlendirme izinsiz bir siteye gittiyse ValueError."""
    son = r.geturl() if hasattr(r, 'geturl') else url
    if not url_guvenli_mi(son):
        raise ValueError('yanıt izinsiz bir adrese yönlendirildi')
    govde = govde_oku(r)
    # bazı sunucular istenmese de gzip gönderiyor
    return gzip_ac(govde) if govde[:2] == b'\x1f\x8b' else govde


FOTMOB_API = 'https://www.fotmob.com/api/data'


def fotmob_url(yol, **param):
    """FotMob API adresi: fotmob_url('leagues', id=47, season='2025/2026') → .../leagues?id=47&season=2025%2F2026.
    Değerler tamamen yüzde-kodlanır ('/' dahil); None olanlar atlanır."""
    sorgu = '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in param.items() if v is not None)
    return f'{FOTMOB_API}/{yol}' + (f'?{sorgu}' if sorgu else '')


def kimlik(x):
    """Dosya adına girecek kimliği (takım, maç, oyuncu) metin olarak döner; yalnızca ASCII rakamlardan oluşmuyorsa
    ValueError. Dış kaynaktan gelen değerler yol gezintisine (../) açık olmasın diye dosya yollarından önce kullanılır."""
    if isinstance(x, bool) or not isinstance(x, (int, str)):
        raise ValueError('geçersiz kimlik')
    s = str(x)
    if not re.fullmatch(r'[0-9]{1,18}', s):
        raise ValueError('geçersiz kimlik')
    return s


def hata_ozeti(ex):
    """Kullanıcıya (arayüz, durum satırı) gösterilebilecek kısa, ayrıntısız hata metni: yol, adres ve istisna metni
    sızmasın. Ayrıntı logging ile günlüğe yazılır."""
    if isinstance(ex, (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException)):
        return 'internet bağlantısı yok ya da kaynak yanıt vermiyor'
    return 'beklenmeyen bir sorun oluştu (ayrıntı uygulama günlüğünde)'


def liste_url(giris):
    """FotMob istatistik listesi girişindeki fetchAllUrl, izinliyse; değilse uyarı yazılır ve None döner."""
    url = (giris or {}).get('fetchAllUrl')
    if url_guvenli_mi(url):
        return url
    logger.warning('FotMob liste adresi izinli değil, atlandı: %.80r', url)
    return None


def json_getir(url, ek_basliklar=None):
    if not url_guvenli_mi(url):
        raise ValueError(f'izinsiz adres reddedildi: {str(url)[:80]}')
    # gzip: yanıtlar 8-12 kat küçük gelir (açma yanit_oku'da); sunucu sıkıştırmazsa düz gelir, o da okunur
    basliklar = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*', 'Accept-Encoding': 'gzip',
                 **(ek_basliklar or {})}
    with ac(urllib.request.Request(url, headers=basliklar), timeout=60) as r:
        govde = yanit_oku(r, url)
    return json.loads(govde.decode('utf-8'))


def onbellekli(yol, url, ek_basliklar=None, yenile=False):
    """Ham yanıtı diske yazar; aynı dosya varsa yeniden indirmez."""
    yol = Path(yol)
    if yol.exists() and not yenile:
        return json.loads(yol.read_text(encoding='utf-8'))
    veri = json_getir(url, ek_basliklar)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding='utf-8')
    time.sleep(BEKLEME)
    return veri


def r2(v):
    return None if v is None else round(float(v), 2)


# ---------------------------------------------------------------- Understat

def _sade_ad(s):
    s = unicodedata.normalize('NFD', str(s).lower().replace('ı', 'i'))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r"[^a-z0-9 ]", ' ', s).split())


def fotmob_mevki_haritasi(anahtar, yil, ham, yenile=False):
    """Aynı ligin aynı sezonu için FotMob'un oyuncu mevkileri: [(sade ad, FotMob takım adı, mevki harfi)] ve
    FotMob takım adları; FotMob'da o sezonun oyuncu listesi yoksa None."""
    lid = FOTMOB_ID[anahtar]
    try:
        lg = onbellekli(Path(ham) / f'fm-{lid}-{yil}.json',
                        fotmob_url('leagues', id=lid, season=f'{yil}/{yil + 1}'), yenile=yenile)
        if lg['details'].get('selectedSeason') != f'{yil}/{yil + 1}':
            return None
        giris = next((e for e in lg['stats'].get('players') or [] if e['name'] == 'mins_played'), None)
        if not giris:
            return None
        liste = liste_url(giris)
        if not liste:
            return None
        x = onbellekli(Path(ham) / f'fm-{lid}-{yil}-mins_played.json', liste, yenile=yenile)
    except Exception:
        logger.warning('FotMob mevki haritası alınamadı: %s %s', anahtar, yil, exc_info=True)
        return None
    takimlar = {}
    for mm in lg['fixtures']['allMatches']:
        takimlar[mm['home']['name']] = int(mm['home']['id'])
        takimlar[mm['away']['name']] = int(mm['away']['id'])
    oyuncular = []
    for it in x['TopLists'][0]['StatList']:
        kod = int(it['Positions'][0]) if it.get('Positions') else None
        if kod is not None:
            oyuncular.append((_sade_ad(it['ParticipantName']), it.get('TeamName'),
                              (fotmob_mevki(kod), fotmob_detay(kod), it['ParticiantId'])))
    # süren sezonda ligden ayrılanlar: FotMob id -> [yeni kulüp, tarih] (lig içi transferleri Understat zaten iki takımla yazar)
    ayrilan = {}
    if yil == SON_SEZON:
        sezon_basi = min((mm['status']['utcTime'] for mm in lg['fixtures']['allMatches']), default='')
        lig_ids = {str(i) for i in takimlar.values()}
        for pid, t in son_transferler(lg).items():
            if str(t.get('toClubId')) not in lig_ids:
                a = ayrilma(t, None, sezon_basi)
                if a:
                    ayrilan[pid] = a
    return {'oyuncular': oyuncular, 'takimlar': takimlar, 'ayrilan': ayrilan}


def understat_fotmob_mevki(adlar_takimlar, harita):
    """Understat oyuncularını FotMob oyuncularıyla ad ve takımla eşleştirir; eşleşenin (mevki harfi, ayrıntılı
    mevki, FotMob id) üçlüsünü döner. adlar_takimlar: [(ad, [Understat takım adları])]. Eşleşmeyenler için None."""
    import difflib
    from .stadyum import eslestir
    us_takimlar = sorted({t for _, ts in adlar_takimlar for t in ts})
    t_es = eslestir(us_takimlar, harita['takimlar'])  # Understat takım adı -> FotMob takım id
    id_ad = {v: k for k, v in harita['takimlar'].items()}
    takim_ici = {}
    for ad, takim, harf in harita['oyuncular']:
        takim_ici.setdefault(takim, []).append((ad, harf))
    tum = [(ad, harf) for ad, _, harf in harita['oyuncular']]
    sonuc = []
    for ad, ts in adlar_takimlar:
        a = _sade_ad(ad)
        adaylar = [c for t in ts for c in takim_ici.get(id_ad.get(t_es.get(t)), [])]
        en, en_puan = None, 0
        for havuz, esik in ((adaylar, 0.72), (tum, 0.92)):  # önce aynı takımda, olmazsa ligin tamamında (sıkı)
            for b, harf in havuz:
                puan = difflib.SequenceMatcher(None, a, b).ratio()
                ta, tb = a.split(), b.split()
                if ta and tb and ta[-1] == tb[-1]:
                    puan += 0.15  # soyadı aynı
                if puan > en_puan and puan >= esik:
                    en, en_puan = harf, puan
            if en:
                break
        sonuc.append(en)
    return sonuc


UNDERSTAT_LIGLERI = ('EPL', 'La_liga', 'Serie_A', 'Bundesliga', 'Ligue_1')
_ID_MEVKI = {}  # (lig, yıl) -> {Understat oyuncu id: (mevki harfi, ayrıntılı mevki, FotMob id)}; bir kez hesaplanır


def _id_mevki(anahtar, yil, ham, yenile=False):
    if (anahtar, yil) not in _ID_MEVKI:
        harita = fotmob_mevki_haritasi(anahtar, yil, ham, yenile)
        sonuc = {}
        if harita:
            try:
                j = onbellekli(Path(ham) / f'{anahtar}-{yil}.json',
                               f'https://understat.com/getLeagueData/{anahtar}/{yil}',
                               {'X-Requested-With': 'XMLHttpRequest'}, yenile)
                fix = lambda s: html.unescape(str(s))
                oy = [o for o in j['players'] if int(o['time']) > 0]
                fm = understat_fotmob_mevki([(fix(o['player_name']), [fix(t) for t in o['team_title'].split(',')])
                                             for o in oy], harita)
                sonuc = {int(o['id']): h for o, h in zip(oy, fm) if h}
            except Exception:
                logger.warning('Understat/FotMob mevki eşleşmesi kurulamadı: %s %s', anahtar, yil, exc_info=True)
                sonuc = {}
        _ID_MEVKI[(anahtar, yil)] = sonuc
    return _ID_MEVKI[(anahtar, yil)]


def sonraki_sezon_mevkileri(yil, ham, yenile=False, pencere=4):
    """FotMob'un oyuncu verisi olmayan eski sezonlar için: Understat oyuncu id -> oyuncunun bu sezondan sonraki en
    yakın sezonundaki (beş büyük ligin herhangi birinde) FotMob eşleşmesi (mevki harfi, ayrıntılı mevki, FotMob id)."""
    sonuc = {}
    for y2 in range(yil + 1, min(SON_SEZON, yil + pencere) + 1):
        for lig in UNDERSTAT_LIGLERI:
            for pid, h in _id_mevki(lig, y2, ham, yenile).items():
                sonuc.setdefault(pid, h)  # en yakın sezon önce geldiği için ilk bulunan kalır
    return sonuc


def _uyumlu(harf, mevki_yazisi):
    """Taşınan mevki, Understat'ın bu sezon için yazdığı mevkilerle çelişmiyor mu? Kanat; forvet ya da orta sahada
    oynamış birine verilebilir. Yalnızca 'S' (yedek) yazılıysa her saha mevkisi kabul edilir."""
    tok = mevki_yazisi.split()
    saha = [t for t in tok if t in ('D', 'M', 'F')]
    if harf == 'G':
        return 'GK' in tok
    if not saha:
        return 'GK' not in tok
    return harf in saha or (harf == 'W' and ('F' in saha or 'M' in saha))


def understat_donustur(j, harita=None, onceki_mevki=None, dogumlar=None, fm_ek=None):
    """fm_ek: FotMob id -> FotMob ek istatistikleri (fotmob_ek_istatistikleri); verilirse FotMob'la eşleşen oyunculara
    eklenir (top çalma, pas isabeti, puan…). Eşleşmeyenlerde bu değerler boş kalır."""
    fix = lambda s: html.unescape(str(s))
    adlar = sorted({fix(t['title']) for t in j['teams'].values()})
    ix = {a: i for i, a in enumerate(adlar)}
    m, u = [], []
    for d in sorted(j['dates'], key=lambda d: d['datetime']):
        h, a = fix(d['h']['title']), fix(d['a']['title'])
        if h not in ix or a not in ix:
            continue
        tarih = d['datetime'][:10]
        if d['isResult']:
            m.append([tarih, ix[h], ix[a], int(d['goals']['h']), int(d['goals']['a']),
                      r2(d['xG']['h']), r2(d['xG']['a'])])
        else:
            # Understat saatleri UTC verir: "2026-10-10 11:30:00"
            u.append([tarih, ix[h], ix[a], d['datetime'].replace(' ', 'T') + 'Z'])
    p = []
    oyuncular = [o for o in j['players'] if int(o['time']) > 0]
    # mevki: FotMob'da eşleşen oyuncu varsa onun ana mevkisi (kanat dahil); yoksa Understat'ın oynadığı bütün
    # mevkileri sabit sırayla yazdığı hâli ("D M S"), ana mevki sonra istatistiklerden seçilir
    # eski sezonlarda FotMob eşleşmesi oyuncunun sonraki sezonlarından taşınır (doğum tarihi için her zaman, mevki
    # için Understat'ın o sezon yazdığıyla uyumluysa)
    fm = (understat_fotmob_mevki([(fix(o['player_name']), [fix(t) for t in o['team_title'].split(',')])
                                  for o in oyuncular], harita) if harita
          else [(onceki_mevki or {}).get(int(o['id'])) for o in oyuncular])
    if dogumlar is None:
        dogumlar = {}
    for o, es in zip(oyuncular, fm):
        takim = ' / '.join(fix(t) for t in o['team_title'].split(','))
        ek = [int(o['npg']), r2(o['npxG']), r2(o['xGChain']), r2(o['xGBuildup'])]
        mevki, detay = o['position'], None
        harf, fm_detay, fm_id = es or (None, None, None)
        if fm_ek:
            ek += fm_ek.get(str(fm_id)) or [None] * len(US_FOTMOB_EK)
        uygun = (_uyumlu(harf, mevki) if not harita else not ('GK' in mevki.split() and harf != 'G'))
        if harf and harf != 'U' and uygun:
            mevki, detay = harf, fm_detay
        p.append([fix(o['player_name']), takim, mevki, int(o['games']), int(o['time']),
                  int(o['goals']), r2(o['xG']), int(o['assists']), r2(o['xA']), int(o['shots']),
                  int(o['key_passes']), int(o['yellow_cards']), int(o['red_cards']), ek, int(o['id']), None,
                  detay, dogumlar.get(str(fm_id)) or None if fm_id else None,
                  ((harita or {}).get('ayrilan') or {}).get(str(fm_id)) if fm_id else None,
                  int(fm_id) if fm_id else None])  # FotMob oyuncu id (oyuncu kartındaki son maçlar için)
    return {'src': 'understat', 't': adlar, 'm': m, 'u': u,
            'x': [['npg', 'Penaltısız gol', 't'], ['npxg', 'Penaltısız xG', 't'],
                  ['xgc', 'xG zinciri', 't'], ['xgb', 'xG hazırlık', 't']] + (US_FOTMOB_EK if fm_ek else []), 'p': p}


def understat_sezon(anahtar, yil, ham, yenile=False):
    j = onbellekli(Path(ham) / f'{anahtar}-{yil}.json', f'https://understat.com/getLeagueData/{anahtar}/{yil}',
                   {'X-Requested-With': 'XMLHttpRequest'}, yenile)
    from .dogum import dogum_oku, tamamla
    harita = fotmob_mevki_haritasi(anahtar, yil, ham, yenile)
    onceki = None if harita else sonraki_sezon_mevkileri(yil, ham, yenile)
    if harita:
        tamamla([o[2][2] for o in harita['oyuncular']], ham)
    fm_ek = fotmob_ek_istatistikleri(anahtar, yil, ham, yenile) if harita else None
    return understat_donustur(j, harita, onceki, dogum_oku(ham), fm_ek)


# ---------------------------------------------------------------- FotMob (Süper Lig ve diğer ligler)

LISTELER = ['mins_played', 'goals', 'goal_assist', 'expected_goals', 'expected_assists', 'total_scoring_att',
            'total_att_assist', 'yellow_card', 'red_card', 'rating', 'expected_goalsontarget',
            'big_chance_created', 'big_chance_missed', 'won_contest', 'accurate_pass', 'total_tackle',
            'interception', 'effective_clearance', 'ball_recovery', 'saves', '_save_percentage',
            'goals_conceded', 'clean_sheet', '_goals_prevented']
FOTMOB_EK = [['rt', 'FotMob puanı', 'r'], ['npg', 'Penaltısız gol', 't'], ['xgot', 'İsabetli şut xG (xGOT)', 't'],
             ['bcc', 'Yaratılan net pozisyon', 't'], ['bcm', 'Kaçan net pozisyon', 't'],
             ['drb', 'Başarılı çalım (90 dk)', 'r'], ['drbp', 'Çalım başarısı %', 'r'],
             ['pas', 'İsabetli pas (90 dk)', 'r'], ['pasp', 'Pas isabeti %', 'r'], ['tkl', 'Top çalma', 't'],
             ['int', 'Pas arası', 't'], ['clr', 'Uzaklaştırma', 't'], ['rec', 'Top kazanma', 't'],
             ['sav', 'Kurtarış', 't'], ['savp', 'Kurtarış %', 'r'], ['gc', 'Yenen gol', 't'],
             ['cs', 'Gol yemeden maç', 't'], ['gp', 'Önlenen gol', 'r']]


# ayrıntılı mevki -> ana mevki harfi
DETAY_GRUP = {'GK': 'G', 'CB': 'D', 'RB': 'D', 'LB': 'D', 'DM': 'M', 'CM': 'M', 'AM': 'M', 'RW': 'W', 'LW': 'W',
              'ST': 'F'}


def fotmob_detay(kod):
    """FotMob sahayı ızgara gibi numaralar: onlar basamağı hat (3 defans, 4-5 kanat bek, 6 ön libero, 7 orta saha,
    8-9 hücum orta saha, 10-11 forvet), birler basamağı yan konum (1-2 sağ ... 8-9 sol). 0-3 yalnızca genel rol
    (kaleci/defans/orta saha/forvet) verir; o zaman ayrıntı yoktur (None)."""
    if kod is None or kod in (1, 2, 3):
        return None
    if kod in (0, 11):
        return 'GK'
    hat, yan = divmod(kod, 10)
    sag, sol = yan <= 2, yan >= 8
    if hat <= 3:
        return 'RB' if sag else 'LB' if sol else 'CB'
    if hat <= 5:  # kanat bekler; ortadakiler üçlü savunmanın stoperi ya da ön libero
        return 'RB' if yan <= 3 else 'LB' if yan >= 7 else 'CB' if hat == 4 else 'DM'
    if hat == 6:
        return 'RB' if sag else 'LB' if sol else 'DM'
    if hat == 7:
        return 'RW' if sag else 'LW' if sol else 'CM'
    if hat <= 9:
        return 'RW' if yan <= 3 else 'LW' if yan >= 7 else 'AM'
    return 'RW' if yan <= 3 else 'LW' if yan >= 7 else 'ST'


def fotmob_mevki(kod):
    if kod is None:
        return 'U'
    if kod in (1, 2, 3):
        return 'DMF'[kod - 1]
    return DETAY_GRUP[fotmob_detay(kod)]


def son_transferler(lg):
    """FotMob lig sayfasındaki son transferlerden (ligin takımlarına gelen ya da onlardan giden, en yeni ~100) her
    oyuncunun son transferi: {oyuncu id: transfer}. Sezon sürerken takımından ayrılanları bulmak için."""
    son = {}
    for t in sorted(((lg.get('transfers') or {}).get('data') or []), key=lambda t: t.get('transferDate') or ''):
        if t.get('playerId') and not t.get('contractExtension'):
            son[str(t['playerId'])] = t
    return son


def ayrilma(t, takim_id, sezon_basi):
    """Oyuncu sezon başladıktan sonra takımından başka bir kulübe gittiyse [yeni kulüp, tarih], değilse None."""
    if not t or (t.get('transferDate') or '') < sezon_basi or str(t.get('toClubId')) == str(takim_id):
        return None
    return [t.get('toClub') or t.get('toClubFullName') or '', (t.get('transferDate') or '')[:10]]


def nz(x, d):
    return d if x is None else x


def i0(x):
    return None if x is None else int(round(x))


def _fotmob_liste(lg, ham, lig_id, yil, ad, kaynak, anahtar, yenile=False):
    """FotMob lig sayfasındaki bir istatistik listesinin tamamı: {oyuncu ya da takım id: satır}; liste yoksa {}."""
    giris = next((e for e in lg['stats'].get(kaynak) or [] if e['name'] == ad), None)
    if not giris:
        return {}
    url = liste_url(giris)
    if not url:
        return {}
    x = onbellekli(Path(ham) / f'fm-{lig_id}-{yil}-{ad}.json', url, yenile=yenile)
    return {str(it[anahtar]): it for it in x['TopLists'][0]['StatList']}


def _okuyucular(L):
    """Listelerden bir oyuncunun değeri (v: ana değer, sv: yan değer; ör. top çalmada toplam sayı)."""
    def v(ad, i):
        it = L[ad].get(i)
        return None if it is None else float(it['StatValue'])

    def sv(ad, i):
        it = L[ad].get(i)
        return None if it is None or it.get('SubStatValue') is None else float(it['SubStatValue'])
    return v, sv


def _fotmob_ek(v, sv, i, npg):
    """FOTMOB_EK sırasıyla bir oyuncunun ek istatistikleri."""
    return [r2(v('rating', i)), npg, r2(v('expected_goalsontarget', i)),
            int(nz(v('big_chance_created', i), 0)), int(nz(v('big_chance_missed', i), 0)),
            r2(v('won_contest', i)), r2(sv('won_contest', i)), r2(v('accurate_pass', i)), r2(sv('accurate_pass', i)),
            i0(sv('total_tackle', i)), i0(sv('interception', i)), i0(sv('effective_clearance', i)),
            i0(sv('ball_recovery', i)), i0(sv('saves', i)), r2(v('_save_percentage', i)),
            i0(sv('goals_conceded', i)), i0(v('clean_sheet', i)), r2(v('_goals_prevented', i))]


# beş büyük ligde Understat'ın tutmadığı, FotMob'dan eklenen istatistikler (penaltısız gol Understat'ta zaten var)
US_FOTMOB_EK = [x for x in FOTMOB_EK if x[0] != 'npg']


def fotmob_ek_istatistikleri(anahtar, yil, ham, yenile=False):
    """Beş büyük lig için: FotMob oyuncu id -> US_FOTMOB_EK sırasıyla ek istatistikler. FotMob'da o sezon yoksa {}."""
    lid = FOTMOB_ID[anahtar]
    try:
        lg = onbellekli(Path(ham) / f'fm-{lid}-{yil}.json',
                        fotmob_url('leagues', id=lid, season=f'{yil}/{yil + 1}'), yenile=yenile)
        if lg['details'].get('selectedSeason') != f'{yil}/{yil + 1}':
            return {}
        L = {ad: _fotmob_liste(lg, ham, lid, yil, ad, 'players', 'ParticiantId', yenile) for ad in LISTELER}
    except Exception:
        logger.warning('FotMob ek istatistikleri alınamadı: %s %s', anahtar, yil, exc_info=True)
        return {}
    v, sv = _okuyucular(L)
    sil = [x[0] for x in FOTMOB_EK].index('npg')
    return {i: [x for j, x in enumerate(_fotmob_ek(v, sv, i, None)) if j != sil] for i in L['mins_played']}


def fotmob_sezon(yil, ham, yenile=False, lig_id=71, takvim_yili=False):
    """Bir FotMob liginin bir sezonu. yil: Ağustos-Mayıs liglerinde başlangıç yılı ("2025/2026"),
    takvim yılına göre oynanan liglerde (takvim_yili=True) sezonun yılı ("2025")."""
    ham = Path(ham)
    sezon = str(yil) if takvim_yili else f'{yil}/{yil + 1}'
    lg = onbellekli(ham / f'fm-{lig_id}-{yil}.json',
                    fotmob_url('leagues', id=lig_id, season=sezon),
                    yenile=yenile)
    if lg['details'].get('selectedSeason') != sezon:  # FotMob olmayan sezon yerine güncel sezonu döndürebiliyor
        raise ValueError(f'FotMob {sezon} sezonunu vermedi ({lg["details"].get("selectedSeason")})')
    tid = {}
    for mm in lg['fixtures']['allMatches']:
        tid[str(mm['home']['id'])] = mm['home']['name']
        tid[str(mm['away']['id'])] = mm['away']['name']
    adlar = sorted(set(tid.values()))
    ix = {a: i for i, a in enumerate(adlar)}
    m, u, atlanan = [], [], 0
    for mm in sorted(lg['fixtures']['allMatches'], key=lambda x: x['status']['utcTime']):
        st = mm['status']
        tarih = st['utcTime'][:10]
        h, a = ix[mm['home']['name']], ix[mm['away']['name']]
        if st.get('cancelled') or st.get('awarded'):
            atlanan += 1
            continue
        if st.get('finished'):
            hg, ag = (int(x) for x in st['scoreStr'].split('-'))
            m.append([tarih, h, a, hg, ag, None, None])
        else:
            u.append([tarih, h, a, st['utcTime']])

    L = {ad: _fotmob_liste(lg, ham, lig_id, yil, ad, 'players', 'ParticiantId', yenile) for ad in LISTELER}
    txg = _fotmob_liste(lg, ham, lig_id, yil, 'expected_goals_team', 'teams', 'TeamId', yenile)
    txga = _fotmob_liste(lg, ham, lig_id, yil, 'expected_goals_conceded_team', 'teams', 'TeamId', yenile)
    tx = [[0, 0] for _ in adlar]
    for k, ad in tid.items():
        if k in txg and k in txga:
            tx[ix[ad]] = [r2(txg[k]['StatValue']), r2(txga[k]['StatValue'])]
    v, sv = _okuyucular(L)
    # süren sezonda takımından ayrılanlar (eski sezonlarda bu bilgi anlamsız: sayfa o sezondan sonra da güncellenmiş olabilir)
    transfer = son_transferler(lg) if yil == SON_SEZON else {}
    sezon_basi = min((mm['status']['utcTime'] for mm in lg['fixtures']['allMatches']), default='')

    from .dogum import dogum_oku, tamamla
    tamamla(L['mins_played'].keys(), ham)
    dogumlar = dogum_oku(ham)
    p = []
    for i, it in L['mins_played'].items():
        dk = int(it.get('MinutesPlayed') or 0) or int(it.get('StatValue') or 0)
        if dk <= 0:
            continue
        mac = int(it.get('MatchesPlayed') or 0) or int(it.get('SubStatValue') or 0)
        takim = tid.get(str(it.get('TeamId')), it.get('TeamName'))
        kod = int(it['Positions'][0]) if it.get('Positions') else None
        mevki, detay = fotmob_mevki(kod), fotmob_detay(kod)
        g = int(nz(v('goals', i), 0))
        pen = int(nz(sv('goals', i), 0))
        sh90 = v('total_scoring_att', i)
        sut = None if sh90 is None else int(round(sh90 * dk / 90))
        sari = int(nz(v('yellow_card', i), nz(sv('red_card', i), 0)))
        kirmizi = int(nz(v('red_card', i), nz(sv('yellow_card', i), 0)))
        ek = _fotmob_ek(v, sv, i, g - pen)
        p.append([it['ParticipantName'], takim, mevki, mac, dk, g, r2(nz(v('expected_goals', i), 0)),
                  int(nz(v('goal_assist', i), 0)), r2(nz(v('expected_assists', i), 0)), sut,
                  int(nz(v('total_att_assist', i), 0)), sari, kirmizi, ek, int(i), it.get('ParticipantCountryCode'),
                  detay, dogumlar.get(str(i)) or None, ayrilma(transfer.get(str(i)), it.get('TeamId'), sezon_basi)])
    return {'src': 'fotmob', 't': adlar, 'm': m, 'u': u, 'tx': tx, 'x': FOTMOB_EK, 'p': p, 'skip': atlanan}


# ---------------------------------------------------------------- toplu indirme

def indir(ligler=None, yillar=None, cikti='d', ham='ham', yenile=False, yaz=print):
    """Seçilen lig ve sezonları indirip d/ klasörüne yazar. Hata veren sezon atlanır ve raporlanır.
    İndirilemeyen sezon sayısını döndürür."""
    Path(cikti).mkdir(parents=True, exist_ok=True)
    hatali = 0
    for anahtar, ad, _, ilk, kaynak in LIGLER:
        if ligler and anahtar not in ligler:
            continue
        for y in range(ilk, SON_SEZON + 1):
            if yillar and y not in yillar:
                continue
            try:
                veri = (understat_sezon(anahtar, y, ham, yenile) if kaynak == 'understat'
                        else fotmob_sezon(y, ham, yenile, FOTMOB_ID[anahtar], anahtar in TAKVIM_YILI))
            except Exception as e:  # tek sezonun hatası diğerlerini durdurmasın
                yaz(f'{anahtar}-{y}: indirilemedi ({e})')
                logger.warning('%s-%s indirilemedi', anahtar, y, exc_info=True)
                hatali += 1
                continue
            yol = Path(cikti) / f'{anahtar}-{y}.json'
            metin = json.dumps(veri, ensure_ascii=False, separators=(',', ':'))
            # değişmediyse yazılmaz: dosya zamanı aynı kalır, uygulama o ligi yeniden kurmaz (depo.Depo.sezon)
            if not (yol.exists() and yol.read_text(encoding='utf-8') == metin):
                gecici = yol.with_suffix('.tmp')
                gecici.write_text(metin, encoding='utf-8')
                gecici.replace(yol)  # sunucu açıkken sayfa yarım yazılmış dosyayı okumasın
            yaz(f'{anahtar}-{y}: {len(veri["m"])} maç, {len(veri["u"])} kalan, {len(veri["p"])} oyuncu')
    return hatali
