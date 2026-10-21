"""sezon.py: puan durumu ve ligin eşitlik kuralı, sezon simülasyonu, dakika eşiği, tahmin ve küçük yardımcılar."""
import json

import pytest
from yardimci import cift_devre, ham_sezon, sezon_kur

from mac_tahmin import sezon as sz
from mac_tahmin.modeller import Mac
from mac_tahmin.sezon import LIGLER, Sezon

H2H_LIGLERI = {'La_liga', 'Serie_A', 'Super_Lig', 'Primeira_Liga', 'Greek_Super_League', 'Saudi_Pro_League'}
DIGER_LIGLER = [l[0] for l in LIGLER if l[0] not in H2H_LIGLERI and l[0] != 'Brasileirao']

# A ile B puanda eşit (6); A'nın averajı iyi, B ikili maçı kazandı. C ile D de puanda eşit (1), ikili maç berabere.
TAKIMLAR = ['A', 'B', 'C', 'D']
ESIT_PUAN = [('A', 'B', 0, 1), ('A', 'C', 3, 0), ('A', 'D', 3, 0), ('B', 'C', 1, 0), ('C', 'D', 0, 0)]


def sira(S):
    return [r['name'] for r in S.tablo]


# ---------------------------------------------------------------- puan durumu

def test_puan_galibiyet_uc_beraberlik_bir():
    S = sezon_kur(TAKIMLAR, [('A', 'B', 2, 0), ('C', 'D', 1, 1), ('B', 'C', 0, 3)])
    r = {x['name']: x for x in S.tb}
    assert (r['A']['P'], r['A']['G'], r['A']['B'], r['A']['M']) == (3, 1, 0, 0)
    assert (r['B']['P'], r['B']['G'], r['B']['B'], r['B']['M']) == (0, 0, 0, 2)
    assert (r['C']['P'], r['C']['G'], r['C']['B'], r['C']['M']) == (4, 1, 1, 0)
    assert (r['D']['P'], r['D']['B']) == (1, 1)
    assert r['A']['AV'] == 2 and r['B']['AV'] == -5 and r['C']['AV'] == 3
    assert r['C']['O'] == 2 and r['C']['AG'] == 4 and r['C']['YG'] == 1


def test_puan_toplami_tutarli():
    S = sezon_kur(TAKIMLAR, cift_devre(TAKIMLAR, lambda h, a, t: ((ord(h) + t) % 3, (ord(a) * 2 + t) % 3)))
    for r in S.tb:
        assert r['P'] == 3 * r['G'] + r['B']
        assert r['O'] == r['G'] + r['B'] + r['M']
    assert sum(r['AG'] for r in S.tb) == sum(r['YG'] for r in S.tb)
    assert sum(r['AV'] for r in S.tb) == 0


def test_bos_sezon_cokmez():
    S = sezon_kur(TAKIMLAR, [])
    assert [r['P'] for r in S.tb] == [0, 0, 0, 0]
    assert sira(S) == TAKIMLAR


# ---------------------------------------------------------------- eşitlik kuralı

def test_esitlik_kurali_lig_listesi():
    assert {k for k, v in sz.ESITLIK_KURALI.items() if v == 'ikili'} == H2H_LIGLERI
    assert {k for k, v in sz.ESITLIK_KURALI.items() if v == 'galibiyet'} == {'Brasileirao'}
    assert set(sz.ESITLIK_KURALI) <= {l[0] for l in LIGLER}
    assert sz.esitlik_kurali('EPL') == 'averaj'
    assert sz.esitlik_kurali(None) == 'averaj'
    assert sz.esitlik_kurali('Brasileirao') == 'galibiyet'


@pytest.mark.parametrize('lig', sorted(H2H_LIGLERI))
def test_ikili_maç_kuralli_ligde_ikili_mac_averajdan_once(lig):
    S = sezon_kur(TAKIMLAR, ESIT_PUAN, anahtar=lig)
    assert sira(S) == ['B', 'A', 'D', 'C']  # B ikili maçı kazandı; C-D ikilisi berabere, D genel averajda önde


@pytest.mark.parametrize('lig', DIGER_LIGLER + [None])
def test_averaj_kuralli_ligde_averaj_once(lig):
    S = sezon_kur(TAKIMLAR, ESIT_PUAN, anahtar=lig)
    assert sira(S) == ['A', 'B', 'D', 'C']


def test_brasileirao_galibiyet_sayisi_averajdan_once():
    # X üç beraberlikle 3 puan (averaj 0), Y bir galibiyet ve iki yenilgiyle 3 puan (averaj -3)
    oy = [('X', 'A', 0, 0), ('X', 'B', 0, 0), ('X', 'C', 0, 0), ('Y', 'A', 1, 0), ('B', 'Y', 2, 0), ('C', 'Y', 3, 0)]
    T = ['X', 'Y', 'A', 'B', 'C']
    bras, epl = sezon_kur(T, oy, anahtar='Brasileirao'), sezon_kur(T, oy, anahtar='EPL')
    assert sira(bras).index('Y') < sira(bras).index('X')
    assert sira(epl).index('X') < sira(epl).index('Y')


