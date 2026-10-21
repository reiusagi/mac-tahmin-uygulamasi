"""CSV dışa aktarma: formül enjeksiyonu ve arayüze sızan hata metinleri."""
import csv
from unittest.mock import MagicMock

import pytest

from mac_tahmin.arayuz import disa_aktar


@pytest.mark.parametrize('metin', ['=1+1', '+SUM(A1)', '-2+3', '@HYPERLINK("http://x")', '\t=1', '\r=1',
                                   '=cmd|\' /C calc\'!A0', '+1+1', '-x'])
def test_formul_baslayan_metin_kesme_alir(metin):
    assert disa_aktar._hucre(metin) == "'" + metin


@pytest.mark.parametrize('metin', ['Arsenal', '', 'a=b', "'=1", ' =1', '1+1', 'Şişli', '0', 'x-y'])
def test_zararsiz_metne_dokunulmaz(metin):
    assert disa_aktar._hucre(metin) == metin


@pytest.mark.parametrize('metin', ['+12', '-3', '-3,5', '+2.5', '-0,25%', '+10'])
def test_sayi_gibi_metin_kesme_almaz(metin):
    # "+12" averajı gibi biçimlenmiş değerler yalnızca sayıdır, formül olamaz
    assert disa_aktar._hucre(metin) == metin


def test_gercek_sayilar_sayi_kalir():
    assert disa_aktar._hucre(-5) == -5
    assert isinstance(disa_aktar._hucre(-5), int)
    assert disa_aktar._hucre(-1.5) == '-1,5'  # ondalık virgül; kesme yok
    assert disa_aktar._hucre(0.0) == '0'
    assert disa_aktar._hucre(True) == 'evet'
    assert disa_aktar._hucre(None) == ''


def test_kaydet_basliklari_ve_satirlari_temizler(monkeypatch, tmp_path):
    monkeypatch.setattr(disa_aktar, 'klasor', lambda: tmp_path)
    yol = disa_aktar.kaydet('Tablo', ['Takım', '=BASLIK()'], [['=1+1', -3, -1.25, None], ['Galatasaray', 2, 0.5, 'x']])
    with open(yol, newline='', encoding='utf-8-sig') as f:
        satirlar = list(csv.reader(f, delimiter=';'))
    assert satirlar[0] == ['Takım', "'=BASLIK()"]
    assert satirlar[1] == ["'=1+1", '-3', '-1,25', '']
    assert satirlar[2] == ['Galatasaray', '2', '0,5', 'x']


def test_kaydet_dosya_adindaki_yasak_karakterleri_atar(monkeypatch, tmp_path):
    monkeypatch.setattr(disa_aktar, 'klasor', lambda: tmp_path)
    yol = disa_aktar.kaydet('a/b\\c:d', ['x'], [[1]])
    assert yol.parent == tmp_path and '/' not in yol.name and ':' not in yol.name


# ------------------------------------------------------------ hata metinleri

def _dugme_tikla(monkeypatch, uret, kaydet=None):
    ui = MagicMock()
    monkeypatch.setattr(disa_aktar, 'ui', ui)
    monkeypatch.setattr(disa_aktar, '_goster', lambda yol: None)
    if kaydet:
        monkeypatch.setattr(disa_aktar, 'kaydet', kaydet)
    disa_aktar.dugme('Aktar', uret)
    ui.button.call_args.kwargs['on_click']()
    return ui.notify


def test_uretme_hatasi_yolu_ve_ayrintiyi_arayuze_sizdirmaz(monkeypatch, caplog):
    def uret():
        raise RuntimeError(r'C:\Users\gizli\ham\x.json bulunamadı')
    with caplog.at_level('ERROR'):
        notify = _dugme_tikla(monkeypatch, uret)
    mesaj = notify.call_args.args[0]
    assert 'gizli' not in mesaj and 'x.json' not in mesaj and 'RuntimeError' not in mesaj
    assert 'aktarılamadı' in mesaj.lower()
    assert notify.call_args.kwargs['type'] == 'negative'
    assert 'gizli' in caplog.text  # ayrıntı günlüğe gider


def test_yazma_hatasi_yolu_arayuze_sizdirmaz(monkeypatch, caplog):
    def kaydet(*a):
        raise PermissionError(13, 'Erişim engellendi', r'C:\Users\gizli\Downloads\MacTahmin\t.csv')
    with caplog.at_level('ERROR'):
        notify = _dugme_tikla(monkeypatch, lambda: ('t', ['a'], [[1]]), kaydet)
    mesaj = notify.call_args.args[0]
    assert 'gizli' not in mesaj and 'Downloads' not in mesaj
    assert 'yazılamadı' in mesaj.lower()
    assert 'gizli' in caplog.text


def test_basarida_satir_sayisi_ve_yol_gosterilir(monkeypatch, tmp_path):
    yol = tmp_path / 'ok.csv'
    notify = _dugme_tikla(monkeypatch, lambda: ('t', ['a'], [[1], [2]]), lambda *a: yol)
    assert '2 satır kaydedildi' in notify.call_args.args[0]


def test_satir_yoksa_uyari(monkeypatch):
    notify = _dugme_tikla(monkeypatch, lambda: ('t', ['a'], []))
    assert 'yok' in notify.call_args.args[0]
