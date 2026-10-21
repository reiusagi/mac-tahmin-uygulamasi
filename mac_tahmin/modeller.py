"""Maç sonucu modelleri: Poisson, lojistik regresyon, random forest ve skorlama.

Eski web sürümündeki (web/mac-tahmin.html) hesapların birebir karşılığıdır. Aynı veriyle aynı sayıları üretmesi için
toplamalar soldan sağa yapılır (Python 3.12'nin telafili sum() fonksiyonu kullanılmaz)
ve rastgele sayı üreteci mulberry32'dir (eski web sürümüyle aynı sonuçları vermesi için seçildi).
"""
import math
from dataclasses import dataclass


def toplam(xs):
    s = 0
    for v in xs:
        s += v
    return s


def ortalama(xs):
    xs = list(xs)
    return toplam(xs) / len(xs)


def js_round(x):
    """.5 her zaman yukarı yuvarlanır (Python'un round'u çifte yuvarlar)."""
    return math.floor(x + 0.5)


@dataclass
class Mac:
    d: str
    h: int
    a: int
    hg: int
    ag: int
    hx: float = 0.0
    ax: float = 0.0


# ---------------------------------------------------------------- Poisson

def pmf(k, l):
    f = 1
    for i in range(2, k + 1):
        f *= i
    return math.exp(-l) * math.pow(l, k) / f


def _dixon_coles(i, j, lh, la, rho):
    """Dixon-Coles düzeltmesi: bağımsız Poisson düşük skorlu sonuçları (0-0, 1-1) az, 1-0 / 0-1'i fazla verir; rho < 0
    bu dört hücreyi düzeltir, diğerleri değişmez."""
    if i == 0 and j == 0:
        return max(0.0, 1 - lh * la * rho)
    if i == 0 and j == 1:
        return max(0.0, 1 + lh * rho)
    if i == 1 and j == 0:
        return max(0.0, 1 + la * rho)
    if i == 1 and j == 1:
        return max(0.0, 1 - rho)
    return 1.0


MAKS_TABLO = 100  # skor tablosunun en büyük kenarı (pmf'teki faktöriyel taşmasın)
MAKS_BEKLENEN = 15  # beklenen gol bundan büyükse kırpılır: daha büyüğünde bütün hücreler sıfıra iner (sıfıra bölme)


def sonuc_olasiliklari(lh, la, rho=0.0):
    """Beklenen gollerden [ev, beraberlik, deplasman] olasılıkları ve skor tablosu (en az 10x10; beklenen goller büyükse
    tablo genişler, yoksa kuyruk kesilir). rho: Dixon-Coles düzeltmesi (0: düz Poisson). Tablo ve 1X2 aynı toplama
    bölünür, yani tablo toplamı her zaman 1'dir ve bölgelerin toplamı 1X2'ye eşittir."""
    lh, la = min(lh, MAKS_BEKLENEN), min(la, MAKS_BEKLENEN)
    b = max(lh, la)
    n = min(MAKS_TABLO, max(10, math.ceil(b + 6 * math.sqrt(b) + 1)))
    pi = [pmf(i, lh) for i in range(n)]
    pj = [pmf(j, la) for j in range(n)]
    pH = pD = pA = 0.0
    hucreler = []
    for i in range(n):
        for j in range(n):
            p = pi[i] * pj[j] * (_dixon_coles(i, j, lh, la, rho) if rho else 1.0)
            if i > j:
                pH += p
            elif i == j:
                pD += p
            else:
                pA += p
            hucreler.append((i, j, p))
    s = pH + pD + pA
    hucreler = [(i, j, p / s) for i, j, p in hucreler]
    return [pH / s, pD / s, pA / s], hucreler


# maçın beklenen gollerinin ilk yarıya düşen payı: süren sezonun 1.672 maçında ikiye bölünerek iki yönlü seçildi (0,47 /
# 0,48); ilk yarı sonucu tahmini sabit oranlardan iki yönde de anlamlı iyi (log-kayıp −0,04, t ≈ −4), iyi kalibre
IY_PAY = 0.47


