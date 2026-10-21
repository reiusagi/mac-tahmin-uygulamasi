"""modeller.py: Poisson tablosu, piyasalar, canlı olasılık, eleme, rastgele sayı üreteci, Poisson kurulumu, skorlama."""
import math

import pytest

from mac_tahmin import modeller as md
from mac_tahmin.modeller import (IY_PAY, MAC_SURESI, Mac, Orman, canli_olasilik, dakika_oku, ilk_yari, js_round,
                                 lojistik_kur, mulberry32, ortalama, piyasalar, pmf, poisson_cek, poisson_kur, skorla,
                                 softmax, sonuc_olasiliklari, toplam, tur_atlama)

LAMBDALAR = [(1.3, 1.1), (0.4, 0.4), (2.2, 0.7), (3.5, 3.1), (4.5, 3.8)]


# ---------------------------------------------------------------- yardımcı sayısal işlevler

def test_js_round_yarimlar_yukari():
    assert js_round(2.5) == 3
    assert js_round(0.5) == 1
    assert js_round(-2.5) == -2  # JS Math.round gibi: .5 her zaman +sonsuza doğru
    assert js_round(2.4999) == 2


def test_toplam_ve_ortalama():
    assert toplam([]) == 0
    assert toplam(x for x in (1, 2, 3.5)) == 6.5
    assert ortalama(iter([2, 4])) == 3


def test_ortalama_bos_liste_hata_verir():
    with pytest.raises(ZeroDivisionError):
        ortalama([])


def test_pmf_toplami_bire_yakin():
    assert sum(pmf(k, 2.5) for k in range(60)) == pytest.approx(1.0, abs=1e-12)
    assert pmf(0, 1.0) == pytest.approx(math.exp(-1))


# ---------------------------------------------------------------- sonuc_olasiliklari

@pytest.mark.parametrize('rho', [0.0, -0.05])
@pytest.mark.parametrize('lh,la', LAMBDALAR)
def test_sonuc_olasiliklari_tablo_ve_1x2_bire_toplanir(lh, la, rho):
    p, hucreler = sonuc_olasiliklari(lh, la, rho)
    assert sum(p) == pytest.approx(1.0, abs=1e-12)
    assert sum(q for _, _, q in hucreler) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize('rho', [0.0, -0.05])
@pytest.mark.parametrize('lh,la', LAMBDALAR)
def test_sonuc_olasiliklari_tablo_1x2_ile_tutarli(lh, la, rho):
    p, hucreler = sonuc_olasiliklari(lh, la, rho)
    ev = sum(q for i, j, q in hucreler if i > j)
    ber = sum(q for i, j, q in hucreler if i == j)
    dep = sum(q for i, j, q in hucreler if i < j)
    assert [ev, ber, dep] == pytest.approx(p, abs=1e-12)


def test_sonuc_olasiliklari_buyuk_lambdada_tablo_genisler():
    _, hucreler = sonuc_olasiliklari(12.0, 11.0)
    en_buyuk = max(i for i, _, _ in hucreler)
    assert en_buyuk >= 18  # 12 beklenen golün çevresi 10x10'a sığmaz
    i, j, _ = max(hucreler, key=lambda c: c[2])
    assert i >= 10 or j >= 10


def test_sonuc_olasiliklari_normal_lambdada_10x10_kalir():
    _, hucreler = sonuc_olasiliklari(1.3, 1.1, -0.05)
    assert len(hucreler) == 100
    assert {i for i, _, _ in hucreler} == set(range(10))


def test_sonuc_olasiliklari_tablo_sirasi_belirli():
    # soldan sağa, i sonra j (eski JS sürümüyle aynı toplama sırası)
    _, hucreler = sonuc_olasiliklari(1.3, 1.1)
    assert [(i, j) for i, j, _ in hucreler[:3]] == [(0, 0), (0, 1), (0, 2)]
    assert [(i, j) for i, j, _ in hucreler[10:12]] == [(1, 0), (1, 1)]


def test_sonuc_olasiliklari_belirlenimci():
    assert sonuc_olasiliklari(1.7, 0.9, -0.05) == sonuc_olasiliklari(1.7, 0.9, -0.05)


