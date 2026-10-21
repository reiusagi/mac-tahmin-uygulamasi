"""Karne sekmesinin saf işlevleri: kalibrasyon sapması, kalibrasyon tablosu ve grafik noktaları."""
import pytest

from mac_tahmin import karne
from mac_tahmin.arayuz import karne_sekme


def kayit(p, hg, ag):
    return ['EPL', 2026, '2026-09-16', 'A', 'B', *p, hg, ag, 0.8, 0.5, 0.2, 0.5]


T = [{'alt': 0.2, 'ust': 0.3, 'n': 30, 'tahmin': 0.25, 'oran': 0.3},
     {'alt': 0.6, 'ust': 0.7, 'n': 10, 'tahmin': 0.65, 'oran': 0.45}]


def test_kalibrasyon_sapmasi_yuzde_puani():
    assert karne_sekme.kalibrasyon_sapmasi(T) == pytest.approx((30 * 0.05 + 10 * 0.2) / 40 * 100)
    assert karne_sekme.kalibrasyon_sapmasi([]) is None


def test_kalibrasyon_noktalari_az_olasilikli_dilim_atlanir():
    n = karne_sekme.kalibrasyon_noktalari(T, en_az=20)
    assert len(n) == 1
    assert n[0]['value'] == [25.0, 30.0] and '30' in n[0]['name']
    assert n[0]['symbolSize'] >= 6


def test_kalibrasyon_html_dilimleri_ve_farki_gosterir():
    h = karne_sekme.kalibrasyon_html(T)
    assert '20–30' in h and '60–70' in h
    assert h.count('<tr>') == 3  # başlık + iki dilim
    assert '−20' in h or '-20' in h  # 0,65 dedi, 0,45 oldu: 20 puan az
    assert karne_sekme.kalibrasyon_html([]) == ''


def test_gercek_kayitlarla_tutarli():
    K = [kayit((0.6, 0.25, 0.15), 2, 0), kayit((0.2, 0.3, 0.5), 1, 1)]
    t = karne.kalibrasyon_tablosu(K)
    assert karne_sekme.kalibrasyon_sapmasi(t) == pytest.approx(karne.kalibrasyon_hatasi(t) * 100)