def ilk_yari(lh, la):
    """İlk yarı tahmini, maçın beklenen gollerinin IY_PAY kadarıyla (Poisson): {'p': [ev önde, berabere, dep önde],
    'ust05', 'ust15' (ilk yarıda en az 1 / 2 gol), 'lh', 'la'}."""
    l1, l2 = min(lh, MAKS_BEKLENEN) * IY_PAY, min(la, MAKS_BEKLENEN) * IY_PAY
    b = max(l1, l2)
    n = min(MAKS_TABLO, max(8, math.ceil(b + 6 * math.sqrt(b) + 1)))  # olağan beklentide 8x8; büyükse kuyruk kesilmesin
    p = [0.0, 0.0, 0.0]
    ust05 = ust15 = 0.0
    for i in range(n):
        for j in range(n):
            q = pmf(i, l1) * pmf(j, l2)
            p[0 if i > j else 1 if i == j else 2] += q
            ust05 += q if i + j >= 1 else 0
            ust15 += q if i + j >= 2 else 0
    s = sum(p) or 1
    return {'p': [x / s for x in p], 'ust05': ust05 / s, 'ust15': ust15 / s, 'lh': l1, 'la': l2}


def piyasalar(hucreler):
    """Skor tablosundan (sonuc_olasiliklari'nın hücreleri) toplam gol ve karşılıklı gol olasılıkları:
    {'ust15', 'ust25', 'ust35', 'kg', 'ev_gol_yemez', 'dep_gol_yemez'} ve çifte şans {'cs_1x' (ev sahibi kaybetmez),
    'cs_x2' (deplasman kaybetmez), 'cs_12' (beraberlik olmaz)}."""
    s = sum(p for _, _, p in hucreler) or 1

    def topla(kosul):
        return sum(p for i, j, p in hucreler if kosul(i, j)) / s
    return {'ust15': topla(lambda i, j: i + j >= 2), 'ust25': topla(lambda i, j: i + j >= 3),
            'ust35': topla(lambda i, j: i + j >= 4), 'kg': topla(lambda i, j: i > 0 and j > 0),
            'ev_gol_yemez': topla(lambda i, j: j == 0), 'dep_gol_yemez': topla(lambda i, j: i == 0),
            'cs_1x': topla(lambda i, j: i >= j), 'cs_x2': topla(lambda i, j: i <= j), 'cs_12': topla(lambda i, j: i != j),
            # handikap ±1,5 (beraberliksiz): ev −1,5 iki ve üstü farkla kazanır, ev +1,5 en çok bir farkla kaybeder
            'ev_m15': topla(lambda i, j: i - j >= 2), 'ev_p15': topla(lambda i, j: j - i <= 1),
            'dep_m15': topla(lambda i, j: j - i >= 2), 'dep_p15': topla(lambda i, j: i - j <= 1)}


def _fark_dagilimi(lh, la):
    """Ev golü − deplasman golü dağılımı: {fark: olasılık}."""
    out = {}
    for i, j, p in sonuc_olasiliklari(lh, la)[1]:
        out[i - j] = out.get(i - j, 0) + p
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}


MAC_SURESI = 94  # uzatmalarla bir maçın ortalama süresi (dakika); canlı olasılıkta kalan süre buna göre
KALAN_EN_AZ = 1  # süren maçta (90+5' gibi uzatma dakikalarında da) en az bu kadar dakika kalmış sayılır


DUZELTME_TABAN = 1e-3  # düzeltme oranında sıfıra bölmeyi ve bir sonucu tamamen sıfırlamayı önler


def dakika_oku(yazi):
    """Canlı skor dakikası ("67'", "45+2'") → oynanan dakika; devre arası 45. Okunamazsa None."""
    import re
    yazi = str(yazi or '')
    m = re.match(r'\s*(\d+)(?:\+(\d+))?', yazi)
    if m:
        return int(m.group(1)) + int(m.group(2) or 0)
    if re.search(r'HT|Devre|Half', yazi, re.I):
        return 45
    return None


