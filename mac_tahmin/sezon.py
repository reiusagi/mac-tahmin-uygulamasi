"""Bir lig-sezon dosyasından puan durumu, Elo, modeller, gol atma olasılıkları ve oyuncu kartı."""
import json
import math
import sys
import threading
import unicodedata
from pathlib import Path

from datetime import date

from .modeller import (Mac, Orman, js_round, lojistik_kur, mulberry32, ortalama, pmf, poisson_kur,
                       skorla, softmax, sonuc_olasiliklari, toplam)

# [anahtar, ad, ülke, ilk sezon, kaynak]
LIGLER = [
    ('EPL', 'Premier League', 'İngiltere', 2014, 'understat'),
    ('La_liga', 'La Liga', 'İspanya', 2014, 'understat'),
    ('Serie_A', 'Serie A', 'İtalya', 2014, 'understat'),
    ('Bundesliga', 'Bundesliga', 'Almanya', 2014, 'understat'),
    ('Ligue_1', 'Ligue 1', 'Fransa', 2014, 'understat'),
    ('Super_Lig', 'Süper Lig', 'Türkiye', 2018, 'fotmob'),
    ('Eredivisie', 'Eredivisie', 'Hollanda', 2018, 'fotmob'),
    ('Primeira_Liga', 'Liga Portugal', 'Portekiz', 2018, 'fotmob'),
    ('Pro_League', 'Pro League', 'Belçika', 2019, 'fotmob'),
    ('Premiership', 'Premiership', 'İskoçya', 2020, 'fotmob'),
    ('Championship', 'Championship', 'İngiltere 2. lig', 2018, 'fotmob'),
    ('Saudi_Pro_League', 'Saudi Pro League', 'Suudi Arabistan', 2021, 'fotmob'),
    ('Austria_Bundesliga', 'Bundesliga', 'Avusturya', 2019, 'fotmob'),
    ('Swiss_Super_League', 'Super League', 'İsviçre', 2018, 'fotmob'),
    ('Greek_Super_League', 'Super League 1', 'Yunanistan', 2024, 'fotmob'),
    ('Eliteserien', 'Eliteserien', 'Norveç', 2020, 'fotmob'),
    ('Brasileirao', 'Série A', 'Brezilya', 2019, 'fotmob'),
    ('Liga_Profesional', 'Liga Profesional', 'Arjantin', 2021, 'fotmob'),
]
LIG_ADI = {l[0]: l[1] for l in LIGLER}  # lig anahtarı → görünen ad
# FotMob lig kimlikleri: canlı skor, stadyum ve (FotMob kaynaklı liglerde) sezon verisi için
FOTMOB_ID = {'EPL': 47, 'La_liga': 87, 'Serie_A': 55, 'Bundesliga': 54, 'Ligue_1': 53, 'Super_Lig': 71,
             'Eredivisie': 57, 'Primeira_Liga': 61, 'Pro_League': 40, 'Premiership': 64, 'Championship': 48,
             'Saudi_Pro_League': 536, 'Austria_Bundesliga': 38, 'Swiss_Super_League': 69, 'Greek_Super_League': 135,
             'Eliteserien': 59, 'Brasileirao': 268, 'Liga_Profesional': 112}
# sezonu takvim yılına göre oynanan ligler: sezon "2026" diye adlandırılır, "2026/27" değil
TAKVIM_YILI = {'Eliteserien', 'Brasileirao', 'Liga_Profesional'}
SON_SEZON = 2026
POS = {'F': 'Forvet', 'W': 'Kanat', 'M': 'Orta saha', 'D': 'Defans', 'G': 'Kaleci', 'S': 'Yedek', 'U': 'Belirsiz'}
SAHA = ('D', 'M', 'F', 'W')  # saha mevkileri: defans, orta saha, forvet, kanat
# ayrıntılı mevkiler (FotMob'un sahadaki yerinden); ana mevki harfi ve adı
DETAY = {'GK': ('G', 'Kaleci'), 'CB': ('D', 'Stoper'), 'RB': ('D', 'Sağ bek'), 'LB': ('D', 'Sol bek'),
         'DM': ('M', 'Ön libero'), 'CM': ('M', 'Merkez orta saha'), 'AM': ('M', 'On numara'),
         'RW': ('W', 'Sağ kanat'), 'LW': ('W', 'Sol kanat'), 'ST': ('F', 'Forvet')}
# yaş süzgeçleri: (ad, en küçük yaş, en büyük yaş)
YAS_GRUPLARI = {'U18': (0, 17), 'U21': (0, 20), 'U23': (0, 22), '23-29': (23, 29), '30+': (30, 99)}


# Puan eşitliğinde sıralama (gerçek lig kuralları). 'averaj': averaj, atılan gol (varsayılan; İngiltere, Almanya, Fransa,
# Hollanda, İskoçya, İsviçre, Norveç, Arjantin…). 'ikili': eşit puanlı takımların kendi aralarındaki maçlar (puan, averaj),
# sonra genel averaj ve atılan gol. 'galibiyet': galibiyet sayısı, averaj, atılan gol (Brezilya). Emin olunmayan ligler
# (Belçika: galibiyet sayısı önce olabilir; Avusturya) varsayılanda bırakıldı.
ESITLIK_KURALI = {'La_liga': 'ikili', 'Serie_A': 'ikili', 'Super_Lig': 'ikili', 'Primeira_Liga': 'ikili',
                  'Greek_Super_League': 'ikili', 'Saudi_Pro_League': 'ikili', 'Brasileirao': 'galibiyet'}


def esitlik_kurali(anahtar):
    return ESITLIK_KURALI.get(anahtar, 'averaj')


def tablo_sirala(tb, M, kural='averaj'):
    """Puan durumu sırası (tb: takım satırları, M: oynanmış maçlar). Puanı eşit olanların hepsi tek grup sayılır ve
    'ikili' kuralda ikili maç tablosu bu grubun maçlarından kurulur (grup içinde kısmi eşitlikte yeniden bölünmez)."""
    if kural == 'galibiyet':
        return sorted(tb, key=lambda r: (-r['P'], -r['G'], -r['AV'], -r['AG']))
    if kural != 'ikili':
        return sorted(tb, key=lambda r: (-r['P'], -r['AV'], -r['AG']))
    puan = {r['i']: r['P'] for r in tb}
    ikili = {i: [0, 0] for i in puan}  # takım -> [ikili puan, ikili averaj]
    for m in M:
        if m.h in puan and m.a in puan and puan[m.h] == puan[m.a]:
            ikili[m.h][1] += m.hg - m.ag
            ikili[m.a][1] += m.ag - m.hg
            ikili[m.h][0] += 3 if m.hg > m.ag else 1 if m.hg == m.ag else 0
            ikili[m.a][0] += 3 if m.ag > m.hg else 1 if m.hg == m.ag else 0
    return sorted(tb, key=lambda r: (-r['P'], -ikili[r['i']][0], -ikili[r['i']][1], -r['AV'], -r['AG']))


def yas_tarihi(yil, takvim_yili=False, bugun=None):
    """Yaşın hesaplandığı gün: süren sezonda bugün; geçmiş sezonlarda sezonun ortası (Ağustos-Mayıs liglerinde
    1 Ocak, takvim yılı liglerinde 1 Temmuz)."""
    if yil >= SON_SEZON:
        return bugun or date.today()
    return date(yil, 7, 1) if takvim_yili else date(yil + 1, 1, 1)


def yas_hesap(dogum, yil, takvim_yili=False, bugun=None):
    """Oyuncunun yaşı (yas_tarihi'ne göre). Doğum tarihi bilinmiyorsa None."""
    if not dogum:
        return None
    y, a, g = (int(x) for x in dogum.split('-'))
    if y < 1900:  # kaynağın "bilinmiyor" yer tutucusu (0001-01-01)
        return None
    t = yas_tarihi(yil, takvim_yili, bugun)
    return t.year - y - (1 if (t.month, t.day) < (a, g) else 0)


def yas_metni(yas, yil):
    """Kartlarda gösterilen yaş: süren sezonda '24 yaş', geçmiş sezonda '25 yaş (sezon ortasında)'."""
    if yas is None:
        return ''
    return f'{yas} yaş' + ('' if yil >= SON_SEZON else ' (sezon ortasında)')


def mevki_adi(p):
    """Ayrıntılı mevki biliniyorsa onun adı, yoksa ana mevki."""
    d = p.get('detay')
    return DETAY[d][1] if d in DETAY and DETAY[d][0] == p['pos'] else POS.get(p['pos'], p['pos'])
OZELLIKLER = ['Elo farkı', 'Ev Elo', 'Dep. Elo', 'Ev hücum', 'Ev savunma', 'Dep. hücum',
              'Dep. savunma', 'Ev form', 'Dep. form']
# kaynağa özgü ek istatistikler: t = toplam (90 dk'ya çevrilebilir), r = oran ya da ortalama
EK = {'npg': ('Penaltısız gol', 't'), 'npxg': ('Penaltısız xG', 't'), 'xgc': ('xG zinciri (xGChain)', 't'),
      'xgb': ('xG hazırlık (xGBuildup)', 't'), 'rt': ('FotMob puanı', 'r'), 'xgot': ('İsabetli şut xG (xGOT)', 't'),
      'bcc': ('Yaratılan net pozisyon', 't'), 'bcm': ('Kaçan net pozisyon', 't'),
      'drb': ('Başarılı çalım (90 dk)', 'r'), 'drbp': ('Çalım başarısı %', 'r'),
      'pas': ('İsabetli pas (90 dk)', 'r'), 'pasp': ('Pas isabeti %', 'r'), 'tkl': ('Top çalma', 't'),
      'int': ('Pas arası', 't'), 'clr': ('Uzaklaştırma', 't'), 'rec': ('Top kazanma', 't'),
      'sav': ('Kurtarış', 't'), 'savp': ('Kurtarış %', 'r'), 'gc': ('Yenen gol', 't'),
      'cs': ('Gol yemeden maç', 't'), 'gp': ('Önlenen gol', 'r')}