def _satir(i, P, AV, AG, G=0):
    return dict(i=i, name='ABCDE'[i], P=P, AV=AV, AG=AG, G=G)


def test_tablo_sirala_uc_takimli_grupta_mini_tablo():
    # X, Y, Z puanda eşit. Genel averajda X en iyi; ama ikili maçlarda Y: Y-X 3-0, X-Z 1-0, Z-Y 0-0
    tb = [_satir(0, 10, 9, 20), _satir(1, 10, 2, 8), _satir(2, 10, 1, 9)]
    M = [Mac('2026-08-01', 1, 0, 3, 0), Mac('2026-08-08', 0, 2, 1, 0), Mac('2026-08-15', 2, 1, 0, 0),
         Mac('2026-08-22', 0, 3, 5, 0)]  # son maç grubun dışındaki takımla: sayılmaz
    assert [r['i'] for r in sz.tablo_sirala(tb, M, 'ikili')] == [1, 0, 2]
    assert [r['i'] for r in sz.tablo_sirala(tb, M, 'averaj')] == [0, 1, 2]


def test_tablo_sirala_donguda_ikili_esitse_genel_averaja_duser():
    # X>Y, Y>Z, Z>X (hepsi 1-0): ikili puan ve averaj eşit -> genel averaj, sonra atılan gol
    tb = [_satir(0, 9, 4, 10), _satir(1, 9, 6, 9), _satir(2, 9, 6, 12)]
    M = [Mac('2026-08-01', 0, 1, 1, 0), Mac('2026-08-08', 1, 2, 1, 0), Mac('2026-08-15', 2, 0, 1, 0)]
    assert [r['i'] for r in sz.tablo_sirala(tb, M, 'ikili')] == [2, 1, 0]


def test_tablo_sirala_puani_yuksek_olan_ikili_maçtan_bagimsiz_once():
    tb = [_satir(0, 12, -3, 5), _satir(1, 9, 8, 20)]
    M = [Mac('2026-08-01', 1, 0, 5, 0)]
    assert [r['i'] for r in sz.tablo_sirala(tb, M, 'ikili')] == [0, 1]


def test_tablo_sirala_galibiyet_kurali():
    tb = [_satir(0, 3, 0, 0, G=0), _satir(1, 3, -3, 1, G=1), _satir(2, 3, -3, 3, G=1)]
    assert [r['i'] for r in sz.tablo_sirala(tb, [], 'galibiyet')] == [2, 1, 0]


def test_tablo_sirala_girdi_listesini_degistirmez():
    tb = [_satir(0, 3, 0, 0), _satir(1, 6, 0, 0)]
    kopya = [dict(r) for r in tb]
    sz.tablo_sirala(tb, [], 'averaj')
    assert tb == kopya


# ---------------------------------------------------------------- simülasyon

def _tam_bitmis(anahtar):
    return sezon_kur(TAKIMLAR, ESIT_PUAN, anahtar=anahtar)


def _dagilim(S, **kw):
    return {r['name']: r['dist'] for r in S.simulasyon(**kw)}


def test_simulasyon_biten_sezonda_kesin_ve_kural_tablosuyla_ayni():
    for anahtar in ('La_liga', None, 'Brasileirao'):
        S = _tam_bitmis(anahtar)
        d = _dagilim(S, N=300)
        for k, ad in enumerate(sira(S)):
            assert d[ad][k] == 1.0, (anahtar, ad, k)


def test_simulasyon_ikili_kuralda_B_A_nin_onunde():
    d = _dagilim(_tam_bitmis('Serie_A'), N=200)
    assert d['B'][0] == 1.0 and d['A'][1] == 1.0
    d = _dagilim(_tam_bitmis('EPL'), N=200)
    assert d['A'][0] == 1.0 and d['B'][1] == 1.0


def test_simulasyon_brasileirao_galibiyet():
    oy = [('X', 'A', 0, 0), ('X', 'B', 0, 0), ('X', 'C', 0, 0), ('Y', 'A', 1, 0), ('B', 'Y', 2, 0), ('C', 'Y', 3, 0)]
    S = sezon_kur(['X', 'Y', 'A', 'B', 'C'], oy, anahtar='Brasileirao')
    d = _dagilim(S, N=200)
    assert sira(S).index('Y') < sira(S).index('X')
    k = {ad: v.index(1.0) for ad, v in d.items()}
    assert k['Y'] < k['X']