def canli_olasilik(lh, la, ev_gol, dep_gol, dakika, once=None):
    """Maç sürerken sonuç olasılıkları [ev, beraberlik, deplasman]: maç öncesi beklenen gollerin (uzatmalar dahil bütün
    maç için lh, la) kalan süreye düşen kısmı Poisson'la oynatılır, şu anki skora eklenir. Kırmızı kart, oyun akışı
    hesaba katılmaz. Yalnızca süren maç için çağrılır: MAC_SURESI geçse de (uzatmalar) en az KALAN_EN_AZ dakika kalmış
    sayılır, sonuç neredeyse kesin olur ama maç bitmeden %100'e çıkmaz.
    once: maç öncesi harmanlı tahmin (Poisson + Dixon-Coles + Elo, Sezon.olasilik). Verilirse onun düz Poisson'dan farkı
    (Elo ve Dixon-Coles'in katkısı) oran olarak, kalan süre üssüyle çarpılır ve yeniden ölçeklenir: dakika 0'da 0-0
    sonuç tam olarak once olur, maç ilerledikçe düzeltme söner. Çarpımsal olduğundan skor durumunu bozmaz (0-3 geride
    olan favorinin şansı şişmez, beraberlik sıfırlanmaz). Dixon-Coles'i kalan süre dağılımına ayrıca uygulamak
    düzeltmeyi iki kez saymak olurdu; etkisi bu farkın içinde zaten var."""
    kalan = max(KALAN_EN_AZ, MAC_SURESI - dakika) / MAC_SURESI
    fark = ev_gol - dep_gol
    p = [0.0, 0.0, 0.0]
    for k, v in _fark_dagilimi(max(lh * kalan, 1e-6), max(la * kalan, 1e-6)).items():
        son = fark + k
        p[0 if son > 0 else 1 if son == 0 else 2] += v
    if once is not None:
        duz = sonuc_olasiliklari(lh, la)[0]
        p = [p[k] * (max(once[k], DUZELTME_TABAN) / max(duz[k], DUZELTME_TABAN)) ** kalan for k in range(3)]
        s = p[0] + p[1] + p[2]
        p = [x / s for x in p]
    return p


def tur_atlama(lh, la, onceki=None, rovans=None):
    """Eleme maçında bu maçın ev sahibinin turu geçme olasılığı. lh, la: bu maçın beklenen golleri.
    onceki: bu maç rövanşsa ilk maçta (bu maçın ev sahibi, deplasmanı) attığı goller.
    rovans: bu maç iki maçlı eşleşmenin ilk maçıysa rövanşın beklenen golleri (rövanşın ev sahibi, yani bu maçın
    deplasmanı önce). Toplam eşitse uzatma (son maçın sahasında, beklenen gollerin üçte biri) ve penaltılar (yarı yarıya)."""
    if rovans:
        d1 = _fark_dagilimi(lh, la)
        d2 = {-k: v for k, v in _fark_dagilimi(*rovans).items()}  # bu maçın ev sahibi açısından
        uz = sonuc_olasiliklari(rovans[0] / 3, rovans[1] / 3)[0]
        uz_ev = uz[2] + uz[1] / 2
        return sum(v1 * v2 * (1 if a + b > 0 else uz_ev if a + b == 0 else 0) for a, v1 in d1.items() for b, v2 in d2.items())
    bas = (onceki[0] - onceki[1]) if onceki else 0
    uz = sonuc_olasiliklari(lh / 3, la / 3)[0]
    uz_ev = uz[0] + uz[1] / 2
    return sum(v * (1 if bas + k > 0 else uz_ev if bas + k == 0 else 0) for k, v in _fark_dagilimi(lh, la).items())


@dataclass
class Poisson:
    mu: float
    hm: float
    att: list
    de: list

    def lambdalar(self, h, a):
        """Ev ve deplasman takımının beklenen golü."""
        return (self.mu * self.hm * self.att[h] * self.de[a],
                self.mu * self.att[a] * self.de[h])


YENI_ATT, YENI_DEF, YENI_S = 0.8, 1.2, 10  # ligde yeni takımların ön bilgisi ve gücü (gol cinsinden)