KALECI_EK = {'sav', 'savp', 'gc', 'cs', 'gp'}
YUZDELIK = {
    'understat': {'out': [('g', 'Gol'), ('xg', 'xG'), ('npxg', 'Penaltısız xG'), ('a', 'Asist'), ('xa', 'xA'),
                          ('sh', 'Şut'), ('kp', 'Kilit pas'), ('xgc', 'xG zinciri'), ('xgb', 'xG hazırlık')],
                  # kaleciler: FotMob'la eşleşen ek istatistikler (Understat kaleci istatistiği tutmaz)
                  'gk': [('sav', 'Kurtarış'), ('savp', 'Kurtarış %'), ('gp', 'Önlenen gol'), ('pas', 'İsabetli pas')]},
    'fotmob': {'out': [('g', 'Gol'), ('xg', 'xG'), ('a', 'Asist'), ('xa', 'xA'), ('sh', 'Şut'), ('kp', 'Kilit pas'),
                       ('drb', 'Başarılı çalım'), ('pas', 'İsabetli pas'), ('tkl', 'Top çalma'),
                       ('int', 'Pas arası'), ('rec', 'Top kazanma')],
               'gk': [('sav', 'Kurtarış'), ('savp', 'Kurtarış %'), ('gp', 'Önlenen gol'), ('pas', 'İsabetli pas')]},
}


def lig(anahtar):
    for l in LIGLER:
        if l[0] == anahtar:
            return l
    raise KeyError(f'Bilinmeyen lig: {anahtar}. Seçenekler: ' + ', '.join(l[0] for l in LIGLER))


def sezon_etiketi(y, anahtar=None):
    return str(y) if anahtar in TAKVIM_YILI else f'{y}/{(y + 1) % 100:02d}'


def sadelestir(s):
    """Arama için: küçük harf, Türkçe ı → i, aksanlar atılır."""
    s = s.lower().replace('ı', 'i').replace('İ', 'i')
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def ham_oku(veri_klasoru, anahtar, yil):
    yol = Path(veri_klasoru) / f'{anahtar}-{yil}.json'
    if not yol.exists():
        raise FileNotFoundError(f'{yol} yok. Önce "python -m mac_tahmin veri" ile veriyi indir.')
    return json.loads(yol.read_text(encoding='utf-8'))


def metrik(p, k):
    """Oyuncunun bir istatistiği 90 dk başına (ek istatistiklerde oran olanlar olduğu gibi)."""
    if k in EK and k not in p:
        v = p['ex'].get(k)
        if v is None:
            return None
        return v / p['min'] * 90 if EK[k][1] == 't' else v
    return None if p[k] is None else p[k] / p['min'] * 90


def konum_ayikla(s):
    """Kaynaktaki mevki yazısını ayrıştırır. Understat oynanan bütün mevkileri sabit sırayla yazar ("D M S");
    tek saha mevkisi varsa o alınır, birden çoksa ya da hiç yoksa (yalnızca "S") ana mevki konum_tahmin ile
    istatistiklerden seçilir. FotMob tek harf verir (D, M, F, G, U)."""
    tok = str(s).split(' ')
    ad = [t for t in tok if t in SAHA]
    if len(ad) == 1:
        return ad[0], ad
    if not ad and ('GK' in tok or 'G' in tok):
        return 'G', ad
    return ('S' if ad else 'U' if 'U' in tok else 'S'), ad


def oyuncular(raw):
    xk = [x[0] for x in raw.get('x') or []]
    out = []
    for a in raw['p']:
        if not a[1]:  # takımı ligde olmayan kayıt (ör. FotMob listelerine karışan kadın takımı oyuncuları)
            continue
        idx = len(out)
        ex = {k: (a[13][i] if len(a) > 13 and a[13] else None) for i, k in enumerate(xk)}
        pos, adaylar = konum_ayikla(a[2])
        out.append({'idx': idx, 'n': a[0], 't': a[1], 'pos': pos, 'adaylar': adaylar, 'mp': a[3], 'min': a[4], 'g': a[5],
                    'xg': a[6], 'a': a[7], 'xa': a[8], 'sh': a[9], 'kp': a[10], 'yc': a[11], 'rc': a[12],
                    'ex': ex, 'id': a[14] if len(a) > 14 else None, 'cc': (a[15] if len(a) > 15 else None) or '',
                    'detay': a[16] if len(a) > 16 else None, 'dogum': a[17] if len(a) > 17 else None,
                    # süren sezonda takımından ayrıldıysa [yeni kulüp, tarih]
                    'ayrildi': a[18] if len(a) > 18 else None,
                    # FotMob oyuncu id: FotMob kaynaklı liglerde id'nin kendisi, Understat liglerinde eşleşen kayıt
                    'fm_id': a[19] if len(a) > 19 else (a[14] if raw.get('src') == 'fotmob' and len(a) > 14 else None)})
    return out


# ---------------------------------------------------------------- çok sezonlu eğitim
GECMIS = 3            # modele eklenen önceki sezon sayısı
# Maç tahmini ayarları. Değerler tahmin karnesiyle aynı düzende (her hafta yalnızca önceki maçlarla) 2025 sezonunda
# seçildi, 2026'da doğrulandı (18 lig, ~7.500 maç): log-loss 1,0072 → ~1,003; kadro değeri süren sezonda ayrıca ~0,006.
YARI_OMUR = 540       # Poisson'da maç ağırlığının yarıya indiği gün sayısı
XG_PAYI = 0.25        # takım güçleri hesaplanırken maç golüne karışan xG payı
DC_RHO = -0.05        # Dixon-Coles düzeltmesi (düşük skorlu beraberlikler)
ELO_PAYI = 0.35       # sonuç olasılıklarında Poisson ile maç maç güncellenen Elo'nun harmanı
ELO_EV = 60           # Elo'da ev sahibi avantajı (sezon_gecisi ile aynı)
DEGER_US = 0.1        # süren sezonda beklenen goller kadro değeri oranına göre eğilir: × (ev değeri / dep değeri)^üs
DEGER_TAVAN = 1.2     # …en fazla %20 (değer uçurumu olan liglerde beklenen gol abartılmasın; kazancın çoğu korunuyor)
ON_BILGI_MAC = 4      # önceki sezon hücum/savunma bilgisinin kaç maç yerine geçtiği
ELO_KORU = 0.9        # sezon arasında Elo'nun ortalamadan uzaklığının korunan kısmı (karneyle: 2/3'ten 0,9'a çıkınca
#                       log-kayıp 2025'te 1,0015 → 1,0010, 2026'da 1,0099 → 1,0085; güçler yazdan yaza sanılandan kalıcı)
ELO_YENI = 1450       # ligde yeni olan (yükselen) takımların başlangıç Elo'su
XG_OZELLIKLER = ['Ev xG hücum', 'Ev xG savunma', 'Dep. xG hücum', 'Dep. xG savunma']


def gun_no(d):
    return date.fromisoformat(d).toordinal()


def maclar(raw):
    return [Mac(r[0], r[1], r[2], r[3], r[4], r[5] or 0, r[6] or 0) for r in raw['m']]


def sezon_gecisi(raw, onceki):
    """Bir sezonu baştan sona oynatır: her maç için maç öncesi özellikler (X), sonuç (Y) ve Elo beklentisi.
    onceki: önceki sezondan takım adı -> {elo, atk, def, xatk, xdef}; None ise herkes nötr başlar."""
    T, K, HFA = raw['t'], 20, 60
    n = len(T)
    M = maclar(raw)
    pr = [(onceki or {}).get(t) if onceki is not None else None for t in T]
    elo = [p['elo'] if p else (ELO_YENI if onceki is not None else 1500) for p in pr]
    elo_bas = list(elo)
    hist = [[] for _ in T]
    pa = [p['atk'] if p else (0.85 if onceki is not None else 1) for p in pr]
    pd = [p['def'] if p else (1.15 if onceki is not None else 1) for p in pr]
    pxa = [p['xatk'] if p and p['xatk'] is not None else (0.85 if onceki is not None else 1) for p in pr]
    pxd = [p['xdef'] if p and p['xdef'] is not None else (1.15 if onceki is not None else 1) for p in pr]
    pk = ON_BILGI_MAC if onceki is not None else 0
    gf, ga, xf, xa, gp = [0] * n, [0] * n, [0] * n, [0] * n, [0] * n
    son = [[] for _ in T]
    xg_var = any(m.hx > 0 or m.ax > 0 for m in M)

    def rel(s, g, prv, avg):
        # o güne kadarki maç başına değerin lig ortalamasına oranı; önceki sezon bilgisi pk maç ağırlığında karışır
        return (((s / avg) if g else 0) + pk * prv) / (g + pk) if (g + pk) else 1

    totG = totX = totTG = 0
    X, Y, eloE = [], [], []
    for m in M:
        avg = totG / totTG if totG else 1.35
        xavg = totX / totTG if totTG and totX else avg
        form = lambda i: ortalama(son[i]) if son[i] else 1.3
        satir = [elo[m.h] - elo[m.a], elo[m.h], elo[m.a], rel(gf[m.h], gp[m.h], pa[m.h], avg),
                 rel(ga[m.h], gp[m.h], pd[m.h], avg), rel(gf[m.a], gp[m.a], pa[m.a], avg),
                 rel(ga[m.a], gp[m.a], pd[m.a], avg), form(m.h), form(m.a)]
        if xg_var:
            satir += [rel(xf[m.h], gp[m.h], pxa[m.h], xavg), rel(xa[m.h], gp[m.h], pxd[m.h], xavg),
                      rel(xf[m.a], gp[m.a], pxa[m.a], xavg), rel(xa[m.a], gp[m.a], pxd[m.a], xavg)]
        X.append(satir)
        res = 0 if m.hg > m.ag else 1 if m.hg == m.ag else 2
        Y.append(res)
        E = 1 / (1 + math.pow(10, -(elo[m.h] + HFA - elo[m.a]) / 400))
        eloE.append(E)
        gd = abs(m.hg - m.ag)
        k = K * (1 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8)
        dl = k * ((1 if res == 0 else .5 if res == 1 else 0) - E)
        elo[m.h] += dl
        elo[m.a] -= dl
        hist[m.h].append(elo[m.h])
        hist[m.a].append(elo[m.a])
        gf[m.h] += m.hg; ga[m.h] += m.ag; gf[m.a] += m.ag; ga[m.a] += m.hg
        gp[m.h] += 1; gp[m.a] += 1
        xf[m.h] += m.hx; xa[m.h] += m.ax; xf[m.a] += m.ax; xa[m.a] += m.hx
        son[m.h].append(3 if res == 0 else 1 if res == 1 else 0)
        son[m.a].append(3 if res == 2 else 1 if res == 1 else 0)
        if len(son[m.h]) > 5: son[m.h].pop(0)
        if len(son[m.a]) > 5: son[m.a].pop(0)
        totG += m.hg + m.ag
        totX += m.hx + m.ax
        totTG += 2
    avg = totG / totTG if totG else 1
    xavg = totX / totTG if totTG and totX else avg
    sonraki = {t: {'elo': 1500 + (elo[i] - 1500) * ELO_KORU, 'atk': gf[i] / gp[i] / avg, 'def': ga[i] / gp[i] / avg,
                   'xatk': xf[i] / gp[i] / xavg if xg_var else None, 'xdef': xa[i] / gp[i] / xavg if xg_var else None}
               for i, t in enumerate(T) if gp[i]}
    return {'T': T, 'M': M, 'X': X, 'Y': Y, 'eloE': eloE, 'elo': elo, 'elo_bas': elo_bas, 'hist': hist,
            'son': son, 'xg': xg_var, 'sonraki': sonraki}