def test_simulasyon_buyuk_gol_sayilarinda_anahtar_tasmaz():
    # P: 3 puan, averaj +1, 1500 gol; Q: 3 puan, averaj +2, 2 gol -> averaj kuralında Q önde
    # X: 4 puan, averaj -1499; Y: 3 puan, averaj +1 -> puanı fazla olan X önde (eski bileşik anahtar ikisini karıştırıyordu)
    oy = [('P', 'R', 1500, 1499), ('Q', 'S', 2, 0), ('X', 'Y2', 1, 0), ('X', 'Z', 0, 0), ('Z', 'X', 1500, 0), ('Y', 'Z', 1, 0)]
    T = ['P', 'Q', 'R', 'S', 'X', 'Y', 'Y2', 'Z']
    S = sezon_kur(T, oy)
    d = _dagilim(S, N=100)
    konum = {ad: v.index(1.0) for ad, v in d.items()}
    assert konum['Q'] < konum['P']
    puan = {r['name']: r['P'] for r in S.tb}
    assert puan['X'] == 4 and puan['Y'] == 3 and puan['P'] == puan['Q'] == 3
    assert konum['X'] < konum['Y']


def _devam_eden():
    T = ['A', 'B', 'C', 'D']
    oy = cift_devre(T, lambda h, a, t: ((ord(h) + t) % 3, (ord(a) + 2 * t) % 3))[:6]
    kalan = [(h, a) for h in T for a in T if h != a][:8]
    return sezon_kur(T, oy, kalan, anahtar='La_liga')


def test_simulasyon_dagilimlar_bire_toplanir():
    S = _devam_eden()
    out = S.simulasyon(N=500)
    n = len(S.T)
    assert len(out) == n
    for r in out:
        assert sum(r['dist']) == pytest.approx(1.0, abs=1e-12)
    for k in range(n):  # her sırada tam bir takım
        assert sum(r['dist'][k] for r in out) == pytest.approx(1.0, abs=1e-12)
    # beklenen puan: şimdiki puan + kalan maçlardan (en az 0, en çok 3 puan/maç)
    for r in out:
        kalan_mac = sum(1 for m in S.U if r['i'] in (m.h, m.a))
        assert r['P'] <= r['exp'] <= r['P'] + 3 * kalan_mac + 1e-9


def test_simulasyon_sabit_tohumla_belirlenimci():
    assert _devam_eden().simulasyon(N=400) == _devam_eden().simulasyon(N=400)


def test_simulasyon_sabit_sonuclar_etkili():
    S = _devam_eden()
    m = S.U[0]
    ev_kazanir = {r['name']: r['exp'] for r in S.simulasyon(N=400, sabit={(m.h, m.a): (5, 0)})}
    dep_kazanir = {r['name']: r['exp'] for r in S.simulasyon(N=400, sabit={(m.h, m.a): (0, 5)})}
    assert ev_kazanir[S.T[m.h]] > dep_kazanir[S.T[m.h]]
    assert ev_kazanir[S.T[m.a]] < dep_kazanir[S.T[m.a]]


def test_simulasyon_kalan_mac_yoksa_beklenen_puan_gercek():
    S = _tam_bitmis('EPL')
    for r in S.simulasyon(N=50):
        assert r['exp'] == r['P']


# ---------------------------------------------------------------- dakika eşiği

def test_min_esik_tam_sezon_38_maçta_900():
    T = [f'T{i}' for i in range(20)]
    S = sezon_kur(T, cift_devre(T, lambda h, a, t: (1, 0) if h < a else (0, 1)))
    assert max(r['O'] for r in S.tb) == 38
    assert S.min_esik == 900


def test_min_esik_biten_34_maçlik_sezon_tam_esige_ulasir():
    T = [f'T{i}' for i in range(18)]
    S = sezon_kur(T, cift_devre(T, lambda h, a, t: (1, 0) if h < a else (0, 1)))
    assert max(r['O'] for r in S.tb) == 34
    assert S.min_esik == 900  # eskiden 34/38'e göre 800


