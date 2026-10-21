"""Oyuncu tahminleri: gol / asist krallığı yarışı (sezonun kalanı Monte Carlo ile oynatılır), maçta kim asist yapar,
kim kart görür. Hepsi sezon.Sezon verisinden (oyuncuların sezonki dakikaları, gol, asist, xG, xA, kartları)."""
import math

import numpy as np

# Küçük örneklem düzeltmeleri. Değerler geri testle seçildi (2026 sezonu: ilk 3-5 haftanın verisiyle sonraki haftalarda
# oyuncunun maçta gol / asist / sarı kart olasılığı; Brezilya, İngiltere, İspanya, Türkiye liglerinde ~5.600 oyuncu-maç).
ON_MAC = 6        # gol ve asist oranı, oyuncunun mevkisinin ortalamasıyla bu kadar maçlık süre kadar harmanlanır
KART_ON_MAC = 10  # sarı kart oranı, ligin ortalamasıyla bu kadar maçlık süre kadar harmanlanır
# önceki sezonlar: geçen sezonun ve ondan önceki sezonun dakikalarının ağırlığı; toplam ağırlık en fazla ONCEKI_TAVAN
# maçlık süre kadar (sezon başında geçmiş baskın, sezon ilerledikçe bu sezonun verisi öne geçer)
ONCEKI_AGIRLIK = {1: 0.6, 2: 0.3}
ONCEKI_TAVAN = 12
_ALAN = {'gol': ('g', 'xg'), 'asist': ('a', 'xa')}


def _takim_indeksi(S, p):
    """Oyuncunun (sezonda en son oynadığı) takımının indeksi; bulunamazsa None."""
    ad = p['t'].split(' / ')[-1]
    return S.T.index(ad) if ad in S.T else None


def _uretim(p, tur):
    """Oyuncunun bu sezonki üretimi: (gol + xG) / 2 ya da (asist + xA) / 2 (xG / xA yoksa yalnızca gol / asist)."""
    k, kx = _ALAN[tur]
    return (p[k] + (p[kx] if p[kx] is not None else p[k])) / 2


def mevki_oranlari(S, tur):
    """Mevki mevki (ve None: bütün lig) 90 dakika başına ortalama üretim. Sezonda bir kez hesaplanır."""
    onbellek = S.__dict__.setdefault('_mevki_oran', {})
    if tur not in onbellek:
        top = {}
        for p in S.PLY:
            for anahtar in (p['pos'], None):
                t = top.setdefault(anahtar, [0.0, 0.0])
                t[0] += _uretim(p, tur)
                t[1] += p['min'] / 90
        onbellek[tur] = {m: (v / n if n else 0.0) for m, (v, n) in top.items()}
    return onbellek[tur]


def oran(S, p, tur, onceki=None):
    """Oyuncunun 90 dakika başına gol ya da asist üretimi (tahmini): bu sezonki üretimi, önceki sezonları (onceki:
    onceki_sezonlar() sonucu) ve mevkisinin ortalaması (ON_MAC maçlık süre kadar) harmanlanır. Sezon başında birkaç
    maçlık şanslı ya da şanssız gidiş tahmini uç noktalara taşımaz."""
    m = mevki_oranlari(S, tur)
    mo = m.get(p['pos'], m.get(None, 0.0)) if p['pos'] not in ('S', 'U') else m.get(None, 0.0)
    od, o90 = (onceki or {}).get(p['idx'], (0.0, 0.0))
    return (_uretim(p, tur) + od + mo * ON_MAC) / (p['min'] / 90 + o90 + ON_MAC)


