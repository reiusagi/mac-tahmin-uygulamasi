"""avrupa.py: lig aşaması eşitlik sırası (UEFA kuralları) ve kupa simülasyonunun tutarlılığı (uydurma veriyle)."""
import numpy as np
import pytest

from mac_tahmin import avrupa


# ---------------------------------------------------------------- UEFA lig aşaması sırası

def _sirala(**kw):
    """Tek simülasyonluk (1 x n) dizilerle avrupa.lig_sirasi; verilmeyen ölçüt hepsi eşit."""
    n = len(next(iter(kw.values())))
    z = lambda k: np.array([kw.get(k, [0] * n)])  # noqa: E731
    return avrupa.lig_sirasi(z('pts'), z('av'), z('gf'), z('gf_dep'), z('gal'), z('gal_dep'),
                             np.array([kw.get('kura', [0.0] * n)]))[0].tolist()


def test_lig_sirasi_puan_once():
    assert _sirala(pts=[3, 9, 6], av=[10, -10, 0]) == [1, 2, 0]


def test_lig_sirasi_averaj_sonra_atilan_gol():
    assert _sirala(pts=[6, 6, 6], av=[1, 3, 3], gf=[9, 4, 8]) == [2, 1, 0]


def test_lig_sirasi_deplasmanda_atilan_gol():
    assert _sirala(pts=[6, 6], av=[2, 2], gf=[8, 8], gf_dep=[3, 5]) == [1, 0]


def test_lig_sirasi_galibiyet_sonra_deplasman_galibiyeti():
    assert _sirala(pts=[6, 6], av=[2, 2], gf=[8, 8], gf_dep=[3, 3], gal=[1, 2]) == [1, 0]
    assert _sirala(pts=[6, 6], av=[2, 2], gf=[8, 8], gf_dep=[3, 3], gal=[2, 2], gal_dep=[0, 1]) == [1, 0]


def test_lig_sirasi_hicbir_olcut_ayirmazsa_kura():
    assert _sirala(pts=[6, 6], kura=[0.7, 0.2]) == [1, 0]
    assert _sirala(pts=[6, 6], kura=[0.2, 0.7]) == [0, 1]


def test_lig_sirasi_buyuk_sayilarda_tasmaz():
    # eski bileşik anahtar (puan·1e6 + (averaj+500)·1e3 + gol) averajı 1000'in üstündeki gol sayılarıyla karıştırırdı
    assert _sirala(pts=[3, 3], av=[2, 1], gf=[2, 5000]) == [0, 1]
    assert _sirala(pts=[4, 3], av=[-5000, 5], gf=[0, 0]) == [0, 1]


def test_lig_sirasi_her_simulasyon_icin_ayri_siralar():
    s = avrupa.lig_sirasi(np.array([[3, 1], [0, 5]]), np.zeros((2, 2), int), np.zeros((2, 2), int),
                          np.zeros((2, 2), int), np.zeros((2, 2), int), np.zeros((2, 2), int), np.zeros((2, 2)))
    assert s.tolist() == [[0, 1], [1, 0]]


# ---------------------------------------------------------------- uydurma kupa verisi

N_TAKIM = 36


class _Elo:
    a, b = 0.25, 0.6
    ad = {}

    def puan(self, t):
        return 1500 + 10 * (t % 7)


def _kupa(kalan_sayisi=6, bitmis=False):
    """36 takım, her takım 8 maç (i ile i+1..i+4); son kalan_sayisi maç oynanmadı. Eleme turları belli değil."""
    maclar, kalan = [], 0
    for i in range(N_TAKIM):
        for k in range(1, 5):
            j = (i + k) % N_TAKIM
            oynandi = bitmis or len(maclar) < N_TAKIM * 4 - kalan_sayisi
            kalan += not oynandi
            maclar.append([1000 + len(maclar), f'2026-01-{1 + k:02d}T20:00:00Z', i + 1, j + 1, f'T{i + 1}', f'T{j + 1}',
                           (i * 3 + k) % 4 if oynandi else None, (j + k) % 3 if oynandi else None, str(k), False, False])
    tablo = [[t + 1, f'T{t + 1}', 8, 0, 0, 0, '0-0', 0, 0] for t in range(N_TAKIM)]
    return {'tablo': [('', tablo)], 'maclar': maclar, 'eleme': []}, kalan


def _sim(**kw):
    S, kalan = _kupa(**kw)
    v = {'kupalar': {'42': {'2025/2026': S}}}
    return avrupa.simulasyon(v, _Elo(), 42, '2025/2026', N=60, tohum=7), kalan


def test_simulasyon_lig_asamasi_dagilimlari_tutarli():
    out, kalan = _sim()
    assert out['kalan_mac'] == kalan == 6
    t = out['takimlar']
    assert len(t) == N_TAKIM
    for r in t:
        assert r['ilk8'] + r['playoff'] + r['elendi'] == pytest.approx(1.0, abs=1e-9)
    assert sum(r['ilk8'] for r in t) == pytest.approx(8.0, abs=1e-9)
    assert sum(r['playoff'] for r in t) == pytest.approx(16.0, abs=1e-9)
    assert sum(r['elendi'] for r in t) == pytest.approx(12.0, abs=1e-9)
    assert sum(r['turlar'][-1] for r in t) == pytest.approx(1.0, abs=1e-9)  # tek şampiyon


def test_simulasyon_ayni_tohumla_ayni_sonuc():
    a, _ = _sim()
    b, _ = _sim()
    assert [r['sira'] for r in a['takimlar']] == [r['sira'] for r in b['takimlar']]
    assert a['ornek'] == b['ornek']


def test_simulasyon_lig_asamasi_bitmisse_fotmob_sirasi():
    out, kalan = _sim(bitmis=True)
    assert kalan == 0 and out['kalan_mac'] == 0
    assert out['ornek_sira'] == list(range(1, N_TAKIM + 1))  # tablodaki sıra olduğu gibi


def test_simulasyon_36dan_az_takimda_none():
    S, _ = _kupa()
    S['tablo'] = [('', S['tablo'][0][1][:20])]
    assert avrupa.simulasyon({'kupalar': {'42': {'x': S}}}, _Elo(), 42, 'x', N=10) is None
    assert avrupa.simulasyon({'kupalar': {}}, _Elo(), 42, 'x', N=10) is None