@pytest.mark.parametrize('rho', [0.0, -0.05])
def test_sonuc_olasiliklari_esit_lambdada_simetrik(rho):
    p, hucreler = sonuc_olasiliklari(1.4, 1.4, rho)
    assert p[0] == pytest.approx(p[2], abs=1e-12)
    d = {(i, j): q for i, j, q in hucreler}
    for (i, j), q in d.items():
        if (j, i) in d:
            assert q == pytest.approx(d[(j, i)], abs=1e-15)


def test_guclu_ev_sahibi_daha_cok_kazanir():
    p, _ = sonuc_olasiliklari(2.5, 0.6)
    assert p[0] > p[1] > p[2]


def test_dixon_coles_dusuk_skorlari_duzeltir():
    d0 = {(i, j): q for i, j, q in sonuc_olasiliklari(1.3, 1.1)[1]}
    d1 = {(i, j): q for i, j, q in sonuc_olasiliklari(1.3, 1.1, -0.05)[1]}
    assert d1[(0, 0)] > d0[(0, 0)]  # rho < 0: 0-0 artar
    assert d1[(1, 1)] > d0[(1, 1)]
    assert d1[(1, 0)] < d0[(1, 0)]


def test_dixon_coles_negatife_dusmez():
    assert md._dixon_coles(0, 0, 30.0, 30.0, 0.5) == 0.0  # max(0, 1 - 450)
    assert md._dixon_coles(3, 2, 1.0, 1.0, -0.05) == 1.0


# ---------------------------------------------------------------- piyasalar

@pytest.mark.parametrize('lh,la', LAMBDALAR)
def test_piyasalar_tutarli(lh, la):
    p, hucreler = sonuc_olasiliklari(lh, la, -0.05)
    pz = piyasalar(hucreler)
    assert pz['cs_1x'] == pytest.approx(p[0] + p[1], abs=1e-12)
    assert pz['cs_x2'] == pytest.approx(p[1] + p[2], abs=1e-12)
    assert pz['cs_12'] == pytest.approx(p[0] + p[2], abs=1e-12)
    assert pz['ust15'] >= pz['ust25'] >= pz['ust35']
    assert pz['ev_m15'] + pz['dep_p15'] == pytest.approx(1.0, abs=1e-12)
    assert pz['dep_m15'] + pz['ev_p15'] == pytest.approx(1.0, abs=1e-12)
    for k, v in pz.items():
        assert 0.0 <= v <= 1.0, k


def test_piyasalar_kg_ve_gol_yemez():
    _, hucreler = sonuc_olasiliklari(1.5, 1.0)
    pz = piyasalar(hucreler)
    # karşılıklı gol = 1 − (ev gol yemez) − (dep gol yemez) + (0-0)
    p00 = next(q for i, j, q in hucreler if (i, j) == (0, 0))
    assert pz['kg'] == pytest.approx(1 - pz['ev_gol_yemez'] - pz['dep_gol_yemez'] + p00, abs=1e-12)


def test_piyasalar_olceklenmemis_tabloyu_normaliser():
    pz = piyasalar([(0, 0, 0.1), (1, 0, 0.1), (2, 1, 0.2)])  # toplam 0.4
    assert pz['cs_12'] == pytest.approx(0.75)
    assert pz['kg'] == pytest.approx(0.5)


# ---------------------------------------------------------------- ilk yarı

def test_ilk_yari_toplamlar():
    iy = ilk_yari(1.6, 1.1)
    assert sum(iy['p']) == pytest.approx(1.0, abs=1e-12)
    assert 0 < iy['ust15'] < iy['ust05'] < 1
    assert iy['lh'] == pytest.approx(1.6 * IY_PAY)
    assert iy['la'] == pytest.approx(1.1 * IY_PAY)


def test_ilk_yari_golsuz_maci_olasi_buluyor():
    iy = ilk_yari(0.01, 0.01)
    assert iy['p'][1] > 0.99
    assert iy['ust05'] < 0.01


# ---------------------------------------------------------------- dakika_oku