def onceki_sezonlar(S, veri_klasoru, tur='gol'):
    """Oyuncuların önceki iki sezondaki üretimi (uygulamadaki bütün ligler; transfer olanlar FotMob id'siyle eşleşir):
    {oyuncu idx: (ağırlıklı değer, ağırlıklı 90 dakika sayısı)}; değer (gol + xG) / 2 ya da (asist + xA) / 2.
    Ağırlıklı süre ONCEKI_TAVAN maçı geçmez. Sezonda bir kez hesaplanır (S._onceki)."""
    from .sezon import _kariyer_dizini
    onbellek = S.__dict__.setdefault('_onceki', {})
    if tur in onbellek:
        return onbellek[tur]
    dizin = _kariyer_dizini(veri_klasoru)
    k, kx = _ALAN[tur]
    out = {}
    for p in S.PLY:
        # sezon.kariyer ile aynı eşleştirme: aynı kaynakta oyuncu id'si, kaynaklar arasında FotMob id'si
        satirlar = {(r['anahtar'], r['yil'], r['takim']): r for r in dizin['kaynak'].get((S.src, p['id']), [])}
        for r in dizin['fm'].get(p.get('fm_id'), []) if p.get('fm_id') is not None else []:
            satirlar.setdefault((r['anahtar'], r['yil'], r['takim']), r)
        deger = doksan = 0.0
        for r in satirlar.values():
            w = ONCEKI_AGIRLIK.get(S.yil - r['yil'])
            if not w or not r['min']:
                continue
            deger += w * (r[k] + (r[kx] if r[kx] is not None else r[k])) / 2
            doksan += w * r['min'] / 90
        if doksan > 0:
            olcek = min(1.0, ONCEKI_TAVAN / doksan)
            out[p['idx']] = (deger * olcek, doksan * olcek)
    onbellek[tur] = out
    return out


def _ilk3(son):
    """Her oyuncunun, simülasyonların kaçında ilk üçte olduğu (kendisinden kesin fazla atan en çok 2 oyuncu varsa): üçüncü
    en yüksek değerden az atmamış olmak. son: (simülasyon, oyuncu) gol sayıları. O(N·A) bellek (eskisi N·A·A idi)."""
    n_oyuncu = son.shape[1]
    if n_oyuncu < 3:
        return np.ones(n_oyuncu)
    ucuncu = np.partition(son, n_oyuncu - 3, axis=1)[:, n_oyuncu - 3]
    return (son >= ucuncu[:, None]).mean(axis=0)


def krallik(S, tur='gol', N=10000, adet=15, tohum=7, onceki=None):
    """Gol (tur='gol') ya da asist krallığı yarışı: her oyuncunun kalan maçlardaki golü, 90 dakikadaki (gol + xG) / 2
    oranı ve maç başına süresiyle Poisson'dan çekilir; sezon N kez sonuna kadar oynatılır. Eşitlikte krallık paylaştırılır.
    Oran oran() ile: önceki sezonlar (onceki: onceki_sezonlar() sonucu) ve mevkinin ortalamasıyla harmanlanır; sezon
    başında birkaç maçta gol atan oyuncu, geçmişi zayıfsa listenin tepesine fırlamaz.
    Döner: [{'p', 'mevcut', 'beklenen', 'kral', 'ilk3'}] (krallık olasılığına göre)."""
    k, kx = ('g', 'xg') if tur == 'gol' else ('a', 'xa')
    onceki = onceki or {}
    kalan = {i: 0 for i in range(len(S.T))}
    for m in S.U:
        kalan[m.h] += 1
        kalan[m.a] += 1
    oynanan = {r['i']: r['O'] for r in S.tb}
    # adaylar: bu sezon üreten ya da geçmişi güçlü olan (ör. ilk haftalarda gol atamamış golcü) oyuncular
    adaylar = [p for p in S.PLY if p[k] > 0 or (p[kx] or 0) >= 1 or (p['min'] > 0 and onceki.get(p['idx'], (0,))[0] >= 3)]
    if not adaylar:
        return []
    mevcut = np.array([p[k] for p in adaylar], float)
    lam = np.zeros(len(adaylar))
    for j, p in enumerate(adaylar):
        t = _takim_indeksi(S, p)
        if t is None or p.get('ayrildi') or not oynanan.get(t):
            continue  # ligden ayrılan ya da takımı bulunamayan: golü sabit kalır
        mac_basi_dk = min(90.0, p['min'] / oynanan[t])
        lam[j] = oran(S, p, tur, onceki) * mac_basi_dk / 90 * kalan[t]
    rng = np.random.default_rng(tohum)
    son = mevcut + rng.poisson(lam, size=(N, len(adaylar)))
    en = son.max(axis=1, keepdims=True)
    esit = son == en
    kral = (esit / esit.sum(axis=1, keepdims=True)).mean(axis=0)
    ilk3 = _ilk3(son)
    out = [{'p': p, 'mevcut': int(mevcut[j]), 'beklenen': float(son[:, j].mean()), 'kral': float(kral[j]),
            'ilk3': float(ilk3[j])} for j, p in enumerate(adaylar)]
    return sorted(out, key=lambda r: (-r['kral'], -r['beklenen']))[:adet]


