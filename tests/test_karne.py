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


def test_kalibrasyon_tablosu_dilimler():
    # 4 maç × 3 sonuç = 12 olasılık; 0,6 / 0,7 tek, 0,5 tek dilimde
    t = karne.kalibrasyon_tablosu(K)
    assert sum(d['n'] for d in t) == 12
    assert [d['alt'] for d in t] == sorted(d['alt'] for d in t)
    d6 = next(d for d in t if d['alt'] == pytest.approx(0.6))
    assert d6['n'] == 1 and d6['tahmin'] == pytest.approx(0.6) and d6['oran'] == 1.0  # 2-0, ev %60
    d5 = next(d for d in t if d['alt'] == pytest.approx(0.5))
    assert d5['n'] == 2 and d5['oran'] == 0.0  # 0,5 ev (0-1) ve 0,5 deplasman (1-1): ikisi de olmadı
    assert karne.kalibrasyon_tablosu([]) == []


def test_kalibrasyon_tablosu_bir_olasiligi_son_dilimde():
    t = karne.kalibrasyon_tablosu([kayit((1.0, 0.0, 0.0), 1, 0)])
    assert t[-1]['alt'] == pytest.approx(0.9) and t[-1]['n'] == 1 and t[-1]['oran'] == 1.0
    assert t[0]['alt'] == 0.0 and t[0]['n'] == 2 and t[0]['oran'] == 0.0


def test_kalibrasyon_hatasi():
    assert karne.kalibrasyon_hatasi([]) is None
    assert karne.kalibrasyon_hatasi([{'n': 10, 'tahmin': 0.3, 'oran': 0.3}]) == pytest.approx(0.0)
    # ağırlıklı ortalama |söylenen - olan|: (10·0,1 + 30·0,2) / 40
    t = [{'n': 10, 'tahmin': 0.3, 'oran': 0.4}, {'n': 30, 'tahmin': 0.7, 'oran': 0.5}]
    assert karne.kalibrasyon_hatasi(t) == pytest.approx(0.175)
    # mükemmel tahmin: hata 0
    assert karne.kalibrasyon_hatasi(karne.kalibrasyon_tablosu([kayit((1.0, 0.0, 0.0), 1, 0)] * 3)) == pytest.approx(0.0)


def test_ozet_kalibrasyon_hatasi():
    o = karne.ozet(K)
    assert o['ece'] == pytest.approx(karne.kalibrasyon_hatasi(karne.kalibrasyon_tablosu(K)))
    assert o['kalibrasyon_tablosu'] == karne.kalibrasyon_tablosu(K)