@pytest.mark.parametrize('yazi,beklenen', [
    ("67'", 67), ("45+2'", 47), ("90+5'", 95), ('HT', 45), ('Half-time', 45), ('Devre arası', 45),
    (' 12', 12), ("0'", 0), (None, None), ('', None), ('FT', None), ('abc', None)])
def test_dakika_oku(yazi, beklenen):
    assert dakika_oku(yazi) == beklenen


# ---------------------------------------------------------------- canlı olasılık

def test_canli_olasilik_toplam_bir():
    for dk in (0, 10, 45, 80, 93, 94, 120):
        for skor in ((0, 0), (1, 0), (0, 2), (3, 3)):
            assert sum(canli_olasilik(1.5, 1.1, *skor, dk)) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize('ev,dep,yon', [(2, 1, 0), (1, 1, 1), (0, 3, 2), (0, 0, 1)])
def test_canli_olasilik_uzatmada_neredeyse_kesin_ama_bitmemis(ev, dep, yon):
    """Fonksiyon yalnızca süren maç için çağrılır: 94. dakikadan sonra (90+5') maç bitmemiştir, en az bir dakika kalır."""
    for dk in (MAC_SURESI, MAC_SURESI + 1, MAC_SURESI + 4, 130):
        for once in (None, [0.4, 0.3, 0.3]):
            p = canli_olasilik(1.5, 1.1, ev, dep, dk, once=once)
            assert 0.95 < p[yon] < 1.0
            assert sum(p) == pytest.approx(1.0)


def test_canli_olasilik_uzatma_dakikasi_ilerledikce_kesinlesir():
    assert canli_olasilik(1.5, 1.1, 0, 0, 80)[1] < canli_olasilik(1.5, 1.1, 0, 0, 92)[1] < canli_olasilik(1.5, 1.1, 0, 0, 95)[1]


@pytest.mark.parametrize('lam', [16, 40, 1000, 1e6])
def test_asiri_beklenen_golde_gecerli_dagilim(lam):
    p, hucreler = sonuc_olasiliklari(lam, lam)
    assert sum(p) == pytest.approx(1.0) and sum(h[2] for h in hucreler) == pytest.approx(1.0)
    assert p[0] == pytest.approx(p[2])
    iy = ilk_yari(lam, lam)
    assert sum(iy['p']) == pytest.approx(1.0) and 0 <= iy['ust15'] <= iy['ust05'] <= 1


def test_ilk_yari_yuksek_beklentide_kuyruk_kesilmez():
    """Tablo beklentiye göre genişler: ilk yarıda 5,6 gol beklentisinde 2+ gol olasılığı neredeyse 1."""
    assert ilk_yari(12, 12)['ust15'] > 0.999


def test_canli_olasilik_mac_basi_duz_poisson_ile_ayni():
    # dakika 0, 0-0: maçın tamamı kalıyor (beklenen goller 94/90 ile şişmemeli)
    lh, la = 1.7, 1.0
    assert canli_olasilik(lh, la, 0, 0, 0) == pytest.approx(sonuc_olasiliklari(lh, la)[0], abs=1e-9)


def test_canli_olasilik_mac_basi_maç_oncesi_harmanina_esit():
    once = [0.46, 0.27, 0.27]
    simdi = canli_olasilik(1.7, 1.0, 0, 0, 0, once=once)
    assert simdi == pytest.approx(once, abs=1e-9)


def test_canli_olasilik_duzeltme_sure_ilerledikce_soner():
    once = [0.60, 0.25, 0.15]
    duz = canli_olasilik(1.7, 1.0, 1, 1, 80)
    duzeltmeli = canli_olasilik(1.7, 1.0, 1, 1, 80, once=once)
    fark80 = max(abs(a - b) for a, b in zip(duz, duzeltmeli))
    fark0 = max(abs(a - b) for a, b in zip(canli_olasilik(1.7, 1.0, 0, 0, 0), canli_olasilik(1.7, 1.0, 0, 0, 0, once=once)))
    assert fark80 < fark0 / 4


def test_canli_olasilik_asiri_duzeltme_kirpilir_ve_normalize_olur():
    p = canli_olasilik(1.2, 1.2, 0, 0, 50, once=[0.99, 0.01, 0.0])
    assert all(0.0 <= x <= 1.0 for x in p)
    assert sum(p) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize('once', [[0.6, 0.2, 0.2], [0.9, 0.05, 0.05]])