ENDEKS_ON_MAC = 6  # performans endeksi, az süre alan oyuncuda bu kadar maçlık süre kadar ortalamaya (50) çekilir


def performans_endeksi(S):
    """Her oyuncu için 0-100 performans endeksi: mevkidaşlarına göre yüzdelik dilimlerinin (gol, xG, asist, xA, şut, kilit
    pas, çalım, pas, top çalma…; 90 dk başına) ortalaması; az süre alan oyuncuda ortalamaya (50) doğru çekilir (2 maçlık
    parlak gidiş, 20 maçlık istikrarlı üretimle aynı sayılmasın). Ligde eşik kadar oynamamışsa None. Sezonda bir kez
    hesaplanır."""
    if getattr(S, '_endeks', None) is not None:
        return S._endeks
    out, ham_ = {}, {}
    for p in S.PLY:
        if p['min'] < S.min_esik:
            continue
        y = S.oyuncu_karti(p)['yuzdelik']
        if y:
            ham = sum(pc for _, _, pc in y) / len(y)
            n = p['min'] / 90
            out[p['idx']] = 50 + (ham - 50) * n / (n + ENDEKS_ON_MAC)
            ham_[p['idx']] = (ham, n)
    S._endeks, S._endeks_ham = out, ham_  # ham: (çekilmemiş yüzdelik ortalaması, 90 dk sayısı); endeks_harmanla için
    return out


ONCEKI_ENDEKS_AGIRLIK = 0.5  # scout endeksinde önceki sezonun süresinin ağırlığı (bu sezonun bir maçı = önceki sezonun 2'si)
ONCEKI_ENDEKS_TAVAN = 15     # önceki sezondan en çok bu kadar maçlık (90 dk) süre sayılır


def endeks_harmanla(S, onceki):
    """Scout'un performans endeksi: bu sezonun yüzdelikleri önceki sezonunkiyle harmanlanır; bir sezonun kısa düşüşü ya
    da birkaç maçlık parlak gidişi tek başına belirleyici olmasın. onceki: {oyuncu idx: (önceki sezonun çekilmemiş
    yüzdelik ortalaması, 90 dk sayısı)} (o sezon ligindeki mevkidaşlarına göre). Önceki sezon en çok ONCEKI_ENDEKS_TAVAN
    maçlık süre × ONCEKI_ENDEKS_AGIRLIK kadar sayılır; sezon ilerledikçe bu sezon öne geçer. Sonra performans_endeksi gibi
    az süreye göre 50'ye çekilir. S._endeks_harman'a yazılır (scout_endeksi)."""
    performans_endeksi(S)
    out = {}
    for idx, (ham, n) in S._endeks_ham.items():
        h0, n0 = onceki.get(idx, (None, 0))
        w = min(n0, ONCEKI_ENDEKS_TAVAN) * ONCEKI_ENDEKS_AGIRLIK if h0 is not None else 0.0
        H, N = ((ham * n + h0 * w) / (n + w), n + w) if w else (ham, n)
        out[idx] = 50 + (H - 50) * N / (N + ENDEKS_ON_MAC)
    S._endeks_harman = out
    return out


def scout_endeksi(S):
    """Scout'ta kullanılan endeks: önceki sezonla harmanlanmışsa (endeks_harmanla) o, değilse bu sezonunki."""
    return getattr(S, '_endeks_harman', None) or performans_endeksi(S)


def fiyat_performans(S, degerler):
    """Oyuncunun performans endeksi ile piyasa değerinin ligdeki yüzdelik sırası arasındaki fark (−100…+100): artı,
    değerinin üstünde oynuyor demek. degerler: {oyuncu idx: €}. Döner: {idx: fark}."""
    endeks = scout_endeksi(S)
    ortak = [i for i in endeks if degerler.get(i)]
    if len(ortak) < 10:
        return {}
    sirali = sorted(degerler[i] for i in ortak)
    out = {}
    for i in ortak:
        alt = sum(1 for x in sirali if x < degerler[i])
        esit = sum(1 for x in sirali if x == degerler[i])
        out[i] = endeks[i] - (alt + esit / 2) / len(sirali) * 100
    return out


SCOUT_GRUPLARI = [('kaleci', 'Kaleciler'), ('stoper', 'Stoperler'), ('bek', 'Bekler'), ('orta', 'Orta saha'),
                  ('kanat', 'Kanatlar'), ('forvet', 'Forvetler')]
