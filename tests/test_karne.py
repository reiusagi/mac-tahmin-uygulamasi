"""karne.py: özet, favori isabeti, gol özeti, hafta başı ve okuma (elle yapılmış kayıtlarla)."""
import json
import math

import pytest

from mac_tahmin import karne


def kayit(p, hg, ag, lig='EPL', tarih='2026-09-16', piy=(0.8, 0.5, 0.2, 0.5)):
    return [lig, 2026, tarih, 'A', 'B', *p, hg, ag, *piy]


K = [kayit((0.6, 0.25, 0.15), 2, 0), kayit((0.2, 0.3, 0.5), 1, 1), kayit((0.5, 0.3, 0.2), 0, 1, lig='La_liga'),
     kayit((0.1, 0.2, 0.7), 0, 3, lig='La_liga')]


def test_hafta_basi_pazartesi():
    assert karne._hafta_basi('2026-09-16') == '2026-09-14'  # çarşamba
    assert karne._hafta_basi('2026-09-14') == '2026-09-14'
    assert karne._hafta_basi('2026-09-20T18:00:00Z') == '2026-09-14'  # pazar
    assert karne._hafta_basi('2026-09-21') == '2026-09-21'


def test_ozet_bos_none():
    assert karne.ozet([]) is None


def test_ozet_degerleri():
    o = karne.ozet(K)
    assert o['n'] == 4
    assert o['isabet'] == pytest.approx(0.5)  # 1. ve 4. tuttu
    assert o['ev_isabet'] == pytest.approx(0.25)
    assert o['oran'] == [0.25, 0.25, 0.5]
    beklenen = -(math.log(0.6) + math.log(0.3) + math.log(0.2) + math.log(0.7)) / 4
    assert o['log_kayip'] == pytest.approx(beklenen)
    assert 0 < o['brier'] < 2
    assert o['bilgisiz_log_kayip'] > 0


def test_ozet_mukemmel_tahmin():
    o = karne.ozet([kayit((1.0, 0.0, 0.0), 1, 0)] * 3)
    assert o['isabet'] == 1.0 and o['brier'] == pytest.approx(0.0)


def test_favori_isabeti():
    assert karne.favori_isabeti(K, 0.6, pay=0.05) == (1.0, 1)
    assert karne.favori_isabeti(K, 0.5, pay=0.05) == (0.0, 2)  # ikisi de tutmadı (1-1 ve 0-1)
    assert karne.favori_isabeti(K, 0.5, lig='La_liga', pay=0.05) == (0.0, 1)
    assert karne.favori_isabeti(K, 0.9) == (None, 0)
    assert karne.favori_isabeti([], 0.5) == (None, 0)


def test_gol_ozeti():
    g = karne.gol_ozeti(K)
    assert [x['ad'] for x in g] == ['1,5 üst', '2,5 üst', '3,5 üst', 'Karşılıklı gol']
    assert g[3]['n'] == 4 and g[3]['oran'] == pytest.approx(0.25)  # yalnız 1-1 karşılıklı gol
    assert karne.gol_ozeti([]) == []
    assert karne.gol_ozeti([r[:10] for r in K]) == []  # eski kısa kayıtlar yok sayılır


def test_oku_ve_onbellek(tmp_path):
    assert karne.oku(tmp_path) == []
    assert karne.oku_onbellek(tmp_path) == []
    (tmp_path / 'karne.json').write_text(json.dumps(K), encoding='utf-8')
    assert karne.oku(tmp_path) == K
    assert karne.oku_onbellek(tmp_path) == K
    assert karne.oku_onbellek(tmp_path) is karne.oku_onbellek(tmp_path)
