"""Tahmin oyunu (arayuz/oyun.py): haftalık toplam puan grafiğinin verisi ve lig lig istatistik."""
from datetime import date

import pytest

pytest.importorskip('nicegui')

from mac_tahmin.arayuz import oyun  # noqa: E402


def _kayit(tarih, sen, model, sonuc, lig='EPL'):
    return {'lig': lig, 'tarih': tarih, 'ev': 'A', 'dep': 'B', 'sen': sen, 'model': model, 'sonuc': sonuc}


def test_haftalar_pazartesi_baslangicli_toplanir():
    biten = [_kayit('2026-03-02', [1, 0], [0, 0], [1, 0]),  # Pzt: sen 3, model 0
             _kayit('2026-03-08', [2, 1], [1, 1], [3, 0]),  # Paz (aynı hafta): sen 1, model 0
             _kayit('2026-03-09', [0, 0], [0, 0], [0, 0])]  # sonraki hafta: 3 - 3
    h = oyun._haftalar(biten)
    assert {g.isoformat(): v for g, v in h.items()} == {'2026-03-02': [4, 0, 2], '2026-03-09': [3, 3, 1]}


def test_grafik_serileri_kumulatif_ve_fark():
    haftalar = {date(2026, 3, 9): [3, 3, 1], date(2026, 3, 2): [4, 0, 2]}  # sırasız verilse de tarihe göre
    x, ys, ym, fark = oyun._grafik_serileri(haftalar)
    assert len(x) == 2 and ys == [4, 7] and ym == [0, 3] and fark == [4, 4]


def test_bos_veri():
    assert oyun._grafik_serileri({}) == ([], [], [], [])
    assert oyun._haftalar([]) == {}


def test_istatistik_lig_basina_puan_ve_dogru_sonuc_orani():
    biten = [_kayit('2026-03-02', [1, 0], [0, 1], [1, 0], 'EPL'), _kayit('2026-03-03', [0, 1], [0, 1], [2, 0], 'EPL'),
             _kayit('2026-03-04', [1, 1], [1, 1], [1, 1], 'La_liga')]
    html = oyun._istatistik_html(biten)
    assert '<td>2</td><td class="hi">3</td><td class="hi">0</td><td>%50</td><td>%0</td>' in html  # EPL: sen 3+0, model 0+0
    assert '<td>1</td><td class="hi">3</td><td class="hi">3</td><td>%100</td><td>%100</td>' in html  # La Liga
