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


def _gorunum_ligler():
    gorunum = Mock()
    gorunum.depo.stadyumlar.return_value = {'ligler': {
        'EPL': {'Arsenal': 9825, 'Chelsea': 8455},
        'Ligue_1': {'Paris Saint Germain': 9847, 'Lyon': 9748}}}
    return gorunum


def test_ligi_bilinmeyen_mac_takimlarindan_bulunur():
    """Takımlarım ve takım sayfasından açılan maç kartında lig yok: iki takımı birlikte içeren lig kullanılır."""
    gorunum = _gorunum_ligler()

    assert tahmine_git(gorunum, {'durum': 'baslamadi', 'evId': 9847, 'depId': 9748}) is True

    gorunum.tahmin_ac.assert_called_once_with('Ligue_1', 'Paris Saint Germain', 'Lyon')


def test_farkli_liglerin_takimlari_bulunamaz(monkeypatch):
    from nicegui import ui
    monkeypatch.setattr(ui, 'notify', Mock())
    gorunum = _gorunum_ligler()

    assert tahmine_git(gorunum, {'durum': 'baslamadi', 'evId': 9847, 'depId': 9825}) is False

    gorunum.tahmin_ac.assert_not_called()


def test_lig_anahtari_fotmob_kimliginden():
    from mac_tahmin.canli import lig_anahtari
    from mac_tahmin.sezon import FOTMOB_ID
    assert lig_anahtari(FOTMOB_ID['Ligue_1']) == 'Ligue_1'
    assert lig_anahtari(42) == 'avrupa-42'  # Şampiyonlar Ligi
    assert lig_anahtari(None) is None and lig_anahtari(999999) is None


def test_kulup_kartindaki_sampiyonlar_ligi_maci_kupa_analizini_acar():
    """PSG – Barcelona (oynanmış Şampiyonlar Ligi maçı) kulüp kartından: lig maçı sanılıp 'bulunamadı' denmesin."""
    from mac_tahmin.arayuz.ortak import fikstur_maci
    f = {'id': 77, 'zaman': '2026-10-21T19:00:00Z', 'turnuva_id': 42, 'turnuva': 'Şampiyonlar Ligi', 'ev': 'PSG',
         'dep': 'Barcelona', 'evId': 9847, 'depId': 8634, 'skor': (4, 2), 'bitti': True, 'canli': False, 'iptal': False}
    m = fikstur_maci(f)
    assert (m['lig'], m['evId'], m['depId'], m['durum'], m['baslik']) == ('avrupa-42', 9847, 8634, 'bitti', 'Şampiyonlar Ligi')
    gorunum = _gorunum_ligler()
    assert tahmine_git(gorunum, m) is True
    gorunum.avrupa_mac_ac.assert_called_once_with(42, 77)
    gorunum.kartlari_kapat.assert_not_called()  # kupa analizi pencere: kulüp kartı arkada kalır, kapanınca ona dönülür


def test_lig_tahminine_gecerken_acik_kartlar_kapanir():
    """Kulüp kartından lig maçının tahminine geçince Maç tahmini sekmesi kulüp kartının arkasında kalmasın."""
    gorunum = _gorunum_ligler()
    assert tahmine_git(gorunum, {'durum': 'baslamadi', 'lig': 'Ligue_1', 'evId': 9847, 'depId': 9748}) is True
    gorunum.kartlari_kapat.assert_called_once_with()
    gorunum.tahmin_ac.assert_called_once_with('Ligue_1', 'Paris Saint Germain', 'Lyon')


def test_gorunum_kartlari_kapat():
    from mac_tahmin.arayuz.sayfa import Gorunum
    G = Gorunum(depo=None)
    kapanan = []
    G.kart_kapatanlar += [lambda: kapanan.append('kulüp'), lambda: kapanan.append('oyuncu')]
    G.kartlari_kapat()
    assert kapanan == ['kulüp', 'oyuncu']


def test_mac_kimlikleri_karttaki_ayrintidan_tamamlanir():
    from mac_tahmin.arayuz.ortak import mac_kimlikleri_tamamla
    mac = {'id': 1, 'durum': 'baslamadi'}
    veri = {'ev': {'id': 9847, 'ad': 'Paris Saint-Germain'}, 'dep': {'id': 9748, 'ad': 'Lyon'}}

    tam = mac_kimlikleri_tamamla(mac, veri)

    assert (tam['evId'], tam['depId']) == (9847, 9748)
    assert 'evId' not in mac  # özgün sözlük değişmez
    assert mac_kimlikleri_tamamla({'evId': 1, 'depId': 2}, veri) == {'evId': 1, 'depId': 2}
    assert mac_kimlikleri_tamamla(mac, None) == mac


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
