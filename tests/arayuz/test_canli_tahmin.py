"""Canlı maçın tahminine tıklamak açık sekmeyi korur."""
from unittest.mock import Mock

import pytest

from mac_tahmin.arayuz.ortak import tahmine_git


@pytest.mark.parametrize('lig', ['Super_Lig', 'avrupa-42', 'milli-84'])
def test_canli_mac_tahmini_sekme_degistirmez(lig):
    gorunum = Mock()

    assert tahmine_git(gorunum, {'durum': 'canli', 'lig': lig, 'id': 123}) is False

    gorunum.sekme_ac.assert_not_called()
    gorunum.tahmin_ac.assert_not_called()
    gorunum.avrupa_mac_ac.assert_not_called()
    gorunum.milli_mac_ac.assert_not_called()
    gorunum.depo.stadyumlar.assert_not_called()


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
