"""Tahmin karnesi: modelin maç sonuçlarını ne kadar iyi bildiği. Her ligin süren ve geçen sezonundaki her hafta, yalnızca
o haftadan önce oynanmış maçlarla (ve önceki sezonlarla) kurulan modelle tahmin edilir ve gerçek sonuçla karşılaştırılır:
maç günü yapılmış tahminin aynısı, sonradan öğrenilen hiçbir şey kullanılmaz (sezon toplamı xG gibi bilgiler de çıkarılır).
Sonuçlar cikti/karne.json'da birikir; her güncellemede yalnızca yeni haftalar hesaplanır."""
import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path

from .modeller import piyasalar
from .sezon import GECMIS, LIGLER, SON_SEZON, Sezon, ham_oku

logger = logging.getLogger(__name__)

SEZONLAR = (SON_SEZON - 1, SON_SEZON)
KAYIT_UZUNLUK = 14  # [lig, sezon, tarih, ev, dep, p ev, p ber, p dep, ev gol, dep gol, 1,5 üst, 2,5 üst, 3,5 üst, kg]
# gol piyasaları: (kayıttaki sıra, ad, gerçekleşti mi (ev golü, dep golü))
GOL_PIYASALARI = [(10, '1,5 üst', lambda h, a: h + a >= 2), (11, '2,5 üst', lambda h, a: h + a >= 3),
                  (12, '3,5 üst', lambda h, a: h + a >= 4), (13, 'Karşılıklı gol', lambda h, a: h > 0 and a > 0)]


def _hafta_basi(tarih):
    g = date.fromisoformat(tarih[:10])
    return (g - timedelta(days=g.weekday())).isoformat()


def oku(cikti):
    yol = Path(cikti) / 'karne.json'
    return json.loads(yol.read_text(encoding='utf-8')) if yol.exists() else []


_ONBELLEK = {}  # karne dosyası -> (değişme zamanı, kayıtlar)


def oku_onbellek(cikti):
    """oku()'nun dosya değişmedikçe bellekten dönen hâli (maç tahmini her maçta güven göstergesi için okur)."""
    yol = Path(cikti) / 'karne.json'
    if not yol.exists():
        return []
    damga = yol.stat().st_mtime
    eski = _ONBELLEK.get(str(yol))
    if eski and eski[0] == damga:
        return eski[1]
    kayitlar = oku(cikti)
    _ONBELLEK[str(yol)] = (damga, kayitlar)
    return kayitlar


GUVEN_PAY = 0.05  # güven göstergesi: favorinin olasılığına ± bu kadar yakın geçmiş tahminlere bakılır
GUVEN_LIG_MIN = 30  # ligin kendi oranı en az bu kadar benzer maç varsa gösterilir


def favori_isabeti(kayitlar, p_fav, lig=None, pay=GUVEN_PAY):
    """Model en olası sonuca p_fav civarında (± pay) olasılık verdiği geçmiş maçlarda o sonucun gerçekleşme oranı.
    lig verilirse yalnızca o lig. Döner: (oran, maç sayısı); hiç maç yoksa (None, 0)."""
    tut = n = 0
    for r in kayitlar:
        if lig is not None and r[0] != lig:
            continue
        p = r[5:8]
        en = max(p)
        if abs(en - p_fav) > pay:
            continue
        sonuc = 0 if r[8] > r[9] else 1 if r[8] == r[9] else 2
        n += 1
        tut += p.index(en) == sonuc
    return (tut / n if n else None), n