_DETAY_GRUP = {'GK': 'kaleci', 'CB': 'stoper', 'RB': 'bek', 'LB': 'bek', 'DM': 'orta', 'CM': 'orta', 'AM': 'orta',
               'RW': 'kanat', 'LW': 'kanat', 'ST': 'forvet'}
_ANA_GRUP = {'G': 'kaleci', 'D': 'stoper', 'M': 'orta', 'W': 'kanat', 'F': 'forvet'}


def scout_grubu(p):
    """Oyuncunun scout'taki mevki grubu: ayrıntılı mevkisi (CB, RB…) ana mevkisiyle uyumluysa ondan, değilse ana mevkiden."""
    from .sezon import DETAY
    d = p.get('detay')
    if d in _DETAY_GRUP and DETAY.get(d, ('',))[0] == p['pos']:
        return _DETAY_GRUP[d]
    return _ANA_GRUP.get(p['pos'])


# Transfer zorluğu (0-100): oyuncuyu kulübünden almanın ne kadar zor olduğu. Bileşenler ve ağırlıkları:
#   kulüp büyüklüğü (kadro değeri, log ölçek): dev kulüpler satma baskısı altında değil, küçük kulüpler doğru fiyata satar
#   rolü: takımının maçlarındaki süre payı (düzenli ilk 11 oyuncusu yedekten zor alınır)
#   kulüp için önemi: değerinin kulübün kadro değerindeki payı (kulübün en değerli oyuncularından biri en zor alınır)
ZORLUK_AGIRLIK = {'kulup': 60, 'rol': 25, 'onem': 15}
KULUP_ALT, KULUP_UST = 15e6, 1.2e9  # kadro değeri bunun altındaysa kulüp büyüklüğü 0, üstündeyse 100
ONEM_TAVAN = 0.10                   # kadro değerinin %10'u ve üstü: kulüp için önemi tam
# etiketler: dev kulübün yedeği "zor" (kiralık / satış görüşülebilir), düzenli oynayan yıldızı "çok zor"
ZORLUK_ETIKET = [(80, 'Çok zor'), (60, 'Zor'), (35, 'Orta'), (0, 'Kolay')]
KULUP_SINIFI = [(700e6, 'dev kulüp'), (250e6, 'büyük kulüp'), (80e6, 'orta-üst sıra kulüp'), (25e6, 'orta halli kulüp'),
                (0, 'küçük kulüp')]
GERCEKCI_CEZA = 0.4  # "gerçekçi hedef" sıralaması: endeks × (1 − 0,4 × zorluk / 100)
# yaş düzeltmesi: kulüpler deneyimli oyuncuyu daha kolay bırakır, genç yetenekleri korur
YAS_DUZELTME = [(33, -20, 'deneyimli: kulüpler bu yaştaki oyuncuyu kolay bırakır'),
                (30, -10, 'otuzlarında: kulüpler satmaya daha açık'),
                (0, 0, None)]
GENC_YAS, GENC_EK = 21, 5  # 21 yaş ve altı: kulüpler genç yetenekleri korur
# sözleşme düzeltmesi (bitişe kalan ay): son 6 ay bedelsiz / ucuz, son yıl kulüp satmaya açık, uzun sözleşme korur
SOZLESME_DUZELTME = [(6, -35, 'bedelsiz ya da çok ucuza alınabilir'), (18, -15, 'kulüp satmaya daha açık'),
                     (48, 0, None), (10 ** 6, 5, 'uzun sözleşmeli')]


def _para(x):
    return f'{x / 1e9:.1f} Mr€'.replace('.', ',') if x >= 1e9 else f'{round(x / 1e6)} M€'