def poisson_kur(M, n, w=None, yeni=None, xg_pay=0.0):
    """Gol beklentisi = lig ortalaması × ev avantajı × hücum gücü × rakibin savunma zaafı.
    w: maç ağırlıkları (eski maçlar daha az etkili olsun diye). yeni: geçmiş verisi olmayan takımlar;
    bunlar az maça aşırı güvenilmesin diye "yükselen takım" ön bilgisine daha güçlü çekilir.
    xg_pay: güçler hesaplanırken maçın golü yerine (1 - pay) × gol + pay × xG kullanılır (xG'si olan maçlarda); xG
    şansa daha az bağlı olduğu için güçler daha az oynar."""
    if xg_pay:
        M = [Mac(m.d, m.h, m.a, (1 - xg_pay) * m.hg + xg_pay * m.hx, (1 - xg_pay) * m.ag + xg_pay * m.ax, m.hx, m.ax)
             if (m.hx or m.ax) else m for m in M]
    att = [1.0] * n
    de = [1.0] * n
    mu, hm = 1.2, 1.3
    s = [YENI_S if yeni and yeni[i] else 3 for i in range(n)]
    a0 = [1 if v == 3 else YENI_ATT for v in s]
    d0 = [1 if v == 3 else YENI_DEF for v in s]
    q = w if w is not None else [1] * len(M)
    for _ in range(60):
        num = [0] * n
        den = [0] * n
        for m, k in zip(M, q):
            num[m.h] += k * m.hg
            den[m.h] += k * mu * hm * de[m.a]
            num[m.a] += k * m.ag
            den[m.a] += k * mu * de[m.h]
        att = [(num[i] + s[i] * a0[i]) / (den[i] + s[i]) for i in range(n)]
        nd = [0] * n
        dd = [0] * n
        for m, k in zip(M, q):
            nd[m.a] += k * m.hg
            dd[m.a] += k * mu * hm * att[m.h]
            nd[m.h] += k * m.ag
            dd[m.h] += k * mu * att[m.a]
        de = [(nd[i] + s[i] * d0[i]) / (dd[i] + s[i]) for i in range(n)]
        ma, md = ortalama(att), ortalama(de)
        att = [v / ma for v in att]
        de = [v / md for v in de]
        hg = ag = hd = ad = 0
        for m, k in zip(M, q):
            hg += k * m.hg
            ag += k * m.ag
            hd += k * att[m.h] * de[m.a]
            ad += k * att[m.a] * de[m.h]
        if ad > 0 and hd > 0 and ag > 0:
            mu = ag / ad
            hm = (hg / hd) / mu
    return Poisson(mu, hm, att, de)


def poisson_cek(R, l):
    """Knuth yöntemiyle Poisson dağılımından bir sayı (verilen rastgele sayı üretecini kullanır)."""
    L = math.exp(-l)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= R()
        if p <= L:
            return k - 1


# ---------------------------------------------------------------- lojistik regresyon

def softmax(W, x):
    z = []
    for w in W:
        s = w[len(x)]
        for f, v in enumerate(x):
            s += v * w[f]
        z.append(s)
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = e[0] + e[1] + e[2]
    return [v / s for v in e]


def lojistik_kur(X, Y, adim=600, oran=0.3, l2=0.02):
    """Üç sınıflı (ev/beraberlik/deplasman) softmax regresyonu, tam yığın gradyan inişi."""
    F, N = len(X[0]), len(X)
    W = [[0.0] * (F + 1) for _ in range(3)]
    for _ in range(adim):
        G = [[0.0] * (F + 1) for _ in range(3)]
        for i in range(N):
            p = softmax(W, X[i])
            for k in range(3):
                e = p[k] - (1 if Y[i] == k else 0)
                for f in range(F):
                    G[k][f] += e * X[i][f]
                G[k][F] += e
        for k in range(3):
            for f in range(F + 1):
                W[k][f] -= oran * (G[k][f] / N + (l2 * W[k][f] if f < F else 0))
    return W


# ---------------------------------------------------------------- random forest

def _i32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def _imul(a, b):
    return _i32((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF))