def test_canli_olasilik_geride_olan_favori_mac_oncesi_duzeltmesiyle_sismez(once):
    # 30. dakikada 0-3 geride: maç öncesi ne kadar favori olursa olsun galibiyet ihtimali küçük kalmalı, beraberlik sıfırlanmamalı
    duz = canli_olasilik(1.7, 1.0, 0, 3, 30)
    p = canli_olasilik(1.7, 1.0, 0, 3, 30, once=once)
    assert p[0] < (0.05 if once[0] < 0.7 else 0.10)  # eski toplamsal düzeltmede %9 ve %27 çıkıyordu
    assert p[1] > 0.0 and p[0] > 0.0
    assert p[0] < 5 * duz[0]  # düzeltme skoru yok saymaz: düz hesabın birkaç katını aşmaz
    assert sum(p) == pytest.approx(1.0, abs=1e-12)


def test_canli_olasilik_geride_olan_favorinin_sansi_dakika_ilerledikce_azalir():
    once = [0.6, 0.2, 0.2]
    sans = [canli_olasilik(1.7, 1.0, 0, 3, dk, once=once)[0] for dk in (10, 30, 60, 85)]
    assert sans == sorted(sans, reverse=True)


def test_canli_olasilik_gol_atan_takimin_sansi_artar():
    p0 = canli_olasilik(1.5, 1.5, 0, 0, 30)
    p1 = canli_olasilik(1.5, 1.5, 1, 0, 30)
    assert p1[0] > p0[0] and p1[2] < p0[2]


def test_canli_olasilik_ayni_skorda_gec_dakikada_onde_olan_daha_emin():
    assert canli_olasilik(1.5, 1.5, 1, 0, 80)[0] > canli_olasilik(1.5, 1.5, 1, 0, 40)[0]


# ---------------------------------------------------------------- eleme

def test_tur_atlama_tek_mac_iki_yon_bire_toplanir():
    for lh, la in ((1.8, 0.9), (1.1, 1.1), (0.6, 2.4)):
        assert tur_atlama(lh, la) + tur_atlama(la, lh) == pytest.approx(1.0, abs=1e-9)


def test_tur_atlama_esit_lambda_yari_yariya():
    assert tur_atlama(1.3, 1.3) == pytest.approx(0.5, abs=1e-9)


def test_tur_atlama_buyuk_ilk_mac_avantaji():
    # 3-0'lık ilk maç: rakip üç farkla kazanırsa bile uzatma var (ev sahibi lehine yarı yarıya), yine de çok öndedir
    assert tur_atlama(1.2, 1.2, onceki=(3, 0)) > 0.95
    assert tur_atlama(2.0, 0.7, onceki=(3, 0)) > 0.99
    assert tur_atlama(1.2, 1.2, onceki=(4, 0)) > 0.99
    assert tur_atlama(1.2, 1.2, onceki=(0, 4)) < 0.01
    assert tur_atlama(1.2, 1.2, onceki=(3, 0)) + tur_atlama(1.2, 1.2, onceki=(0, 3)) == pytest.approx(1.0, abs=1e-9)


def test_tur_atlama_ilk_mac_simetrik_kurulumda_yari_yariya():
    assert tur_atlama(1.3, 1.3, rovans=(1.3, 1.3)) == pytest.approx(0.5, abs=1e-9)
    assert 0 < tur_atlama(1.5, 1.0, rovans=(1.1, 1.6)) < 1


def test_tur_atlama_ev_sahibi_avantajli_ilk_maçta_onde():
    assert tur_atlama(2.0, 0.8, rovans=(0.8, 2.0)) > 0.5


# ---------------------------------------------------------------- rastgele sayı üreteci

def _mulberry32_referans(tohum):
    """JS'teki mulberry32'nin bağımsız yazımı (32 bit işaretsiz aritmetik)."""
    m = 0xFFFFFFFF
    a = tohum & m

    def r():
        nonlocal a
        a = (a + 0x6D2B79F5) & m
        t = ((a ^ (a >> 15)) * (1 | a)) & m
        t = (t ^ ((t + (((t ^ (t >> 7)) * (61 | t)) & m)) & m)) & m
        return ((t ^ (t >> 14)) & m) / 4294967296
    return r