def transfer_zorlugu(S, p, deger, kulup_degeri):
    """(puan 0-100, etiket, [nedenler]) — kulüp büyüklüğü, takımdaki rolü ve kulüp için önemi (ZORLUK_AGIRLIK)."""
    t = _takim_indeksi(S, p)
    oynanan = S.tb[t]['O'] if t is not None else 0
    rol = min(1.0, p['min'] / (oynanan * 90)) if oynanan else 0.0
    kulup = 0.0
    if kulup_degeri:
        kulup = (math.log10(max(kulup_degeri, KULUP_ALT)) - math.log10(KULUP_ALT)) / (math.log10(KULUP_UST) - math.log10(KULUP_ALT))
        kulup = min(1.0, kulup)
    onem = min(1.0, (deger or 0) / kulup_degeri / ONEM_TAVAN) if kulup_degeri else 0.0
    puan = ZORLUK_AGIRLIK['kulup'] * kulup + ZORLUK_AGIRLIK['rol'] * rol + ZORLUK_AGIRLIK['onem'] * onem
    yas = p.get('yas')
    yas_neden = None
    if yas is not None:
        alt, fark, yas_neden = next(x for x in YAS_DUZELTME if yas >= x[0])
        if yas <= GENC_YAS:
            fark, yas_neden = GENC_EK, 'genç: kulüpler genç yetenekleri korur'
        puan = min(100.0, max(0.0, puan + fark))
    etiket = _etiket(puan)
    takim = p['t'].split(' / ')[-1]
    nedenler = []
    if kulup_degeri:
        sinif = next(ad for alt, ad in KULUP_SINIFI if kulup_degeri >= alt)
        nedenler.append(f'{takim} {sinif} (kadro {_para(kulup_degeri)})')
    nedenler.append('takımında düzenli ilk 11' if rol >= 0.7 else 'takımında rotasyon oyuncusu' if rol >= 0.4
                    else 'takımında az süre alıyor')
    if deger and kulup_degeri:
        pay = deger / kulup_degeri
        if pay >= 0.06:
            nedenler.append(f'kulübün en değerli oyuncularından (kadro değerindeki payı %{round(pay * 100)})')
    if yas_neden:
        nedenler.append(f'{yas} yaşında, {yas_neden}')
    return round(puan), etiket, nedenler


def _etiket(puan):
    return next(ad for alt, ad in ZORLUK_ETIKET if puan >= alt)


def sozlesme_uygula(a, bitis, bugun=None, kaynak=None, kiralik=False):
    """Scout adayının transfer zorluğuna sözleşme bitişini ('YYYY-AA-GG' ya da None) ekler; zorluk, etiket, nedenler ve
    gerçekçi hedef puanı yeniden hesaplanır. Sözleşme bilinmiyorsa düzeltme yok. kaynak: nedenlerde yazılır
    (ör. 'Transfermarkt'); kiralik: tarih ana kulübüyle sözleşmesidir."""
    from datetime import date
    bugun = bugun or date.today()
    puan, nedenler = a['zorluk_taban'], list(a['zorluk_neden_taban'])
    a['sozlesme'] = bitis
    if bitis:
        try:
            b = date.fromisoformat(bitis)
        except ValueError:
            b = None
        if b:
            ay = (b.year - bugun.year) * 12 + b.month - bugun.month
            _, fark, neden = next(x for x in SOZLESME_DUZELTME if ay < x[0])
            puan = min(100.0, max(0.0, puan + fark))
            yazi = (f'{"kiralık; ana kulübüyle " if kiralik else ""}sözleşme bitişi {b.month:02d}.{b.year}'
                    + (f' ({kaynak})' if kaynak else ''))
            nedenler.append(f'{yazi}: {neden}' if neden else yazi)
    a['zorluk'] = round(puan)
    a['zorluk_etiket'] = _etiket(puan)
    a['zorluk_neden'] = nedenler
    a['gercekci'] = a['endeks'] * (1 - GERCEKCI_CEZA * puan / 100)
    return a


# takımın bir mevkideki gücü: o mevkide en çok oynayan bu kadar oyuncunun performans endeksi ortalaması (ilk 11'deki yer)
IHTIYAC_KISI = {'kaleci': 1, 'stoper': 2, 'bek': 2, 'orta': 3, 'kanat': 2, 'forvet': 1}


IKI_YAN = {'bek': ('RB', 'LB'), 'kanat': ('RW', 'LW')}  # sağ / sol: biri eksikse ihtiyaç diğer yan