def test_min_esik_30_maçlik_ligde_yarida_450():
    T = [f'T{i}' for i in range(16)]
    tam = cift_devre(T, lambda h, a, t: (1, 0) if h < a else (0, 1))  # 16 takım: 30 maç/takım
    yarim, kalan = tam[:len(tam) // 2], [(h, a) for h, a, *_ in tam[len(tam) // 2:]]
    S = sezon_kur(T, yarim, kalan)
    assert S.min_esik == 450  # 15 / 30 maç -> yarı


def test_min_esik_en_az_90():
    assert sezon_kur(TAKIMLAR, [('A', 'B', 1, 0)], [('B', 'A')] * 40).min_esik == 90


def test_min_esik_38_maç_yarida_450_kalan_listesi_olmadan_da():
    T = [f'T{i}' for i in range(20)]
    tam = cift_devre(T, lambda h, a, t: (1, 0) if h < a else (0, 1))
    S = sezon_kur(T, tam[:190], [(h, a) for h, a, *_ in tam[190:]])
    assert S.min_esik == 450


# ---------------------------------------------------------------- tahmin

def test_tahmin_olasiliklari_tutarli():
    S = _devam_eden()
    t = S.tahmin(0, 1)
    assert sum(t['p']) == pytest.approx(1.0, abs=1e-9)
    assert sum(c for _, _, c in t['hucreler']) == pytest.approx(1.0, abs=1e-9)
    assert t['p'] == pytest.approx(S.olasilik(0, 1), abs=1e-12)
    for k, bolge in enumerate((lambda i, j: i > j, lambda i, j: i == j, lambda i, j: i < j)):
        assert sum(c for i, j, c in t['hucreler'] if bolge(i, j)) == pytest.approx(t['p'][k], abs=1e-9)
    assert t['skorlar'] == sorted(t['hucreler'], key=lambda c: -c[2])[:5]


def test_tahmin_oyuncusuz_sezonda_golcu_listesi_bos():
    t = _devam_eden().tahmin(0, 1)
    assert t['golcu_ev'] == [] and t['golcu_dep'] == []


def test_takim_bul():
    S = _devam_eden()
    assert S.takim_bul('a') == 0
    with pytest.raises(ValueError):
        S.takim_bul('Yok')


def test_kadro_degeri_beklenen_golu_egitir():
    S = _devam_eden()
    onceki = S.lambdalar(0, 1)
    S.deger_ata({'A': 900e6, 'B': 100e6, 'C': 300e6, 'D': 300e6})
    sonra = S.lambdalar(0, 1)
    assert sonra[0] > onceki[0] and sonra[1] < onceki[1]
    assert sonra[0] / onceki[0] <= sz.DEGER_TAVAN + 1e-9


# ---------------------------------------------------------------- küçük yardımcılar

def test_ham_oku(tmp_path):
    (tmp_path / 'EPL-2026.json').write_text(json.dumps(ham_sezon(TAKIMLAR, ESIT_PUAN)), encoding='utf-8')
    assert sz.ham_oku(tmp_path, 'EPL', 2026)['t'] == TAKIMLAR
    with pytest.raises(FileNotFoundError):
        sz.ham_oku(tmp_path, 'EPL', 2020)


def test_lig_ve_sezon_etiketi():
    assert sz.lig('EPL')[1] == 'Premier League'
    with pytest.raises(KeyError):
        sz.lig('YOK')
    assert sz.sezon_etiketi(2026, 'Brasileirao') == '2026'
    assert sz.sezon_etiketi(2026, 'EPL') == '2026/27'
    assert sz.sezon_etiketi(2099) == '2099/00'


def test_sadelestir():
    assert sz.sadelestir('Fenerbahçe') == 'fenerbahce'
    assert sz.sadelestir('İstanbul ILIK') == 'istanbul ilik'


def test_yas_hesap():
    bugun = sz.date(2026, 10, 21)
    assert sz.yas_hesap('2000-10-21', 2026, bugun=bugun) == 26
    assert sz.yas_hesap('2000-10-22', 2026, bugun=bugun) == 25
    assert sz.yas_hesap('0001-01-01', 2026) is None
    assert sz.yas_hesap(None, 2026) is None
    assert sz.yas_hesap('2000-06-30', 2024) == 24  # geçmiş sezon: 1 Ocak 2025
    assert sz.yas_hesap('2000-06-30', 2024, takvim_yili=True) == 24  # 1 Temmuz 2024


def test_gol_dagilimi_toplami_bir():
    assert sum(sz.gol_dagilimi(1.4, [0.3, 0.5, 0.1, 0.4, 0.1])) == pytest.approx(1.0)
    assert sum(sz.gol_dagilimi(1.4)) == pytest.approx(1.0, abs=1e-3)
    assert sz.gol_dagilimi(0.0, []) == [1.0]


def test_hak_edilen_puan_simetrik():
    out = sz.hak_edilen_puan([('X', 'Y', 1, 1, 1.2, 1.2)])
    assert out['X']['xP'] == pytest.approx(out['Y']['xP'], abs=1e-9)
    assert out['X']['P'] == out['Y']['P'] == 1
    assert 1.0 < out['X']['xP'] < 1.6


def test_hic_gol_atilmamis_sezon_cokmez():
    S = sezon_kur(TAKIMLAR, [('A', 'B', 0, 0), ('C', 'D', 0, 0), ('A', 'C', 0, 0)])
    assert [r['P'] for r in S.tb] == [2, 1, 2, 1]
    assert all(r['hucum'] == 0 for r in S.reyting)