@pytest.mark.parametrize('tohum', [0, 1, 42, 2026, 0x7FFFFFFF, 0xFFFFFFFF, -1, 123456789])
def test_mulberry32_referans_uygulamayla_ayni(tohum):
    r, ref = mulberry32(tohum), _mulberry32_referans(tohum)
    assert [r() for _ in range(50)] == [ref() for _ in range(50)]


def test_mulberry32_belirlenimci_ve_aralikta():
    a, b = mulberry32(7), mulberry32(7)
    xs = [a() for _ in range(2000)]
    assert xs == [b() for _ in range(2000)]
    assert all(0.0 <= x < 1.0 for x in xs)
    assert len(set(xs)) > 1990
    assert abs(sum(xs) / len(xs) - 0.5) < 0.03
    assert xs != [mulberry32(8)() for _ in range(2000)]


@pytest.mark.parametrize('x,beklenen', [
    (0, 0), (1, 1), (0x7FFFFFFF, 2147483647), (0x80000000, -2147483648), (0xFFFFFFFF, -1), (-1, -1),
    (2 ** 32, 0), (2 ** 32 + 5, 5), (-2 ** 31, -2147483648), (-2 ** 31 - 1, 2147483647)])
def test_i32(x, beklenen):
    assert md._i32(x) == beklenen


@pytest.mark.parametrize('a,b,beklenen', [
    (0, 12345, 0), (3, 4, 12), (-1, -1, 1), (0x7FFFFFFF, 2, -2), (0xFFFF, 0xFFFF, -131071),
    (0x80000000, 2, 0), (-5, 3, -15), (0xFFFFFFFF, 0xFFFFFFFF, 1)])
def test_imul(a, b, beklenen):
    assert md._imul(a, b) == beklenen


def test_poisson_cek_ortalamasi():
    r = mulberry32(5)
    xs = [poisson_cek(r, 2.0) for _ in range(4000)]
    assert abs(sum(xs) / len(xs) - 2.0) < 0.1
    assert min(xs) >= 0


# ---------------------------------------------------------------- Poisson kurulumu

def _lig(n_tur=6):
    """0 numaralı takım çok gol atar, 3 numaralı çok gol yer; 4 takım."""
    skorlar = {(0, 1): (4, 0), (0, 2): (3, 1), (0, 3): (5, 1), (1, 2): (1, 1), (1, 3): (2, 0), (2, 3): (2, 1),
               (1, 0): (0, 2), (2, 0): (0, 3), (3, 0): (0, 4), (2, 1): (1, 0), (3, 1): (1, 2), (3, 2): (0, 1)}
    M = []
    for tur in range(n_tur):
        for (h, a), (hg, ag) in skorlar.items():
            M.append(Mac(f'2026-0{1 + tur % 9}-01', h, a, hg, ag))
    return M


def test_poisson_kur_guc_ortalamasi_bir():
    pz = poisson_kur(_lig(), 4)
    assert ortalama(pz.att) == pytest.approx(1.0, abs=1e-9)
    assert ortalama(pz.de) == pytest.approx(1.0, abs=1e-9)


def test_poisson_kur_guclu_hucum_buyuk_att():
    pz = poisson_kur(_lig(), 4)
    assert pz.att[0] == max(pz.att)
    assert pz.de[3] == max(pz.de)  # en çok gol yiyen en zayıf savunma
    assert pz.mu > 0 and pz.hm > 0
    lh, la = pz.lambdalar(0, 3)
    assert lh > la > 0


def test_poisson_kur_bos_mac_listesi_cokmez():
    pz = poisson_kur([], 3)
    assert pz.att == [1.0, 1.0, 1.0] and pz.de == [1.0, 1.0, 1.0]
    assert pz.lambdalar(0, 1)[0] > 0