def takim_ihtiyaci(S, takim):
    """Takımın mevki mevki gücü ve ligin ortalamasıyla farkı: [{'grup', 'baslik', 'oyuncular': [(p, endeks)], 'guc',
    'lig_ort', 'fark', 'detay', 'zayif'}], en zayıftan (fark en küçük) güçlüye. Güç: o mevkide en çok oynayan
    IHTIYAC_KISI oyuncunun scout endeksi ortalaması (eksik kişi 40 sayılır: mevkide yeterli oyuncu yok demek). detay: o
    mevkide asıl ihtiyaç olan ayrıntılı mevki (en zayıf oyuncununki; bek ve kanatta bir yan boşsa o yan) ya da None;
    zayif: o oyuncu (boş yanda None)."""
    endeks = scout_endeksi(S)
    baslik = dict(SCOUT_GRUPLARI)

    def guc(t_ad, g):
        oy = sorted((p for p in S.PLY if p['t'].split(' / ')[-1] == t_ad and not p.get('ayrildi') and p['idx'] in endeks
                     and scout_grubu(p) == g), key=lambda p: -p['min'])[:IHTIYAC_KISI[g]]
        degerler = [endeks[p['idx']] for p in oy] + [40.0] * (IHTIYAC_KISI[g] - len(oy))
        return sum(degerler) / len(degerler), [(p, endeks[p['idx']]) for p in oy]
    out = []
    for g in IHTIYAC_KISI:
        g_t, oy = guc(takim, g)
        lig = [guc(t, g)[0] for t in S.T]
        lig_ort = sum(lig) / len(lig)
        detay, zayif = None, None
        yanlar = {p.get('detay') for p, _ in oy}
        bos = [y for y in IKI_YAN.get(g, ()) if y not in yanlar]
        if len(oy) < IHTIYAC_KISI[g] and len(bos) == 1:  # bek / kanatta bir yan boş
            detay = bos[0]
        elif oy and g not in ('kaleci', 'stoper', 'forvet'):
            zayif = min(oy, key=lambda x: x[1])[0]
            detay = zayif.get('detay')
        out.append({'grup': g, 'baslik': baslik[g], 'oyuncular': oy, 'guc': g_t, 'lig_ort': lig_ort, 'fark': g_t - lig_ort,
                    'detay': detay, 'zayif': zayif})
    return sorted(out, key=lambda r: r['fark'])


def scout_adaylari(S, degerler, yas=None, deger_siniri=None, kadro=None):
    """Bir ligin scout adayları: eşik kadar oynamış (performans endeksi olan), yaş aralığındaki (yas=(alt, üst)),
    değer sınırının altındaki oyuncular. degerler: {FotMob oyuncu id: €}; kadro: {takım adı: kadro değeri €} (yoksa
    ligdeki oyuncuların değerlerinin toplamı). Döner: [{'p', 'lig', 'grup', 'endeks', 'deger', 'fp', 'guclu', 'zorluk',
    'zorluk_etiket', 'zorluk_neden', 'gercekci'}]; guclu: mevkidaşlarına göre en yüksek üç yüzdelik [(istatistik,
    yüzdelik)]; zorluk: transfer_zorlugu; gercekci: zorluğa göre indirimli endeks ("gerçekçi hedef" sıralaması). Endeks
    scout_endeksi: harmanlandıysa önceki sezonla (Depo.endeks_harmanla)."""
    endeks = scout_endeksi(S)
    deger = {p['idx']: degerler.get(p.get('fm_id')) for p in S.PLY if degerler.get(p.get('fm_id'))}
    fp = fiyat_performans(S, deger)
    toplam = {}  # kadro değeri bilinmeyen takım için: ligdeki (ayrılmamış) oyuncularının değerleri toplamı
    for p in S.PLY:
        if not p.get('ayrildi') and deger.get(p['idx']):
            ad = p['t'].split(' / ')[-1]
            toplam[ad] = toplam.get(ad, 0) + deger[p['idx']]
    kadro = kadro or {}
    out = []
    for p in S.PLY:
        if p['idx'] not in endeks or p.get('ayrildi'):
            continue
        if yas and (p.get('yas') is None or not yas[0] <= p['yas'] <= yas[1]):
            continue
        dg = deger.get(p['idx'])
        if deger_siniri and (not dg or dg > deger_siniri):
            continue
        grup = scout_grubu(p)
        if not grup:
            continue
        y = S.oyuncu_karti(p)['yuzdelik']
        takim = p['t'].split(' / ')[-1]
        zp, ze, zn = transfer_zorlugu(S, p, dg, kadro.get(takim) or toplam.get(takim))
        out.append({'p': p, 'lig': S.lig, 'yil': S.yil, 'grup': grup, 'endeks': endeks[p['idx']], 'deger': dg,
                    'fp': fp.get(p['idx']), 'guclu': [(ad, pc) for ad, _, pc in sorted(y, key=lambda x: -x[2])[:3]],
                    'zorluk': zp, 'zorluk_etiket': ze, 'zorluk_neden': zn, 'zorluk_taban': zp, 'zorluk_neden_taban': zn,
                    'sozlesme': None, 'gercekci': endeks[p['idx']] * (1 - GERCEKCI_CEZA * zp / 100)})
    return out