def mac_esle(gecis, T):
    """Önceki bir sezonun maçlarını bu sezonun takım numaralarına çevirir; bu sezonda olmayanların maçları atılır."""
    ix = {t: i for i, t in enumerate(T)}
    out = []
    for m in gecis['M']:
        h, a = ix.get(gecis['T'][m.h]), ix.get(gecis['T'][m.a])
        if h is not None and a is not None:
            out.append(Mac(m.d, h, a, m.hg, m.ag, m.hx, m.ax))
    return out


def zaman_agirligi(M, ref):
    return [math.pow(0.5, max(0, ref - gun_no(m.d)) / YARI_OMUR) for m in M]


def yeni_takimlar(gecmis_M, n, n_onceki):
    if not n_onceki:
        return None
    var = [False] * n
    for m in gecmis_M:
        var[m.h] = var[m.a] = True
    return [not v for v in var]


# ---- karşılaştırılan modeller. Her model bir işlevdir: eğitim bağlamını (c) alır, her test maçı için
# [ev, beraberlik, deplasman] olasılıklarını döner. Bağlamdaki alanlar:
#   Xtr, Ytr, Etr: eğitim özellikleri (OZELLIKLER sırasıyla), sonuçlar (0 ev, 1 beraberlik, 2 deplasman), Elo beklentisi
#   Xte, Ete, Mte: test özellikleri, Elo beklentisi, maçlar (Mac)    Ztr, Zte: standartlaştırılmış özellikler
#   pz: eğitim maçlarıyla kurulmuş Poisson modeli                   freq: eğitimdeki sonuç oranları
# Yeni model: bir işlev yaz ve MODEL_LISTESI'ne ekle; Modeller sekmesi ve degerlendir komutu kendiliğinden gösterir.

def _referans(c):
    return [c['freq'] for _ in c['Xte']]


def _elo(c):
    k = c['freq'][1] / ortalama(4 * E * (1 - E) for E in c['Etr'])  # beraberlik payı, Elo farkı küçüldükçe artar

    def p(E):
        d = k * 4 * E * (1 - E)
        q = [max(E - d / 2, 0.02), d, max(1 - E - d / 2, 0.02)]
        s = q[0] + q[1] + q[2]
        return [v / s for v in q]
    return [p(E) for E in c['Ete']]


def _lojistik(c):
    W = lojistik_kur(c['Ztr'], c['Ytr'])
    c['lrP'] = [softmax(W, z) for z in c['Zte']]
    return c['lrP']


def _orman(c):
    rf = Orman(c['Xtr'], c['Ytr'])
    c['onem'] = rf.onem
    return [rf.tahmin(x) for x in c['Xte']]


def _poisson(c):
    return [sonuc_olasiliklari(*c['pz'].lambdalar(m.h, m.a))[0] for m in c['Mte']]


MODEL_LISTESI = [('Referans: sezon ortalaması', _referans), ('Saf Elo', _elo), ('Lojistik Regresyon', _lojistik),
                 ('Random Forest', _orman), ('Poisson (hücum/savunma)', _poisson)]
MODELLER = [ad for ad, _ in MODEL_LISTESI]


def egit_ve_test(Xtr, Ytr, Etr, Xte, Ete, pz, Mte, Yte):
    """MODEL_LISTESI'ndeki modelleri eğitip aynı test maçlarında puanlar."""
    F = len(Xtr[0])
    mu, sd = [], []
    for f in range(F):
        col = [x[f] for x in Xtr]
        m = ortalama(col)
        mu.append(m)
        v = math.sqrt(ortalama((x - m) * (x - m) for x in col))
        sd.append(v if v and not math.isnan(v) else 1)
    z = lambda x: [(v - mu[f]) / sd[f] for f, v in enumerate(x)]
    c = {'Xtr': Xtr, 'Ytr': Ytr, 'Etr': Etr, 'Xte': Xte, 'Ete': Ete, 'Mte': Mte, 'pz': pz,
         'Ztr': [z(x) for x in Xtr], 'Zte': [z(x) for x in Xte],
         'freq': [sum(1 for y in Ytr if y == k) / len(Ytr) for k in range(3)]}
    P = [fn(c) for _, fn in MODEL_LISTESI]
    return {'skorlar': [skorla(p, Yte) for p in P], 'lrP': c.get('lrP') or P[0], 'onem': c.get('onem') or []}


