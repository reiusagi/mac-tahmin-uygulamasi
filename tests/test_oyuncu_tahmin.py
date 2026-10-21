"""oyuncu_tahmin.py: krallık yarışı (Monte Carlo) ve ilk üç olasılığının bellek dostu hesabı."""
import tracemalloc

import numpy as np
import pytest

from mac_tahmin import oyuncu_tahmin as ot

from yardimci import oyuncu, sezon_kur


def _ilk3_eski(son):
    """Eski formül: kendisinden kesin fazla atan oyuncu sayısı 3'ten azsa ilk üçte (N×A×A bellek)."""
    sira = (son[:, :, None] < son[:, None, :]).sum(axis=2)
    return (sira < 3).mean(axis=0)


@pytest.mark.parametrize('tohum', range(8))
@pytest.mark.parametrize('oyuncu_sayisi', [1, 2, 3, 4, 7, 25])
def test_ilk3_eski_formulle_ayni_beraberliklerle(tohum, oyuncu_sayisi):
    rng = np.random.default_rng(tohum)
    son = rng.poisson(1.2, size=(400, oyuncu_sayisi))  # küçük ortalama: çok beraberlik
    assert ot._ilk3(son) == pytest.approx(_ilk3_eski(son), abs=1e-12)


def test_ilk3_hepsi_esitse_herkes_ilk_uctedir():
    son = np.full((5, 6), 4)
    assert ot._ilk3(son).tolist() == [1.0] * 6


def test_ilk3_az_oyuncuda_hepsi_bir():
    assert ot._ilk3(np.array([[3, 1], [0, 9]])).tolist() == [1.0, 1.0]


def test_ilk3_kesin_fazla_atan_sayisi_uctan_azsa_girer():
    # 5, 5, 4, 4, 1: 4 atanlar kendilerinden fazla atan 2 oyuncu var -> ilk üç; 1 atan 4 oyuncu var -> dışarıda
    son = np.array([[5, 5, 4, 4, 1]])
    assert ot._ilk3(son).tolist() == [1.0, 1.0, 1.0, 1.0, 0.0]


def test_ilk3_buyuk_havuzda_bellek_patlamaz():
    rng = np.random.default_rng(1)
    son = rng.poisson(2.0, size=(10000, 315))
    tracemalloc.start()
    try:
        out = ot._ilk3(son)
        _, tepe = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert out.shape == (315,)
    assert tepe < 150 * 1024 * 1024  # eski formül ~1 GB ayırıyordu (10000 × 315 × 315)


def _lig_ve_oyunculari():
    takimlar = ['A', 'B', 'C', 'D']
    oynanan = [('A', 'B', 2, 1), ('C', 'D', 0, 0), ('A', 'C', 1, 1), ('B', 'D', 3, 0)]
    kalan = [('A', 'D'), ('B', 'C'), ('D', 'A'), ('C', 'B')]
    pl = [oyuncu('Golcu A', 'A', g=5, xg=4.0, no=1), oyuncu('Yan A', 'A', g=2, xg=2.5, no=2),
          oyuncu('Golcu B', 'B', g=4, xg=3.0, no=3), oyuncu('Orta C', 'C', g=1, xg=1.0, no=4),
          oyuncu('Orta D', 'D', g=3, xg=2.0, no=5), oyuncu('Kale B', 'B', g=0, xg=0.0, pos='G', no=6)]
    return sezon_kur(takimlar, oynanan, kalan, oyuncular=pl)


def test_krallik_belirlenimci_ve_olasiliklar_tutarli():
    S = _lig_ve_oyunculari()
    k1, k2 = ot.krallik(S, 'gol', N=2000), ot.krallik(S, 'gol', N=2000)
    assert [(r['p']['n'], r['kral'], r['ilk3']) for r in k1] == [(r['p']['n'], r['kral'], r['ilk3']) for r in k2]
    assert sum(r['kral'] for r in k1) == pytest.approx(1.0, abs=1e-9)  # beraberlikte krallık paylaştırılır
    for r in k1:
        assert 0.0 <= r['kral'] <= r['ilk3'] <= 1.0
        assert r['beklenen'] >= r['mevcut']
    assert k1[0]['p']['n'] == 'Golcu A'  # en çok gol + en yüksek oran


def test_krallik_adaysiz_bos_doner():
    S = sezon_kur(['A', 'B'], [('A', 'B', 1, 0)], [('B', 'A')], oyuncular=[oyuncu('Hic', 'A', g=0, xg=0.0, dk=0)])
    assert ot.krallik(S, 'gol', N=100) == []