def test_poisson_kur_agirlik_eski_maci_azaltir():
    M = _lig(2)
    esit = poisson_kur(M, 4)
    agirlikli = poisson_kur(M, 4, [0.01] * (len(M) // 2) + [1] * (len(M) - len(M) // 2))
    assert esit.att != agirlikli.att


def test_poisson_kur_yeni_takim_onbilgiye_cekilir():
    M = [Mac('2026-01-01', 0, 1, 3, 0), Mac('2026-01-08', 1, 0, 0, 3)]
    normal = poisson_kur(M, 3)
    yeni = poisson_kur(M, 3, yeni=[False, False, True])
    assert yeni.att[2] != normal.att[2] or yeni.de[2] != normal.de[2]


def test_poisson_kur_xg_payi_golu_xg_ile_karistirir():
    M = [Mac('2026-01-01', 0, 1, 4, 0, 1.0, 1.0), Mac('2026-01-08', 1, 0, 0, 4, 1.0, 1.0)]
    assert poisson_kur(M, 2, xg_pay=0.5).att[0] < poisson_kur(M, 2).att[0]  # 4 gol yerine 2,5 gol sayılır
    assert ortalama(poisson_kur(M, 2, xg_pay=0.5).att) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------- lojistik regresyon ve orman

def test_softmax_toplam_bir():
    p = softmax([[1.0, 0.0, 0.2], [0.0, 1.0, -0.1], [0.5, 0.5, 0.0]], [2.0, -1.0])
    assert sum(p) == pytest.approx(1.0)
    assert all(x > 0 for x in p)


def _ayrik_veri():
    X, Y = [], []
    for i in range(60):
        k = i % 3
        X.append([float(k) * 3 + (i % 5) * 0.1, float(-k) + (i % 7) * 0.05, (i % 4) * 0.3, float(k) + (i % 3) * 0.01])
        Y.append(k)
    return X, Y


def test_lojistik_kur_ayrik_veriyi_ogrenir():
    X, Y = _ayrik_veri()
    W = lojistik_kur(X, Y, adim=300)
    dogru = sum(1 for x, y in zip(X, Y) if softmax(W, x).index(max(softmax(W, x))) == y)
    assert dogru / len(X) > 0.9


def test_orman_belirlenimci_ve_ogrenir():
    X, Y = _ayrik_veri()
    o1, o2 = Orman(X, Y, agac=20), Orman(X, Y, agac=20)
    assert o1.tahmin(X[0]) == o2.tahmin(X[0])
    dogru = sum(1 for x, y in zip(X, Y) if o1.tahmin(x).index(max(o1.tahmin(x))) == y)
    assert dogru / len(X) > 0.9
    assert sum(o1.tahmin(X[1])) == pytest.approx(1.0)
    assert sum(o1.onem) == pytest.approx(1.0)


def test_orman_ucten_az_ozellikle_sonsuz_donguye_girmez():
    import threading
    X = [[float(i % 3), float(i % 2)] for i in range(40)]
    Y = [i % 3 for i in range(40)]
    sonuc = []
    t = threading.Thread(target=lambda: sonuc.append(Orman(X, Y, agac=5)), daemon=True)
    t.start()
    t.join(10)
    assert sonuc, 'Orman iki özellikle takıldı (mtry > özellik sayısı)'


# ---------------------------------------------------------------- skorlama

def test_skorla_mukemmel_tahmin():
    s = skorla([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 1, 2])
    assert s['dogruluk'] == 1.0
    assert s['log_loss'] == pytest.approx(0.0, abs=1e-12)
    assert s['brier'] == pytest.approx(0.0, abs=1e-12)


def test_skorla_tamamen_yanlis_tahmin():
    s = skorla([[1, 0, 0], [0, 1, 0]], [2, 0])
    assert s['dogruluk'] == 0.0
    assert s['log_loss'] == pytest.approx(-math.log(1e-9))  # log(0) yerine 1e-9 tabanı
    assert s['brier'] == pytest.approx(2.0)


def test_skorla_esit_olasilik():
    s = skorla([[1 / 3, 1 / 3, 1 / 3]] * 3, [0, 1, 2])
    assert s['log_loss'] == pytest.approx(math.log(3))
    assert s['brier'] == pytest.approx(2 / 3)