class Sezon:
    def __init__(self, raw, anahtar=None, yil=None, onceki=None):
        """onceki: önceki sezonların ham verisi, eskiden yeniye (çok sezonlu eğitim için)."""
        self.lig, self.yil = anahtar, yil
        self.src = raw.get('src') or 'understat'
        self.skip = raw.get('skip') or 0
        T = self.T = raw['t']
        n = len(T)
        self._gecisler, on = [], None
        for r in onceki or []:
            g = sezon_gecisi(r, on)
            self._gecisler.append(g)
            on = g['sonraki']
        cur = self._cur = sezon_gecisi(raw, on)
        self._fresh = sezon_gecisi(raw, None) if self._gecisler else cur
        M = self.M = cur['M']
        self.U = [Mac(r[0], r[1], r[2], 0, 0) for r in raw['u']]
        tb = self.tb = [dict(i=i, name=nm, O=0, G=0, B=0, M=0, AG=0, YG=0, P=0, xG=0, xGA=0)
                        for i, nm in enumerate(T)]
        for m in M:
            H, A = tb[m.h], tb[m.a]
            H['O'] += 1; A['O'] += 1
            H['AG'] += m.hg; H['YG'] += m.ag; A['AG'] += m.ag; A['YG'] += m.hg
            H['xG'] += m.hx; H['xGA'] += m.ax; A['xG'] += m.ax; A['xGA'] += m.hx
            if m.hg > m.ag:
                H['G'] += 1; H['P'] += 3; A['M'] += 1
            elif m.hg < m.ag:
                A['G'] += 1; A['P'] += 3; H['M'] += 1
            else:
                H['B'] += 1; A['B'] += 1; H['P'] += 1; A['P'] += 1
        for i, v in enumerate(raw.get('tx') or []):
            if v and i < n:
                tb[i]['xG'], tb[i]['xGA'] = v[0], v[1]
        for r in tb:
            r['AV'] = r['AG'] - r['YG']
        totG, totTG = sum(r['AG'] for r in tb), sum(r['O'] for r in tb)
        lg_avg = totG / totTG if totG else 1
        self.elo, self.hist, self.elo_bas = cur['elo'], cur['hist'], cur['elo_bas']
        self.xg_var = any(r['xG'] > 0 for r in tb)
        self.tablo = tablo_sirala(tb, M, esitlik_kurali(anahtar))
        self.reyting = sorted(
            [dict(i=r['i'], name=r['name'], elo=self.elo[r['i']],
                  hucum=r['AG'] / r['O'] / lg_avg if r['O'] else 1,
                  savunma=r['YG'] / r['O'] / lg_avg if r['O'] else 1) for r in tb],
            key=lambda r: -r['elo'])
        # tahmin ve simülasyon için Poisson: önceki sezonlar dahil, eski maçların ağırlığı zamanla azalır
        gecmis_M = [m for g in self._gecisler for m in mac_esle(g, T)]
        tum_M = gecmis_M + M
        ref = gun_no(M[-1].d) if M else (gun_no(tum_M[-1].d) if tum_M else 0)
        self.n_onceki, self.n_gecmis_mac = len(self._gecisler), len(gecmis_M)
        self.poisson = poisson_kur(tum_M, n, zaman_agirligi(tum_M, ref), yeni_takimlar(gecmis_M, n, len(self._gecisler)),
                                   XG_PAYI)
        # Elo modelinin beraberlik oranı (önceki sezonlar ve bu sezon); kadro değerleri sonradan atanır (deger_ata)
        self._ber_orani = (sum(1 for m in tum_M if m.hg == m.ag) / len(tum_M)) if tum_M else 0.26
        self.kadro_degeri = None
        self.PLY = oyuncular(raw)
        for p in self.PLY:
            p['yas'] = yas_hesap(p['dogum'], yil, anahtar in TAKVIM_YILI)
        # dakika eşikleri sezonun ilerlemesine göre ölçeklenir (sezon sonunda 900 dk): sezon uzunluğu ligin kendi toplam maçı
        # (oynanan + kalan fikstür), 34 ya da 30 maçlık ligde de bitince tam eşiğe ulaşılır
        ort_mac = ortalama(r['O'] for r in tb)
        sezon_mac = max(ort_mac, (len(M) + len(self.U)) * 2 / n)
        self.min_esik = max(90, js_round(900 * ort_mac / sezon_mac / 10) * 10) if sezon_mac else 90
        self._ev = None
        konum_tahmin(self.PLY, self.src, rol_esik(self.min_esik))
        self.roller = rol_hesapla(self)
        self.ozel = ozel_roller(self)  # kural tabanlı özel roller (Komple hücumcu, Pas ustası…); p['ozel']

    # ------------------------------------------------------------ takım ve maç

    def takim_bul(self, ad):
        q = sadelestir(ad)
        tam = [i for i, t in enumerate(self.T) if sadelestir(t) == q]
        if tam:
            return tam[0]
        adaylar = [i for i, t in enumerate(self.T) if q in sadelestir(t)]
        if len(adaylar) == 1:
            return adaylar[0]
        secenek = ', '.join(self.T[i] for i in adaylar) if adaylar else ', '.join(sorted(self.T))
        raise ValueError(f'"{ad}" için takım bulunamadı ya da birden çok eşleşme var: {secenek}')

    def deger_ata(self, degerler):
        """Kadro değerleri ({takım adı: €}); bilinmeyen takım ligin ortanca değerini alır. Simülasyon yeniden hesaplanır."""
        var = [v for v in degerler.values() if v]
        if len(var) < len(self.T) // 2:
            return
        orta = sorted(var)[len(var) // 2]
        self.kadro_degeri = [degerler.get(t) or orta for t in self.T]
        self.sim = None

    def lambdalar(self, h, a):
        """Beklenen goller: Poisson modeli; kadro değerleri biliniyorsa (süren sezon) değer oranına göre hafifçe eğilir."""
        lh, la = self.poisson.lambdalar(h, a)
        if self.kadro_degeri:
            oran = (self.kadro_degeri[h] / self.kadro_degeri[a]) ** DEGER_US
            oran = min(DEGER_TAVAN, max(1 / DEGER_TAVAN, oran))
            lh, la = lh * oran, la / oran
        return lh, la

    def elo_olasilik(self, h, a):
        """Saf Elo'dan [ev, beraberlik, deplasman]: beraberlik, güçler yakınken en yüksek (ligin beraberlik oranıyla)."""
        E = 1 / (1 + math.pow(10, -(self.elo[h] + ELO_EV - self.elo[a]) / 400))
        pd = min(0.4, self._ber_orani / 0.95 * 4 * E * (1 - E))
        p = [max(0.02, E - pd / 2), pd, max(0.02, 1 - E - pd / 2)]
        s = sum(p)
        return [x / s for x in p]

    def olasilik(self, h, a):
        """Yalnızca sonuç olasılıkları [ev, beraberlik, deplasman] (tahmin()'in hafif hâli: skor tablosu ve golcüler yok;
        çok maçlık hesaplar için, ör. fikstür zorluğu)."""
        lh, la = self.lambdalar(h, a)
        pp, _ = sonuc_olasiliklari(lh, la, DC_RHO)
        pe = self.elo_olasilik(h, a)
        return [(1 - ELO_PAYI) * pp[k] + ELO_PAYI * pe[k] for k in range(3)]

    def tahmin(self, h, a):
        """Maç tahmini: Poisson (kadro değeriyle, Dixon-Coles düzeltmeli) ve Elo harmanı. Skor tablosu, sonuç olasılıklarıyla
        tutarlı olsun diye her bölgesi (ev kazanır / beraberlik / deplasman kazanır) harmana göre ölçeklenir."""
        lh, la = self.lambdalar(h, a)
        pp, hucreler = sonuc_olasiliklari(lh, la, DC_RHO)
        pe = self.elo_olasilik(h, a)
        p = [(1 - ELO_PAYI) * pp[k] + ELO_PAYI * pe[k] for k in range(3)]
        carpan = [p[k] / pp[k] if pp[k] > 0 else 1 for k in range(3)]
        hucreler = [(i, j, q * carpan[0 if i > j else 1 if i == j else 2]) for i, j, q in hucreler]
        en_olasi = sorted(hucreler, key=lambda c: -c[2])[:5]
        return {'lh': lh, 'la': la, 'p': p, 'skorlar': en_olasi, 'hucreler': hucreler,
                'golcu_ev': self.golculer(h, lh), 'golcu_dep': self.golculer(a, la)}

    def golculer(self, takim, lam, adet=5, onceki=None):
        """90 dk oynarsa en az bir gol atma olasılığı: takımın beklenen golü, oyuncunun (önceki sezonlarla ve mevkisinin
        ortalamasıyla harmanlanmış) gol + xG oranına göre dağıtılır (oyuncu_tahmin.mac_olasiliklari). onceki:
        oyuncu_tahmin.onceki_sezonlar() sonucu. adet=None: bütün adaylar (arayüz güncel kadroya göre süzer)."""
        from .oyuncu_tahmin import mac_olasiliklari
        return mac_olasiliklari(self, takim, lam, 'gol', onceki, adet)

    # ------------------------------------------------------------ model karşılaştırması

    def degerlendir(self):
        """Aynı test maçlarında (bu sezonun son %30'u) iki eğitim biçimini karşılaştırır: tek sezon = yalnızca
        bu sezonun ilk %70'i; önceki sezonlarla = buna önceki sezonlar, taşınan Elo ve takım güçleri.
        120 maçtan az oynanmışsa None."""
        if self._ev is not None or len(self.M) < 120:
            return self._ev
        cur, fresh, gecisler, T, n = self._cur, self._fresh, self._gecisler, self.T, len(self.T)
        M = cur['M']
        N = len(M)
        nTr = math.floor(N * 0.7)
        Yte, Mte = cur['Y'][nTr:], M[nTr:]
        temel = lambda x: x[:len(OZELLIKLER)]
        tek = egit_ve_test([temel(x) for x in fresh['X'][:nTr]], fresh['Y'][:nTr], fresh['eloE'][:nTr],
                           [temel(x) for x in fresh['X'][nTr:]], fresh['eloE'][nTr:], poisson_kur(M[:nTr], n, xg_pay=XG_PAYI),
                           Mte, Yte)
        cok, ozellikler, n_gecmis = None, OZELLIKLER, 0
        if gecisler:
            # xG özellikleri yalnızca bütün eğitim sezonlarında maç xG'si varsa kullanılır
            xg = cur['xg'] and all(g['xg'] for g in gecisler)
            sec = (lambda x: x) if xg else temel
            ozellikler = OZELLIKLER + XG_OZELLIKLER if xg else OZELLIKLER
            Xtr = [sec(x) for g in gecisler for x in g['X']] + [sec(x) for x in cur['X'][:nTr]]
            Ytr = [y for g in gecisler for y in g['Y']] + cur['Y'][:nTr]
            Etr = [e for g in gecisler for e in g['eloE']] + cur['eloE'][:nTr]
            n_gecmis = len(Ytr) - nTr
            gecmis_M = [m for g in gecisler for m in mac_esle(g, T)]
            pm = gecmis_M + M[:nTr]
            pz = poisson_kur(pm, n, zaman_agirligi(pm, gun_no(M[nTr - 1].d)), yeni_takimlar(gecmis_M, n, len(gecisler)),
                             XG_PAYI)
            cok = egit_ve_test(Xtr, Ytr, Etr, [sec(x) for x in cur['X'][nTr:]], cur['eloE'][nTr:], pz, Mte, Yte)
        ana = cok or tek
        self._ev = {
            'n_egitim': nTr, 'n_test': N - nTr, 'n_onceki': len(gecisler), 'n_gecmis': n_gecmis,
            'xg': len(ozellikler) > len(OZELLIKLER),
            'sonuclar': [{'model': ad, 'tek': tek['skorlar'][i], 'cok': cok['skorlar'][i] if cok else None}
                         for i, ad in enumerate(MODELLER)],
            'onem': sorted(({'f': f, 'v': ana['onem'][i]} for i, f in enumerate(ozellikler)), key=lambda o: -o['v']),
            'test': [{'mac': m, 'ev': T[m.h], 'dep': T[m.a], 'sonuc': Yte[i], 'p': ana['lrP'][i]}
                     for i, m in enumerate(Mte)],
        }
        return self._ev

    # ------------------------------------------------------------ sezon simülasyonu

    def simulasyon(self, N=10000, sabit=None):
        """Kalan maçları Poisson modeliyle N kez oynatır; eşit puanda ligin kuralı (ESITLIK_KURALI: averaj, ikili maç ya da
        galibiyet sayısı), sonra atılan gol, sonra kura. İkili maç kuralında puanı eşit takımların birbirleriyle oynadığı
        maçlardan mini tablo (puan, averaj) hesaplanır; simülasyon başına kısmi eşitlikte yeniden bölünmez. Takım başına
        beklenen puan ve sıra dağılımı döner. Bütün simülasyonlar numpy ile birlikte oynatılır; sabit tohum sayesinde sonuç
        her çalıştırmada aynıdır. sabit: {(ev, dep): (ev golü, dep golü)} — "ya şöyle olursa": bu maçlar her simülasyonda
        bu skorla biter; diğer maçlar aynı rastgele sayılarla oynatıldığından fark yalnızca sabitlenen sonuçlardan gelir."""
        import numpy as np
        n, U = len(self.T), self.U
        kural = esitlik_kurali(self.lig)
        R = np.random.default_rng(2026)
        pts = np.tile(np.array([r['P'] for r in self.tb], dtype=np.int64), (N, 1))
        gd = np.tile(np.array([r['AV'] for r in self.tb], dtype=np.int64), (N, 1))
        gf = np.tile(np.array([r['AG'] for r in self.tb], dtype=np.int64), (N, 1))
        gal = np.tile(np.array([r['G'] for r in self.tb], dtype=np.int64), (N, 1))
        if kural == 'ikili':  # ik_p[i, j]: i takımının j'ye karşı puanı (ik_g: averajı); oynanmış maçlar, sonra simülasyonlar
            ik_p, ik_g = np.zeros((n, n), dtype=np.int32), np.zeros((n, n), dtype=np.int32)
            for m in self.M:
                ik_p[m.h, m.a] += 3 if m.hg > m.ag else 1 if m.hg == m.ag else 0
                ik_p[m.a, m.h] += 3 if m.ag > m.hg else 1 if m.hg == m.ag else 0
                ik_g[m.h, m.a] += m.hg - m.ag
                ik_g[m.a, m.h] += m.ag - m.hg
            ik_p, ik_g = np.tile(ik_p, (N, 1, 1)), np.tile(ik_g, (N, 1, 1))
        if U:
            lam = np.array([self.lambdalar(m.h, m.a) for m in U])  # (maç, 2)
            goller = R.poisson(lam, size=(N, len(U), 2))
            hg, ag = goller[:, :, 0], goller[:, :, 1]
            for j, m in enumerate(U):
                if sabit and (m.h, m.a) in sabit:
                    hg[:, j], ag[:, j] = sabit[(m.h, m.a)]
            ev = np.array([m.h for m in U])
            dep = np.array([m.a for m in U])
            ev_p = np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
            dep_p = np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
            for j in range(len(U)):  # aynı takımın birden çok maçı olduğundan maç maç toplanır
                pts[:, ev[j]] += ev_p[:, j]; pts[:, dep[j]] += dep_p[:, j]
                gf[:, ev[j]] += hg[:, j]; gf[:, dep[j]] += ag[:, j]
                gd[:, ev[j]] += hg[:, j] - ag[:, j]; gd[:, dep[j]] += ag[:, j] - hg[:, j]
                gal[:, ev[j]] += hg[:, j] > ag[:, j]; gal[:, dep[j]] += ag[:, j] > hg[:, j]
                if kural == 'ikili':
                    ik_p[:, ev[j], dep[j]] += ev_p[:, j]; ik_p[:, dep[j], ev[j]] += dep_p[:, j]
                    ik_g[:, ev[j], dep[j]] += hg[:, j] - ag[:, j]; ik_g[:, dep[j], ev[j]] += ag[:, j] - hg[:, j]
        kura = R.random((N, n))
        # lexsort'ta son anahtar öncelikli; her ölçüt ayrı anahtar olduğundan büyük averaj / gol sayıları birbirini ezmez
        if kural == 'ikili':
            esit = pts[:, :, None] == pts[:, None, :]  # puanı eşit takımlar (kendisi dahil; kendine karşı maç yok)
            anahtarlar = (kura, -gf, -gd, -np.where(esit, ik_g, 0).sum(axis=2), -np.where(esit, ik_p, 0).sum(axis=2), -pts)
        elif kural == 'galibiyet':
            anahtarlar = (kura, -gf, -gd, -gal, -pts)
        else:
            anahtarlar = (kura, -gf, -gd, -pts)
        sira = np.lexsort(anahtarlar, axis=1)  # her simülasyonda 0. sıradaki takım birinci
        poz = np.zeros((n, n), dtype=np.int64)
        for p in range(n):
            poz[:, p] = np.bincount(sira[:, p], minlength=n)
        ort = pts.mean(axis=0)
        out = [{'i': i, 'name': t, 'P': self.tb[i]['P'], 'exp': float(ort[i]), 'dist': [float(c) / N for c in poz[i]]}
               for i, t in enumerate(self.T)]
        return sorted(out, key=lambda r: -r['exp'])

    # ------------------------------------------------------------ oyuncular

    def oyuncu_bul(self, ad):
        q = sadelestir(ad)
        adaylar = [p for p in self.PLY if q in sadelestir(p['n'])]
        tam = [p for p in adaylar if sadelestir(p['n']) == q]
        return tam or sorted(adaylar, key=lambda p: -p['min'])

    def rol_nedeni(self, p):
        """Oyuncunun rolü yoksa kısa nedeni ('kaleci', 'az süre', …); rolü varsa ''."""
        if p.get('rol'):
            return ''
        if p['pos'] == 'G':
            return 'kaleci'
        if not self.roller:
            return 'bu sezon hesaplanmadı'
        if p['min'] < self.roller['esik']:
            return 'az süre'
        return 'eksik veri'

    def _metrik(self, p, k):
        return metrik(p, k)

    def oyuncu_karti(self, p):
        """Web sayfasındaki oyuncu kartının verisi: özet, mevkidaşlara göre yüzdelikler, ayrıntılar."""
        gk = p['pos'] == 'G'
        takim = None if ' / ' in p['t'] else next((r for r in self.tb if r['name'] == p['t']), None)
        tanimlar = YUZDELIK[self.src]['gk' if gk else 'out']
        esler = [q for q in self.PLY if q['min'] >= self.min_esik
                 and (q['pos'] == 'G' if gk else q['pos'] != 'G')
                 and (p['pos'] in ('S', 'U') or gk or q['pos'] == p['pos'])]
        yuzdelik = []
        for k, etiket in tanimlar:
            v = self._metrik(p, k)
            if v is None:
                continue
            vals = [x for x in (self._metrik(q, k) for q in esler) if x is not None]
            if len(vals) < 5:
                continue
            alt = sum(1 for x in vals if x < v)
            esit = sum(1 for x in vals if x == v)
            yuzdelik.append((etiket, v, js_round((alt + esit / 2) / len(vals) * 100)))
        detay = [('Gol − xG', float(p['g'] - p['xg']))]
        if p['g'] + p['a'] > 0:
            detay.append(('Gol katkısı sıklığı (dk)', js_round(p['min'] / (p['g'] + p['a']))))
        if takim and takim['AG']:
            detay.append(('Takım gollerindeki payı', p['g'] / takim['AG']))
        if p['sh']:
            detay.append(('Şut başına gol', p['g'] / p['sh']))
        detay += [('Şut', p['sh']), ('Kilit pas', p['kp']), ('Sarı kart', p['yc']), ('Kırmızı kart', p['rc'])]
        for k, v in p['ex'].items():
            if v is not None and k != 'rt' and k in EK and not (not gk and k in KALECI_EK):
                detay.append((EK[k][0], v))
        return {'oyuncu': p, 'puan': p['ex'].get('rt'), 'yuzdelik': yuzdelik, 'es_sayisi': len(esler),
                'detay': detay, 'az_sure': p['min'] < self.min_esik}


# ---------------------------------------------------------------- oyuncu rolleri (k-means kümeleme)
# Saha oyuncularının 90 dk başına profilleri standartlaştırılıp k kümeye ayrılır; her küme, merkezinin profiline
# en çok uyan rolün adını alır (w: rol şablonu; + o istatistik yüksek, - düşük; son alan rolün izin verdiği
# mevkiler: F forvet, W kanat, M orta saha, D defans). Mevkisine uymayan bir role düşen oyuncu, mevkisine uygun en yakın
# role taşınır.
ROL = {
    'understat': {'feats': [('npxg', 'Penaltısız xG'), ('xa', 'xA'), ('sh', 'Şut'), ('kp', 'Kilit pas'),
                            ('xgc', 'xG zinciri'), ('xgb', 'xG hazırlık')], 'roller': [
        ('Bitirici forvet', 'Ceza sahasında bitirici: çok şut ve yüksek xG, oyun kurulumuna katkısı az.', [2, 0, 1.5, 0, 0, -1], 'FWM'),
        ('Yaratıcı oyuncu', 'Pozisyon hazırlayan: asist beklentisi (xA) ve kilit pas sayısı yüksek.', [0, 2, 0, 2, 0, 0], 'FWMD'),
        ('Çok yönlü hücumcu', 'Hem gol tehdidi hem pozisyon üretimi; hücumların içinde yer alır (xG zinciri yüksek).', [1, 1, 0, 0, 2, 0], 'FWM'),
        ('Oyun kurucu', 'Hücumları geriden başlatır: xG hazırlık yüksek, kendi gol tehdidi düşük.', [-1, 0, -0.5, 0.5, 0, 2], 'MD'),
        ('Savunma ağırlıklı', 'Hücum katkısı düşük; çoğunlukla savunma oyuncuları ve savunma önü orta sahalar.',
         [-1, -1, -1, -1, -1, -0.5], 'MD')]},
    'fotmob': {'feats': [('xg', 'xG'), ('xa', 'xA'), ('sh', 'Şut'), ('kp', 'Kilit pas'), ('drb', 'Başarılı çalım'),
                         ('pas', 'İsabetli pas'), ('tkl', 'Top çalma'), ('int', 'Pas arası'), ('rec', 'Top kazanma'),
                         ('clr', 'Uzaklaştırma')], 'roller': [
        ('Bitirici forvet', 'Ceza sahasında bitirici: çok şut ve yüksek xG, pas oyununa katkısı az.', [2, 0, 2, 0, 0, -1, 0, 0, -0.5, 0], 'FWM'),
        ('Çalımcı kanat', 'Topla adam geçen, kanattan pozisyon üreten oyuncu.', [0, 1, 0, 0.5, 2, 0, 0, 0, 0, -0.5], 'WM'),
        ('Yaratıcı oyun kurucu', 'Son pası veren: asist beklentisi (xA) ve kilit pas sayısı yüksek.', [0, 2, 0, 2, 0.5, 0, 0, 0, 0, -0.5], 'FWM'),
        ('Geriden oyun kuran', 'Geride kalıp topu dolaştıran oyuncu (bek ya da savunma önü orta saha): çok pas yapar ve '
                               'top kazanır, gol tehdidi düşük.', [-1, 0, -0.5, 0, 0, 2, 0, 0.5, 1, 0], 'MD'),
        ('Top kazanan orta saha', 'Top çalma, pas arası ve top kazanmada öne çıkar.', [-0.5, 0, 0, 0, 0, 0, 2, 1, 1, 0], 'M'),
        ('Stoper', 'Uzaklaştırma ve pas arasıyla öne çıkan, hücuma az katılan savunma oyuncusu.', [-0.5, 0, -0.5, 0, -1, 0, 0, 1, 0, 2], 'D'),
        ('Hücum destekçisi', 'Hücumda yer alan ama belirgin bir uzmanlığı olmayan oyuncu; savunma katkısı düşük.',
         [0.5, 0.5, 0.5, 0.5, 0.5, -1, -0.5, -1, -0.5, -1], 'FWM')]},
}


def rol_esik(min_esik):
    return max(270, js_round(min_esik * 2 / 3 / 10) * 10)


def konum_tahmin(ply, src, esik):
    """Ana mevkisi belli olmayan oyuncular (birden çok mevkide oynamış, yalnızca 'yedek' ya da 'belirsiz'): mevki,
    90 dk başına profilin hangi mevkinin ortalamasına en yakın olduğuna bakılarak seçilir; oynadığı mevkiler
    biliniyorsa yalnızca onların arasından. Örnekler tek mevkide oynamış oyunculardır."""
    feats = ROL[src]['feats']
    tamam = lambda x: x is not None and not math.isinf(x) and not math.isnan(x)
    vec = lambda p: [metrik(p, k) for k, _ in feats]
    egitim = [(p, v) for p in ply if p['pos'] in SAHA and p['min'] >= esik for v in [vec(p)] if all(map(tamam, v))]
    if len(egitim) < 30:
        return
    F = len(feats)
    mu, sd = [], []
    for f in range(F):
        col = [e[1][f] for e in egitim]
        m = ortalama(col)
        mu.append(m)
        v = math.sqrt(ortalama((x - m) * (x - m) for x in col))
        sd.append(v if v and not math.isnan(v) else 1)
    merkez = {}
    for pos in SAHA:
        g = [e for e in egitim if e[0]['pos'] == pos]
        if len(g) >= 5:
            merkez[pos] = [ortalama((e[1][f] - mu[f]) / sd[f] for e in g) for f in range(F)]
    for p in ply:
        if p['pos'] not in ('S', 'U'):
            continue
        v = vec(p)
        dims = [f for f, x in enumerate(v) if tamam(x)]
        if not dims:
            continue
        # oynadığı mevkiler biliniyorsa onların arasından; forvet ya da orta sahada oynamış biri kanat da olabilir
        bilinen = len(p['adaylar']) >= 2
        aday = (p['adaylar'] + (['W'] if any(x in ('F', 'M') for x in p['adaylar']) else [])) if bilinen else list(SAHA)
        b, bd = None, float('inf')
        for pos, c in merkez.items():
            if pos not in aday:
                continue
            d = 0
            for f in dims:
                t = (v[f] - mu[f]) / sd[f] - c[f]
                d += t * t
            if d < bd:
                bd, b = d, pos
        if b:
            p['pos'] = b
            p['pos_tahmin'] = 'coklu' if bilinen else 'yok'


def kmeans(Z, k, tohum):
    """k-means++ başlangıçlı k-means; tohum sabit olduğundan sonuç her çalıştırmada aynıdır."""
    R = mulberry32(tohum)
    n, F = len(Z), len(Z[0])

    def d2(a, b):
        s = 0
        for f in range(F):
            t = a[f] - b[f]
            s += t * t
        return s

    C = [list(Z[math.floor(R() * n)])]
    while len(C) < k:
        D = []
        for z in Z:
            m = float('inf')
            for c in C:
                d = d2(z, c)
                if d < m:
                    m = d
            D.append(m)
        r = R() * toplam(D)
        i = 0
        while i < n - 1:
            r -= D[i]
            if r <= 0:
                break
            i += 1
        C.append(list(Z[i]))
    lab = [-1] * n
    for _ in range(100):
        degisti = False
        for i in range(n):
            b, bd = 0, float('inf')
            for c in range(k):
                d = d2(Z[i], C[c])
                if d < bd:
                    bd, b = d, c
            if lab[i] != b:
                lab[i] = b
                degisti = True
        if not degisti:
            break
        for c in range(k):
            s = [0] * F
            m = 0
            for i in range(n):
                if lab[i] == c:
                    m += 1
                    for f in range(F):
                        s[f] += Z[i][f]
            if m:
                C[c] = [v / m for v in s]
    ic = 0
    for i in range(n):
        ic += d2(Z[i], C[lab[i]])
    return C, lab, ic


# o sezon tutulmamış istatistiğin yerine geçen (istatistik, ad)
ROL_YEDEK = {'xg': ('g', 'Gol'), 'xa': ('a', 'Asist')}


def rol_hesapla(s):
    """Oyunculara 'rol' alanını yazar; rollerin özetini döner (yeterli oyuncu yoksa None)."""
    tanim = ROL[s.src]
    k = len(tanim['roller'])
    esik = rol_esik(s.min_esik)
    for p in s.PLY:
        p['rol'] = ''
    tamam = lambda x: x is not None and not math.isinf(x) and not math.isnan(x)
    oyn = [p for p in s.PLY if p['pos'] != 'G' and p['min'] >= esik]
    if len(oyn) < k * 8:
        return None
    # o sezon tutulmamış istatistikler (ör. FotMob'un eski sezonlarında xG, oyuncuların çoğunda 0) kümelemede
    # kullanılmaz: oyuncuların en az yarısında sıfırdan büyük değer olmalı. xG ve xA yoksa yerine gol ve asist geçer.
    dolu = lambda col: sum(1 for x in col if tamam(x) and x > 0) * 2 >= len(col)
    tum_feats, sutunlar = [], []
    for key, ad in tanim['feats']:
        col = [s._metrik(p, key) for p in oyn]
        if not dolu(col) and key in ROL_YEDEK:
            yedek = [s._metrik(p, ROL_YEDEK[key][0]) for p in oyn]
            if dolu(yedek):
                key, ad, col = ROL_YEDEK[key][0], ROL_YEDEK[key][1], yedek
        tum_feats.append((key, ad))
        sutunlar.append(col)
    aday = [(p, [sutunlar[f][i] for f in range(len(sutunlar))]) for i, p in enumerate(oyn)]
    kullan = [f for f in range(len(sutunlar)) if dolu(sutunlar[f])]
    # FotMob, bir istatistikte hiç değeri olmayan oyuncuyu listesine koymaz (ör. hiç çalım yapmamış stoper): en çok iki
    # istatistikte eksik olan oyuncunun eksikleri 0 sayılır; daha fazlası eksikse oyuncu rol almaz
    havuz = []
    for p, v in aday:
        if sum(1 for f in kullan if not tamam(v[f])) <= 2:
            havuz.append((p, [v[f] if tamam(v[f]) else 0 for f in kullan]))
    if len(havuz) < k * 8 or len(kullan) < 3:
        return None
    F = len(kullan)
    feats = [tum_feats[f] for f in kullan]
    roller_tanim = [(ad, ac, [w[f] for f in kullan], m) for ad, ac, w, m in tanim['roller']]
    mu, sd = [], []
    for f in range(F):
        col = [e[1][f] for e in havuz]
        m = ortalama(col)
        mu.append(m)
        v = math.sqrt(ortalama((x - m) * (x - m) for x in col))
        sd.append(v if v and not math.isnan(v) else 1)
    Z = [[(x - mu[f]) / sd[f] for f, x in enumerate(e[1])] for e in havuz]
    def puan(w, c):
        t = 0
        for f, x in enumerate(w):
            t += x * c[f]
        return t

    def d2(z, c):
        t = 0
        for f, x in enumerate(z):
            t += (x - c[f]) * (x - c[f])
        return t

    def adlandir(C, lab):
        """Kümelere rol adı verir ve mevki kısıtını uygular: (küme -> rol, yeni etiketler)."""
        ciftler = sorted(((puan(r[2], c), ci, ri) for ci, c in enumerate(C) for ri, r in enumerate(roller_tanim)),
                         key=lambda x: -x[0])  # sıralama kararlı: eşitlikte tanım sırası korunur
        k_rol, kullanildi = [-1] * k, set()
        for _, ci, ri in ciftler:
            if k_rol[ci] < 0 and ri not in kullanildi:
                k_rol[ci] = ri
                kullanildi.add(ri)
        # mevki kısıtı: oyuncu mevkisine uymayan bir rolün kümesine düştüyse, mevkisine uygun en yakın kümeye taşınır
        izinli = lambda ci, pos: pos in roller_tanim[k_rol[ci]][3]
        yeni_lab = []
        for i, ci in enumerate(lab):
            pos = havuz[i][0]['pos']
            if izinli(ci, pos):
                yeni_lab.append(ci)
                continue
            b, bd = ci, float('inf')
            for cj, c in enumerate(C):
                if izinli(cj, pos):
                    d = d2(Z[i], c)
                    if d < bd:
                        bd, b = d, cj
            yeni_lab.append(b)
        return k_rol, yeni_lab

    # 10 başlangıçtan en sıkı kümeleme; çok küçük rollü çözümler sayılmaz (mevki kısıtından sonra en küçük rol
    # oyuncuların %2'sinden, en az 5 oyuncudan az olmamalı). Uygun çözüm yoksa (sezon başı gibi) roller hesaplanmaz.
    min_boy = max(5, math.ceil(len(havuz) * 0.02))
    en = None
    for tohum in range(1, 11):
        C_, lab_, ic = kmeans(Z, k, tohum)
        k_rol_, lab_ = adlandir(C_, lab_)
        boy = [0] * k
        for c in lab_:
            boy[c] += 1
        if min(boy) >= min_boy and (en is None or ic < en[2]):
            en = (C_, lab_, ic, k_rol_)
    if en is None:
        return None
    C, lab, _, k_rol = en

    # rolün en iyileri: rolü tanımlayan (şablonda + olan) istatistiklerin ağırlıklı toplamı; şablonda + istatistik
    # yoksa (savunma ağırlıklı) en çok süre alanlar. Az oynayanlar (eşiğin 1,5 katından az) listeye girmez.
    def rol_puan(w, i):
        s_, var = 0, False
        for f, x in enumerate(w):
            if x > 0:
                s_ += x * Z[i][f]
                var = True
        return s_ if var else havuz[i][0]['min']

    roller = []
    for ri, (ad, aciklama, w, _) in enumerate(roller_tanim):
        ci = k_rol.index(ri)
        c = C[ci]
        uyeler = []
        for i, (p, _) in enumerate(havuz):
            if lab[i] == ci:
                p['rol'] = ad
                uyeler.append((rol_puan(w, i), p))
        uyeler.sort(key=lambda u: -u[0])
        cok_oynayan = [u for u in uyeler if u[1]['min'] >= esik * 1.5]
        en_iyi = [u[1] for u in (cok_oynayan if len(cok_oynayan) >= 3 else uyeler)[:3]]
        one = sorted(((f, z) for f, z in enumerate(c)), key=lambda x: -abs(x[1]))[:3]
        roller.append({'ad': ad, 'aciklama': aciklama, 'n': len(uyeler), 'en_iyi': en_iyi,
                       'sure': not any(x > 0 for x in w),
                       'one': [(feats[f][1], z > 0) for f, z in one if abs(z) >= 0.3]})
    roller.sort(key=lambda r: -r['n'])
    # yerine başka istatistik kullanılanlar: (asıl ad, kullanılan ad)
    yedek = [(ad, tum_feats[f][1]) for f, (key, ad) in enumerate(tanim['feats']) if tum_feats[f][0] != key and f in kullan]
    return {'roller': roller, 'esik': esik, 'n': len(havuz), 'yedek': yedek}


# ---------------------------------------------------------------- hak edilen puan (xPts)

FIKSTUR_SONRAKI = 5  # fikstür zorluğunda ayrıca gösterilen sıradaki maç sayısı


def fikstur_zorlugu(S):
    """Takımların kalan maçlarının zorluğu. Zorluk rakiplerin gücüdür, takımın kendi gücü karışmaz: her maçta rakibin
    Elo'su, rakip ev sahibiyse ev avantajı (ELO_EV) eklenerek, deplasmandaysa çıkarılarak. Sezon başında herkes kalan
    maçlarda hemen herkesle oynadığından bütün kalan maçların zorluğu az ayrışır; sıralama sıradaki FIKSTUR_SONRAKI maça
    göre. Döner (sıradaki maçları en zordan kolaya): [{'i', 'kalan', 'zorluk' (bütün kalan maçlarda rakiplerin ortalama
    etkin Elo'su), 'zorluk5' (sıradaki maçlarda), 'xp' (modelin kalan maçlardan beklediği puan), 'sonraki': [(rakip
    indeksi, ev mi, etkin Elo, kazanma olasılığı)]}]."""
    maclar = {i: [] for i in range(len(S.T))}
    for m in sorted(S.U, key=lambda m: m.d):
        p = S.olasilik(m.h, m.a)
        maclar[m.h].append((m.a, True, S.elo[m.a] - ELO_EV, p[0], 3 * p[0] + p[1]))
        maclar[m.a].append((m.h, False, S.elo[m.h] + ELO_EV, p[2], 3 * p[2] + p[1]))
    out = [{'i': i, 'kalan': len(ms), 'zorluk': sum(x[2] for x in ms) / len(ms), 'xp': sum(x[4] for x in ms),
            'zorluk5': sum(x[2] for x in ms[:FIKSTUR_SONRAKI]) / len(ms[:FIKSTUR_SONRAKI]),
            'sonraki': [x[:4] for x in ms[:FIKSTUR_SONRAKI]]} for i, ms in maclar.items() if ms]
    return sorted(out, key=lambda r: -r['zorluk5'])


SANS_ESIK = 3.0  # hak edilen puan: gerçek puan ile xPts arasında en az bu kadar fark "şanslı" / "şanssız" sayılır
XG_SUT_UST = 0.97  # şut şut hesapta bir şutun gol olma olasılığı en çok bu


def gol_dagilimi(toplam, sutlar=None, en_cok=10):
    """Bir takımın maçtaki gol sayısının dağılımı [P(0 gol), P(1), …]. Şutları biliniyorsa (her şutun xG'si) şut şut:
    her şut kendi olasılığıyla gol olur ya da olmaz; şutların xG'si toplam xG'ye ölçeklenir (şut haritası FotMob'un,
    toplam xG sezon verisinin kaynağından olabilir). Bilinmiyorsa toplam xG ortalamalı Poisson. Şut şut hesap daha
    doğrudur: 0,9'luk tek net pozisyon ile 0,1'lik dokuz uzak şutun toplamı aynı, gol olasılıkları farklıdır."""
    if sutlar and sum(sutlar) > 0:
        k = toplam / sum(sutlar)
        d = [1.0]
        for x in sutlar:
            q = min(XG_SUT_UST, max(0.0, x * k))
            yeni = [0.0] * (len(d) + 1)
            for i, v in enumerate(d):
                yeni[i] += v * (1 - q)
                yeni[i + 1] += v * q
            d = yeni
        return d
    if sutlar is not None and toplam < 0.05:  # şut verisi var, şut yok
        return [1.0]
    lam = max(toplam, 0.05)
    return [pmf(i, lam) for i in range(en_cok)]


def hak_edilen_puan(maclar):
    """Maçların xG'sinden hak edilen puan: her maç, iki takımın xG'sinden gol dağılımları (gol_dagilimi: şutlar
    biliniyorsa şut şut, bilinmiyorsa Poisson) ile oynatılır; xPts = 3 × kazanma + 1 × beraberlik olasılığı.
    maclar: [(ev, dep, ev golü, dep golü, ev xG, dep xG[, ev şutları, dep şutları])] (ev/dep: takım adı; şutlar: maçtaki
    şutların xG'leri ya da None). Döner: {takım: {'mac', 'P' (bu maçlardaki gerçek puan), 'xP', 'xG', 'xGA', 'AG', 'YG',
    'sut_mac' (şut şut hesaplanan maç sayısı)}}."""
    out = {}
    for m in maclar:
        ev, dep, eg, dg, ex, dx = m[:6]
        es, ds = (m[6], m[7]) if len(m) >= 8 and m[6] is not None and m[7] is not None else (None, None)
        a, b = gol_dagilimi(ex, es), gol_dagilimi(dx, ds)
        p = [0.0, 0.0, 0.0]
        for i, u in enumerate(a):
            for j, v in enumerate(b):
                p[0 if i > j else 1 if i == j else 2] += u * v
        s = sum(p) or 1
        p = [x / s for x in p]
        for t, ag, yg, x, xa, pk, pb in ((ev, eg, dg, ex, dx, p[0], p[1]), (dep, dg, eg, dx, ex, p[2], p[1])):
            r = out.setdefault(t, {'mac': 0, 'P': 0, 'xP': 0.0, 'xG': 0.0, 'xGA': 0.0, 'AG': 0, 'YG': 0, 'sut_mac': 0})
            r['mac'] += 1
            r['sut_mac'] += es is not None
            r['P'] += 3 if ag > yg else 1 if ag == yg else 0
            r['xP'] += 3 * pk + pb
            r['xG'] += x
            r['xGA'] += xa
            r['AG'] += ag
            r['YG'] += yg
    return out


# ---------------------------------------------------------------- özel roller (kümeleme rolünün üstüne, kural tabanlı)
# Bir oyuncu birden çok özel rol alabilir. Yüzdelikler: ligde rol eşiği kadar oynamış saha oyuncuları arasında, 90 dk
# başına (yalnızca F/W havuzu dendiyse forvet ve kanatlar arasında). Bir istatistik o ligde yoksa ya da oyuncuların
# yarısından azında varsa o özel rol o lig için hesaplanmaz. Yeni özel rol: listeye (ad, açıklama, koşul) ekle; koşul
# yuzde(istatistikler, havuz) ile yüzdelik, p ile oyuncunun kendisini kullanır.
def _top(*k):
    return lambda p: (lambda v: None if any(x is None for x in v) else sum(v))([metrik(p, x) for x in k])


# koşul (p, y, k): k sezonun ilerleyişi (0,15–1; sezon başında az maç oynandığından gol / asist sayısına dayanan eşikler
# k ile ölçeklenir). Eşikler lig başına (tam sezonda) yaklaşık 8–20 oyuncu çıkacak şekilde ayarlandı.
OZEL_ROLLER = [
    ('Komple hücumcu', 'Hem gol tehdidi hem pozisyon üretimi ligin en üst %15\'inde (90 dakikada xG ve xA).',
     lambda p, y, k: y('xg') >= 85 and y('xa') >= 85),
    ('Keskin nişancı', 'Beklenen golden (xG) belirgin fazla gol atan bitirici (sezon sonunda en az 4 gol; sezon başında '
     'oynanan maça göre daha az).',
     lambda p, y, k: p['g'] >= max(3, round(4 * k)) and p['xg'] and p['g'] - p['xg'] >= max(1.5, 2.0 * k, 0.3 * p['xg'])),
    ('Pas ustası', 'Son pası veren: asist beklentisi (xA) ligin en üst %8\'inde, kilit pasta en üst %12\'sinde.',
     lambda p, y, k: y('xa') >= 92 and y('kp') >= 88),
    ('Süper yedek', 'Maç başına az süre alıp 90 dakikada çok gol ve asist üreten oyuncu.',
     lambda p, y, k: p['mp'] >= max(3, round(5 * k)) and p['min'] / p['mp'] < 50 and p['g'] + p['a'] >= max(2, round(3 * k))
     and y('ga') >= 85),
    ('Çalım ustası', 'Başarılı çalımda ligin en üst %6\'sında.', lambda p, y, k: y('drb') >= 94),
    ('Pres forveti', 'Önde baskı yapan hücumcu: top çalma ve top kazanmada forvet ve kanatların en üst %15\'inde.',
     lambda p, y, k: p['pos'] in ('F', 'W') and y('pres', 'FW') >= 85),
    ('Top avcısı', 'Top çalma, pas arası ve top kazanmada ligin en üst %6\'sında.', lambda p, y, k: y('savunma') >= 94),
    ('Metronom', 'Oyunun ritmini tutan pasör: isabetli pasta ligin en üst %6\'sında.', lambda p, y, k: y('pas') >= 94),
    ('Kanat bek', 'Hücuma katılan bek: asist beklentisi (xA) ve kilit pasta defans oyuncularının en üst %15\'inde.',
     lambda p, y, k: p['pos'] == 'D' and p.get('detay') in (None, 'RB', 'LB') and y('xa', 'D') >= 85 and y('kp', 'D') >= 80),
    # orta sahalarda savunma ve hücum katkısı ters orantılı (yüzdelikler arası korelasyon ≈ −0,35): ikisinde de üst yarının
    # üstünde olmak seçicidir (lig başına ~8–11 oyuncu)
    ('Box to box', 'İki ceza sahası arasında koşan orta saha: hem savunmada (top çalma, pas arası, top kazanma) hem hücumda '
     '(xG ve xA) orta sahaların üst yarısının üstünde (ikisinde de en az 55. yüzdelik; 90 dakika başına). Orta sahada bu '
     'ikisi genelde birbirini dışlar: ikisini birden yapan az bulunur.',
     lambda p, y, k: p['pos'] == 'M' and min(y('savunma', 'M'), y('xgxa', 'M')) >= 55),
]# maç maç veriden hesaplanan özel rol (sezon verisinde yok): lig_maclari.hava_hakimleri; yalnızca süren sezonda
HAVA_HAKIMI = ('Hava hâkimi', 'Kazandığı hava topunda (90 dakikada) ligin en üst %10\'unda ve hava toplarının en az '
               '%55\'ini kazanıyor. Süren sezonun maç verisinden.')
BUYUK_MAC = ('Büyük maç oyuncusu', 'Ligin en güçlü 6 takımına (Elo) karşı 90 dakikada gol + asist üretiminde ligin en üst '
             '%10\'unda (en az 3 maç, 2 gol ya da asist). Süren sezonun maç verisinden.')
BUYUK_TAKIM_SAYISI = 6
# özel rollerdeki birleşik istatistikler (90 dk başına toplanır)
OZEL_ISTATISTIK = {'ga': _top('g', 'a'), 'pres': _top('tkl', 'rec'), 'savunma': _top('tkl', 'int', 'rec'),
                   'xgxa': _top('xg', 'xa')}


def ozel_roller(s):
    """Oyunculara 'ozel' alanını yazar (özel rol adları listesi). Döner: [{'ad', 'aciklama', 'oyuncular' (en çok
    oynayandan)}] (en az bir oyuncusu olanlar)."""
    esik = rol_esik(s.min_esik)
    for p in s.PLY:
        p['ozel'] = []
    havuz = [p for p in s.PLY if p['pos'] in SAHA and p['min'] >= esik]
    if len(havuz) < 40:
        return []
    tamam = lambda x: x is not None and not math.isinf(x) and not math.isnan(x)
    ilerleme = min(1.0, max(0.15, s.min_esik / 900))  # sezonun ilerleyişi (min_esik tam sezonda 900 dk)
    onbellek = {}

    def degerler(k, alt):
        if (k, alt) not in onbellek:
            fn = OZEL_ISTATISTIK.get(k, lambda p: metrik(p, k))
            h = [p for p in havuz if not alt or p['pos'] in alt]
            v = {p['idx']: fn(p) for p in h}  # 90 dk başına (birleşiklerde bileşenler zaten 90 dk başına)
            dolu =[x for x in v.values() if tamam(x)]
            onbellek[(k, alt)] = (v, sorted(dolu)) if len(dolu) * 2 >= len(h) and len(dolu) >= 20 else (None, None)
        return onbellek[(k, alt)]

    out = []
    for ad, aciklama, kosul in OZEL_ROLLER:
        uyeler = []
        for p in havuz:
            def y(k, alt=None, p=p):
                v, sirali = degerler(k, alt)
                if v is None or not tamam(v.get(p['idx'])):
                    raise KeyError(k)  # istatistik yok: bu özel rol bu ligde (ya da bu oyuncu için) hesaplanmaz
                x = v[p['idx']]
                alt_ = sum(1 for z in sirali if z < x)
                esit = sum(1 for z in sirali if z == x)
                return (alt_ + esit / 2) / len(sirali) * 100
            try:
                if kosul(p, y, ilerleme):
                    uyeler.append(p)
                    p['ozel'].append(ad)
            except (KeyError, TypeError, ZeroDivisionError):
                continue
        if uyeler:
            out.append({'ad': ad, 'aciklama': aciklama, 'oyuncular': sorted(uyeler, key=lambda p: -p['min'])})
    return out


BENZER_MIN_DK = 600


def benzer_esik(s):
    """Benzer oyuncu havuzuna girmek için gereken dakika: BENZER_MIN_DK, sezon başında yüzdelik eşiğinin iki katı (sabit
    600 dk ilk haftalarda havuzu bir avuç oyuncuya indirip benzerlikleri anlamsızlaştırıyordu)."""
    return min(BENZER_MIN_DK, 2 * s.min_esik)


def benzer_oyuncular(s, p, veri_klasoru, tum_ligler=False, adet=8):
    """Oyuncunun 90 dk başına profiline en çok benzeyen oyuncular (oyuncu kartındaki 'Benzer oyuncular').
    Profil, mevkidaş yüzdeliklerindeki istatistiklerin havuz ortalamasına göre standartlaştırılmış hâlidir;
    benzerlik exp(-d²/2F) (d: profiller arası mesafe, F: istatistik sayısı). tum_ligler: aynı veri kaynağındaki
    bütün liglerin aynı sezonu. Havuz: en az benzer_esik(s) dakika oynamış oyuncular. Döner: {'sonuc': [(oyuncu, lig
    anahtarı, benzerlik)], 'tanimlar', 'n', 'esik'} ya da {'kaleci': True} / {'yok': True}."""
    gk = p['pos'] == 'G'
    tanimlar = YUZDELIK[s.src]['gk' if gk else 'out']
    if len(tanimlar) < 3:
        return {'kaleci': True}

    def vektor(q):
        v = [s._metrik(q, k) for k, _ in tanimlar]
        v = [None if x is None or math.isinf(x) or math.isnan(x) else x for x in v]
        # FotMob'un istatistik listelerinde (ör. top çalma) yer almayan oyuncunun o değeri yok: en çok çeyreği eksik olabilir,
        # mesafe ortak değerlerden ölçülür (eskiden tek eksik değer oyuncuyu aramadan tümüyle çıkarıyordu)
        return None if sum(x is None for x in v) > len(v) // 4 else v

    havuz = []
    esik = benzer_esik(s)

    def ekle(ply, lig_anahtar):
        for q in ply:
            if q['min'] < esik or (q['pos'] == 'G') != gk:
                continue
            v = vektor(q)
            if v:
                havuz.append((q, lig_anahtar, v))

    if not tum_ligler:
        ekle(s.PLY, s.lig)
    else:
        for l in LIGLER:
            if l[4] != s.src or s.yil < l[3]:
                continue
            if l[0] == s.lig:
                ekle(s.PLY, s.lig)
                continue
            try:
                ply = oyuncular(ham_oku(veri_klasoru, l[0], s.yil))
                konum_tahmin(ply, s.src, esik)
                ekle(ply, l[0])
            except FileNotFoundError:
                pass
    ben = vektor(p)
    if not ben or len(havuz) < 10:
        return {'yok': True}
    F = len(tanimlar)
    mu, sd = [], []
    for f in range(F):
        col = [e[2][f] for e in havuz if e[2][f] is not None]
        m = ortalama(col) if col else 0.0
        mu.append(m)
        v = math.sqrt(ortalama((x - m) * (x - m) for x in col)) if col else 1.0
        sd.append(v if v and not math.isnan(v) else 1)
    z = lambda v: [None if x is None else (x - mu[f]) / sd[f] for f, x in enumerate(v)]
    zb = z(ben)
    sonuc = []
    for q, lig_anahtar, v in havuz:
        if (lig_anahtar == s.lig and q['idx'] == p['idx']) or (p['id'] is not None and q['id'] == p['id']):
            continue
        ortak = [(x, zb[f]) for f, x in enumerate(z(v)) if x is not None and zb[f] is not None]
        d2 = sum((x - y) * (x - y) for x, y in ortak) * F / len(ortak)  # eksik değer varsa F değere ölçeklenir
        sonuc.append((q, lig_anahtar, math.exp(-d2 / (2 * F))))
    sonuc.sort(key=lambda e: -e[2])
    return {'sonuc': sonuc[:adet], 'tanimlar': tanimlar, 'n': len(havuz), 'esik': esik}


_KARIYER = {}  # veri klasörü -> {'damga': dosya zamanları, 'kaynak': {(src, id): [satır]}, 'fm': {FotMob id: [satır]}}
_KARIYER_KILIT = threading.Lock()  # açılışta arka plan hazırlığı ve ilk istek dizini aynı anda iki kez kurmasın


class _KariyerSatiri:
    """Kariyer dizininin bir satırı, sözlük gibi okunur (r['yil']). Dizinde ~90 bin satır var: sözlüğe göre yarı bellek."""
    __slots__ = ('yil', 'lig', 'anahtar', 'takim', 'mp', 'min', 'g', 'xg', 'a', 'xa', 'id')

    def __init__(self, *degerler):
        for ad, v in zip(self.__slots__, degerler):
            setattr(self, ad, v)

    def __getitem__(self, ad):
        return getattr(self, ad)


def _kariyer_dizini(veri_klasoru):
    """Bütün lig-sezon dosyalarındaki oyuncu satırlarının dizini; dosyalar değişmedikçe bir kez kurulur."""
    dosyalar = []
    for l in LIGLER:
        for y in range(l[3], SON_SEZON + 1):
            yol = Path(veri_klasoru) / f'{l[0]}-{y}.json'
            if yol.exists():
                dosyalar.append((l, y, yol))
    damga = tuple((str(yol), yol.stat().st_mtime) for _, _, yol in dosyalar)
    with _KARIYER_KILIT:
        eski = _KARIYER.get(str(veri_klasoru))
        if eski and eski['damga'] == damga:
            return eski
        kaynak, fm = {}, {}
        for l, y, yol in dosyalar:
            raw = json.loads(yol.read_text(encoding='utf-8'))
            src = raw.get('src') or 'understat'
            for a in raw['p']:
                if len(a) <= 14 or a[14] is None or not a[1]:
                    continue
                satir = _KariyerSatiri(y, l[1], l[0], sys.intern(a[1]), a[3], a[4], a[5], a[6], a[7], a[8], a[14])
                kaynak.setdefault((src, a[14]), []).append(satir)
                fm_id = a[19] if len(a) > 19 else (a[14] if src == 'fotmob' else None)
                if fm_id is not None:
                    fm.setdefault(fm_id, []).append(satir)
        _KARIYER[str(veri_klasoru)] = {'damga': damga, 'kaynak': kaynak, 'fm': fm}
        return _KARIYER[str(veri_klasoru)]


def kariyer(veri_klasoru, src, oyuncu_id, fm_id=None):
    """Oyuncunun uygulamadaki bütün lig-sezonları. Aynı kaynakta (Understat ya da FotMob) oyuncu id'siyle, kaynaklar
    arasında (ör. Serie A'dan Süper Lig'e geçen) FotMob id'siyle eşleşir. Her satırda o lig-sezondaki kendi id'si ('id')."""
    dizin = _kariyer_dizini(veri_klasoru)
    satirlar = {(r['anahtar'], r['yil'], r['takim']): r for r in dizin['kaynak'].get((src, oyuncu_id), [])}
    for r in dizin['fm'].get(fm_id, []) if fm_id is not None else []:
        satirlar.setdefault((r['anahtar'], r['yil'], r['takim']), r)
    return sorted(satirlar.values(), key=lambda r: (-r['yil'], r['lig']))
