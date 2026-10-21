"""Canlı skordan maç tahminine geçmek açık sekmeyi korur: kupa ve milli maçlarda ayrıntılı tahmin penceresi Canlı'nın
üstünde açılır; canlı lig maçında tahmine geçilmez (lig tahmini kendi sekmesidir)."""
from unittest.mock import Mock

import pytest

from mac_tahmin.arayuz.ortak import tahmin_acilabilir, tahmine_git


def test_canli_lig_maci_tahmini_sekme_degistirmez():
    gorunum = Mock()

    assert tahmine_git(gorunum, {'durum': 'canli', 'lig': 'Super_Lig', 'id': 123}) is False

    gorunum.sekme_ac.assert_not_called()
    gorunum.tahmin_ac.assert_not_called()
    gorunum.depo.stadyumlar.assert_not_called()


@pytest.mark.parametrize('durum', ['canli', 'baslamadi'])
@pytest.mark.parametrize('lig, ac, kimlik', [('avrupa-42', 'avrupa_mac_ac', 42), ('kupa-9', 'avrupa_mac_ac', 9),
                                               ('milli-84', 'milli_mac_ac', 84)])
def test_kupa_ve_milli_mac_ayrintili_tahmini_sekme_degistirmeden_acar(durum, lig, ac, kimlik):
    gorunum = Mock()

    assert tahmine_git(gorunum, {'durum': durum, 'lig': lig, 'id': 123}) is True

    getattr(gorunum, ac).assert_called_once_with(kimlik, 123)
    gorunum.sekme_ac.assert_not_called()


def test_kimliksiz_kupa_maci_sekmeye_gecer(monkeypatch):
    from nicegui import ui
    monkeypatch.setattr(ui, 'notify', Mock())
    gorunum = Mock()

    assert tahmine_git(gorunum, {'durum': 'baslamadi', 'lig': 'avrupa-42'}) is True

    gorunum.sekme_ac.assert_called_once_with('avrupa')
    gorunum.avrupa_mac_ac.assert_not_called()


@pytest.mark.parametrize('m, beklenen', [({'durum': 'canli', 'lig': 'Super_Lig'}, False),
                                         ({'durum': 'canli', 'lig': 'avrupa-42'}, True),
                                         ({'durum': 'canli', 'lig': 'milli-84'}, True),
                                         ({'durum': 'baslamadi', 'lig': 'Super_Lig'}, True),
                                         ({'durum': 'bitti', 'lig': 'EPL'}, True)])
def test_tahmin_acilabilir(m, beklenen):
    assert tahmin_acilabilir(m) is beklenen


def test_canli_mac_olasilik_satirinda_olu_tahmin_baglantisi_yok():
    from mac_tahmin.arayuz.canli_sekme import _olas_satiri
    o = {'simdi': [0.5, 0.3, 0.2], 'once': [0.4, 0.3, 0.3]}

    canli = _olas_satiri(o, 'canli')
    baslamadi = _olas_satiri(o, 'baslamadi')

    assert 'Şu an' in canli and 'ayrıntılı tahmin' not in canli and 'maç kartı' in canli
    assert 'ayrıntılı tahmin' in baslamadi


def test_baslamamis_mac_tahmini_acilir():
    gorunum = Mock()
    gorunum.depo.stadyumlar.return_value = {'ligler': {'Super_Lig': {'Ev': 1, 'Dep': 2}}}

    assert tahmine_git(gorunum, {'durum': 'baslamadi', 'lig': 'Super_Lig', 'evId': 1, 'depId': 2}) is True

    gorunum.tahmin_ac.assert_called_once_with('Super_Lig', 'Ev', 'Dep')
