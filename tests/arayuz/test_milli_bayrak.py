"""Milli takım bayrakları: FotMob milli takım id'si → bayrak (takım logosu) adresi; id yoksa boş yer (kırık resim yok)."""
import pytest

from mac_tahmin.arayuz.milli_sekme import BAYRAK_STIL, bayrak_html


def test_gecerli_id_bayrak_adresi_verir():
    html = bayrak_html(6713)

    assert 'teamlogo/6713_xsmall.png' in html
    assert 'class="logo bayrak"' in html and BAYRAK_STIL in html


def test_sayi_olarak_yazilmis_id_de_kabul_edilir():
    assert 'teamlogo/8256_xsmall.png' in bayrak_html('8256')


@pytest.mark.parametrize('tid', [None, '', 'abc', '1);background:red', -5])
def test_gecersiz_id_bos_yer_birakir(tid):
    html = bayrak_html(tid)

    assert 'background-image' not in html and 'url(' not in html
    assert html == f'<span class="logo bayrak" style="{BAYRAK_STIL}"></span>'


def test_ek_stil_eklenir():
    html = bayrak_html(6713, 'margin-left:7px;')

    assert 'style="margin-left:7px;background-image:url(' in html