def mac_olasiliklari(S, takim, lam, tur='gol', onceki=None, adet=None):
    """90 dk oynarsa maçta en az bir gol (tur='gol') ya da asist atma olasılığı: takımın beklenen golü (asistte golün
    ~%75'i asistlidir), oyuncunun tahmini oranının (oran()) takımın maç başına üretimine oranına göre dağıtılır.
    Adaylar: takımdan ayrılmamış, ligde eşik kadar oynamış ya da önceki sezonlarda en az 5 maçlık süresi olan oyuncular."""
    r = S.tb[takim]
    takimdakiler = [p for p in S.PLY if _takim_indeksi(S, p) == takim]
    onceki = onceki or {}
    oy = [p for p in takimdakiler if not p.get('ayrildi') and p['min'] > 0
          and (p['min'] >= S.min_esik or onceki.get(p['idx'], (0, 0))[1] >= 5)]
    if not oy or not r['O']:
        return []
    # takımın maç başına üretimi, oyuncuların aynı yolla harmanlanmış oranlarından (payların toplamı ~%100 kalsın; az
    # gol atan takımda harmanlanmış oranı ham takım toplamına bölmek payları şişirirdi)
    takim_orani = sum(oran(S, p, tur, onceki) * p['min'] / 90 for p in takimdakiler) / r['O']
    carpan = 1.0 if tur == 'gol' else 0.75  # golün yaklaşık %75'i asistlidir
    out = [(p, 1 - math.exp(-carpan * lam * oran(S, p, tur, onceki) / takim_orani)) for p in oy] if takim_orani > 0 else []
    out.sort(key=lambda x: -x[1])
    return out if adet is None else out[:adet]


def asistciler(S, takim, lam, adet=None, onceki=None):
    """90 dk oynarsa en az bir asist yapma olasılığı (mac_olasiliklari'nın asist karşılığı)."""
    return mac_olasiliklari(S, takim, lam, 'asist', onceki, adet)


HAKEM_ON_MAC = 10  # hakemin kart ortalaması, bu kadar maçlık lig ortalamasıyla harmanlanır (az maçlık hakem uç çıkmasın)


def hakem_carpani(h):
    """Hakemin sertliği: maç başına sarı kartı / lig ortalaması, az maç yönetmiş hakemde lig ortalamasına doğru çekilmiş.
    h: hakem bilgisi ({'mac', 'sariOrt', 'sariLigOrt'}); bilgi yoksa 1."""
    if not h or h.get('sariOrt') is None or not h.get('sariLigOrt'):
        return 1.0
    n = h.get('mac') or 0
    return (n * h['sariOrt'] + HAKEM_ON_MAC * h['sariLigOrt']) / (n + HAKEM_ON_MAC) / h['sariLigOrt']


def kartcilar(S, takim, hakem_carpani=1.0, adet=None):
    """Maçta sarı kart görme olasılığı: oyuncunun 90 dakikadaki sarı kart oranı (ligin tipik oranıyla KART_ON_MAC
    maçlık süre kadar harmanlanır) × maç başına oynadığı süre × hakemin sertliği (hakem_carpani)."""
    oy = [p for p in S.PLY if takim == _takim_indeksi(S, p) and p['min'] >= S.min_esik and not p.get('ayrildi') and p['mp']]
    toplam_dk = sum(p['min'] for p in S.PLY) or 1
    onsel = sum(p['yc'] or 0 for p in S.PLY) / toplam_dk * 90
    out = []
    for p in oy:
        kart_orani = ((p['yc'] or 0) + onsel * KART_ON_MAC) / (p['min'] / 90 + KART_ON_MAC)
        mac_basi_dk = min(90.0, p['min'] / p['mp'])
        out.append((p, 1 - math.exp(-kart_orani * mac_basi_dk / 90 * hakem_carpani)))
    out.sort(key=lambda x: -x[1])
    return out if adet is None else out[:adet]