def guncelle(cikti, yaz=None):
    """Eksik haftaları hesaplar ve kaydeder. Kayıt: KAYIT_UZUNLUK alanı (ev/beraberlik/deplasman ve gol piyasalarının
    olasılıkları, gerçek skor). Eski biçimdeki (kısa) kayıtlar yeniden hesaplanır. Yeni kayıt sayısını döner."""
    kayitlar = [r for r in oku(cikti) if len(r) >= KAYIT_UZUNLUK]
    var = {(r[0], r[2], r[3], r[4]) for r in kayitlar}
    yeni = 0
    for l in LIGLER:
        for yil in SEZONLAR:
            if yil < l[3]:
                continue
            try:
                raw = ham_oku(cikti, l[0], yil)
            except FileNotFoundError:
                continue
            onceki = []
            for y in range(yil - GECMIS, yil):
                if y >= l[3]:
                    try:
                        onceki.append(ham_oku(cikti, l[0], y))
                    except FileNotFoundError:
                        pass
            maclar = sorted(raw['m'], key=lambda m: m[0])
            haftalar = {}
            for m in maclar:
                if (l[0], m[0], raw['t'][m[1]], raw['t'][m[2]]) not in var:
                    haftalar.setdefault(_hafta_basi(m[0]), []).append(m)
            for hafta, hm in sorted(haftalar.items()):
                once = [m for m in maclar if m[0] < hafta]
                if len(once) < len(raw['t']) // 2 and not onceki:  # sezonun ilk haftası ve geçmiş yok: tahmin anlamsız
                    continue
                kirpik = {**raw, 'm': once, 'u': [], 'p': [], 'tx': None}
                try:
                    S = Sezon(kirpik, l[0], yil, onceki)
                except Exception:
                    logger.debug('hafta modeli kurulamadı: %s %s %s', l[0], yil, hafta, exc_info=True)
                    continue
                for m in hm:
                    t = S.tahmin(m[1], m[2])
                    p, pz = t['p'], piyasalar(t['hucreler'])
                    kayitlar.append([l[0], yil, m[0], raw['t'][m[1]], raw['t'][m[2]], round(p[0], 4), round(p[1], 4),
                                     round(p[2], 4), m[3], m[4], round(pz['ust15'], 4), round(pz['ust25'], 4),
                                     round(pz['ust35'], 4), round(pz['kg'], 4)])
                    yeni += 1
            if yaz:
                yaz(f'{l[1]} {yil}: tamam')
    if yeni:
        yol = Path(cikti) / 'karne.json'
        gecici = yol.with_suffix('.tmp')
        gecici.write_text(json.dumps(kayitlar, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        gecici.replace(yol)
    return yeni


def gol_ozeti(kayitlar):
    """Gol piyasalarının karnesi: [{'ad', 'n', 'tahmin' (ortalama olasılık), 'oran' (gerçekleşme), 'isabet' (%50 üstü
    "olur", altı "olmaz" deyince tutma oranı), 'log_kayip', 'bilgisiz' (hep ortalama oranı vermenin log-kaybı),
    'kalibrasyon': [(tahmin ort., gerçekleşen, n)]}]."""
    K = [r for r in kayitlar if len(r) >= KAYIT_UZUNLUK]
    if not K:
        return []
    out = []
    for i, ad, oldu_mu in GOL_PIYASALARI:
        ys = [1 if oldu_mu(r[8], r[9]) else 0 for r in K]
        ps = [min(max(r[i], 1e-6), 1 - 1e-6) for r in K]
        n = len(K)
        oran = sum(ys) / n
        q = min(max(oran, 1e-6), 1 - 1e-6)
        kal = {}
        for p, y in zip(ps, ys):
            b = kal.setdefault(min(9, int(p * 10)), [0, 0.0, 0])
            b[0] += 1
            b[1] += p
            b[2] += y
        out.append({'ad': ad, 'n': n, 'tahmin': sum(ps) / n, 'oran': oran,
                    'isabet': sum(1 for p, y in zip(ps, ys) if (p >= 0.5) == bool(y)) / n,
                    'log_kayip': -sum(math.log(p if y else 1 - p) for p, y in zip(ps, ys)) / n,
                    'bilgisiz': -(oran * math.log(q) + (1 - oran) * math.log(1 - q)),
                    'kalibrasyon': [(b[1] / b[0], b[2] / b[0], b[0]) for _, b in sorted(kal.items()) if b[0] >= 20]})
    return out


def ozet(kayitlar):
    """İsabet (en olası sonucun gerçekleşme oranı), log-kayıp, Brier puanı, karşılaştırma ölçütleri ve kalibrasyon."""
    n = len(kayitlar)
    if not n:
        return None
    isabet = logk = brier = ev_isabet = 0.0
    kal = [[0, 0.0, 0] for _ in range(10)]  # [tahmin sayısı, tahmin toplamı, gerçekleşen]
    for r in kayitlar:
        p = r[5:8]
        sonuc = 0 if r[8] > r[9] else 1 if r[8] == r[9] else 2
        isabet += p.index(max(p)) == sonuc
        ev_isabet += sonuc == 0
        logk -= math.log(max(1e-9, p[sonuc]))
        brier += sum((p[k] - (k == sonuc)) ** 2 for k in range(3))
        for k in range(3):
            b = min(9, int(p[k] * 10))
            kal[b][0] += 1
            kal[b][1] += p[k]
            kal[b][2] += k == sonuc
    # kıyas: hep aynı olasılıkları veren "bilgisiz" tahmin (ev, beraberlik, deplasman oranları)
    oran = [sum(1 for r in kayitlar if (r[8] > r[9], r[8] == r[9], r[8] < r[9])[k]) / n for k in range(3)]
    bilgisiz = -sum(oran[k] * math.log(max(1e-9, oran[k])) for k in range(3))
    return {'n': n, 'isabet': isabet / n, 'log_kayip': logk / n, 'brier': brier / n, 'ev_isabet': ev_isabet / n,
            'bilgisiz_log_kayip': bilgisiz, 'oran': oran,
            'kalibrasyon': [(k[1] / k[0], k[2] / k[0], k[0]) for k in kal if k[0] >= 20]}