def mulberry32(seed):
    """Tohumlu, hızlı ve taşınabilir rastgele sayı üreteci (0 ile 1 arası)."""
    state = [_i32(seed)]

    def r():
        state[0] = _i32(state[0] + 0x6D2B79F5)
        s = state[0]
        t = _imul(s ^ ((s & 0xFFFFFFFF) >> 15), 1 | s)
        t = _i32(t + _imul(t ^ ((t & 0xFFFFFFFF) >> 7), 61 | t)) ^ t
        return ((t ^ ((t & 0xFFFFFFFF) >> 14)) & 0xFFFFFFFF) / 4294967296
    return r


def _gini(c):
    s = c[0] + c[1] + c[2]
    return 1 - (c[0] * c[0] + c[1] * c[1] + c[2] * c[2]) / (s * s) if s else 0


class Orman:
    """Gini bölmeli, önyüklemeli (bootstrap) ve her düğümde 3 rastgele özellik deneyen orman."""

    def __init__(self, X, Y, agac=150, derinlik=5, min_yaprak=8, tohum=42):
        self.R = mulberry32(tohum)
        self.X, self.Y = X, Y
        self.F = len(X[0])
        self.derinlik, self.min_yaprak, self.mtry = derinlik, min_yaprak, min(3, self.F)
        imp = [0.0] * self.F
        self._imp = imp
        N = len(X)
        self.agaclar = []
        for _ in range(agac):
            idx = [math.floor(self.R() * N) for _ in range(N)]
            self.agaclar.append(self._buyut(idx, 0))
        tot = toplam(imp) or 1
        self.onem = [v / tot for v in imp]
        del self.X, self.Y

    def _buyut(self, idx, d):
        X, Y = self.X, self.Y
        c = [0, 0, 0]
        for i in idx:
            c[Y[i]] += 1
        yaprak = {'p': [v / len(idx) for v in c]}
        g0 = _gini(c)
        if d >= self.derinlik or len(idx) < 2 * self.min_yaprak or g0 == 0:
            return yaprak
        feats = []
        while len(feats) < self.mtry:
            f = math.floor(self.R() * self.F)
            if f not in feats:
                feats.append(f)
        best = None
        for f in feats:
            s = sorted(idx, key=lambda i: X[i][f])
            L, Rc = [0, 0, 0], list(c)
            for k in range(len(s) - 1):
                L[Y[s[k]]] += 1
                Rc[Y[s[k]]] -= 1
                nl = k + 1
                nr = len(s) - nl
                if nl < self.min_yaprak or nr < self.min_yaprak or X[s[k]][f] == X[s[k + 1]][f]:
                    continue
                gain = g0 - (nl * _gini(L) + nr * _gini(Rc)) / len(s)
                if best is None or gain > best[0]:
                    best = (gain, f, (X[s[k]][f] + X[s[k + 1]][f]) / 2)
        if best is None or best[0] < 1e-9:
            return yaprak
        gain, f, t = best
        self._imp[f] += gain * len(idx)
        sol = self._buyut([i for i in idx if X[i][f] <= t], d + 1)
        sag = self._buyut([i for i in idx if X[i][f] > t], d + 1)
        return {'f': f, 't': t, 'l': sol, 'r': sag}

    def tahmin(self, x):
        p = [0.0, 0.0, 0.0]
        for t in self.agaclar:
            while 'f' in t:
                t = t['l'] if x[t['f']] <= t['t'] else t['r']
            for k in range(3):
                p[k] += t['p'][k]
        q = [max(v / len(self.agaclar), 0.01) for v in p]
        s = q[0] + q[1] + q[2]
        return [v / s for v in q]


# ---------------------------------------------------------------- skorlama

def skorla(P, Y):
    """Doğruluk, log-loss ve (üç sınıf üzerinden toplanan) Brier skoru."""
    acc = ll = br = 0
    for p, y in zip(P, Y):
        if p.index(max(p)) == y:
            acc += 1
        ll -= math.log(max(p[y], 1e-9))
        for k in range(3):
            br += math.pow(p[k] - (1 if y == k else 0), 2)
    n = len(Y)
    return {'dogruluk': acc / n, 'log_loss': ll / n, 'brier': br / n}
