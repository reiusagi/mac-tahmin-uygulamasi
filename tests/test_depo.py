"""Depo: scout havuzu önbelleği artık JSON (pickle yok). Disk ya da ağ kullanılmaz; her şey tmp_path'te."""
import inspect
import json
import pickle
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from mac_tahmin.arayuz import depo as depo_modulu
from mac_tahmin.arayuz.depo import Depo, onbellek_coz, onbellek_kodla

ORNEK_ADAY = {
    'p': {'n': 'Joshua King', 'ex': {'npg': 2, 'sav': None}, 'adaylar': ['M'], 'fm_id': 1422593, 'yas': 19, 'ozel': []},
    'lig': 'EPL', 'yil': 2026, 'endeks': 60.23635340461452, 'deger': 29589233,
    'guclu': [('xG zinciri', 88), ('Gol', 84)],            # tuple listesi
    'zorluk_neden': ['Fulham büyük kulüp (kadro 421 M€)', 'şç ğ ı İ'],
    'uyruk': ('ENG', 'England'),                            # tuple
    'istikrar': {'n': 7, 'ort': 7.218571428571429, 'kaleci': False, 'etiket': 'İstikrarlı'},
    'bos': (),
    'ic_ice': [[('a', 1)], ((1, 2), (3,))],
}


def depo_olustur(tmp_path):
    """Arka plan iş parçacığı başlatmadan Depo (yalnızca disk önbelleği yöntemleri için)."""
    d = Depo.__new__(Depo)
    d.veri_klasoru = tmp_path / 'd'
    d.veri_klasoru.mkdir()
    d.g = SimpleNamespace(ham=tmp_path / 'ham')
    d._scout_kilitleri = {}
    return d


# ------------------------------------------------------------ kodla / çöz

def test_kodla_coz_tuple_ve_tipleri_korur():
    sonuc = onbellek_coz(json.loads(json.dumps(onbellek_kodla(ORNEK_ADAY))))
    assert sonuc == ORNEK_ADAY
    assert isinstance(sonuc['uyruk'], tuple)
    assert isinstance(sonuc['guclu'], list) and isinstance(sonuc['guclu'][0], tuple)
    assert sonuc['bos'] == () and isinstance(sonuc['bos'], tuple)
    assert isinstance(sonuc['ic_ice'][1][0], tuple)
    assert isinstance(sonuc['p']['ex']['npg'], int) and isinstance(sonuc['endeks'], float)
    assert sonuc['istikrar']['kaleci'] is False and sonuc['p']['ex']['sav'] is None


def test_kodla_girdiyi_degistirmez():
    orijinal = {'a': [('x', 1)], 'b': ('y',)}
    kopya = {'a': [('x', 1)], 'b': ('y',)}
    onbellek_kodla(orijinal)
    assert orijinal == kopya


def test_kodla_sayisal_kutuphane_sayilarini_duz_sayiya_cevirir():
    numpy = pytest.importorskip('numpy')
    kod = onbellek_kodla({'a': numpy.float64(1.5), 'b': numpy.int64(3)})
    assert json.loads(json.dumps(kod)) == {'a': 1.5, 'b': 3}


def test_kodla_desteklenmeyen_tipte_hata_verir():
    with pytest.raises(TypeError):
        json.dumps(onbellek_kodla({'a': {1, 2}}))
    with pytest.raises(TypeError):
        onbellek_kodla({1: 'sayı anahtar sessizce metne dönmesin'})


def test_coz_etiketli_sozluk_olmayan_veriye_dokunmaz():
    assert onbellek_coz({'__tuple__': [1, 2], 'baska': 3}) == {'__tuple__': [1, 2], 'baska': 3}
    assert onbellek_coz({'a': [1, {'b': 2}]}) == {'a': [1, {'b': 2}]}


# ------------------------------------------------------------ scout havuzu diskte

def test_scout_havuzu_yaz_oku_gidis_donus(tmp_path):
    d = depo_olustur(tmp_path)
    zamanlar = {x[0]: None for x in depo_modulu.LIGLER}
    adaylar = [ORNEK_ADAY, {**ORNEK_ADAY, 'lig': 'La_liga'}]
    d._scout_yaz('U23', None, zamanlar, adaylar)
    yol = d._scout_yolu('U23', None)
    assert yol.suffix == '.json' and yol.exists()
    oku = d.scout_havuzu_oku('U23', None)
    assert oku is not None
    okunan, taze = oku
    assert okunan == adaylar
    assert isinstance(okunan[0]['uyruk'], tuple)
    assert taze is True  # lig dosyaları yok: yazarkenki durumla aynı


def test_scout_havuzu_eski_ya_da_degismis_lig_dosyasinda_bayat(tmp_path):
    d = depo_olustur(tmp_path)
    ligler = [x[0] for x in depo_modulu.LIGLER]
    d._scout_yaz('U23', 5_000_000, {l: None for l in ligler}, [ORNEK_ADAY])
    (d.veri_klasoru / f'{ligler[0]}-{depo_modulu.SON_SEZON}.json').write_text('{}', encoding='utf-8')
    adaylar, taze = d.scout_havuzu_oku('U23', 5_000_000)
    assert adaylar == [ORNEK_ADAY] and taze is False


def test_scout_havuzu_24_saatten_eskiyse_bayat(tmp_path, monkeypatch):
    d = depo_olustur(tmp_path)
    ligler = [x[0] for x in depo_modulu.LIGLER]
    d._scout_yaz(None, None, {l: None for l in ligler}, [])
    gercek = time.time
    monkeypatch.setattr(time, 'time', lambda: gercek() + 25 * 3600)
    assert d.scout_havuzu_oku(None, None) == ([], False)


def test_eski_pickle_dosyasi_yok_sayilir_ve_hic_acilmaz(tmp_path):
    d = depo_olustur(tmp_path)
    eski = d._scout_yolu('U23', None).with_suffix('.pkl')
    eski.parent.mkdir(parents=True)
    # açılırsa yan etkisi olan bir pickle: okunursa bu test dosya yaratır
    iz = tmp_path / 'calisti.txt'
    eski.write_bytes(pickle.dumps(_Iz(str(iz))))
    assert d.scout_havuzu_oku('U23', None) is None
    assert not iz.exists()


def test_yeni_havuz_yazilinca_eski_pkl_dosyalari_silinir(tmp_path):
    d = depo_olustur(tmp_path)
    eski = d._scout_yolu('U23', None).with_suffix('.pkl')
    eski.parent.mkdir(parents=True)
    eski.write_bytes(b'eski')
    baska = eski.parent / 'not.txt'
    baska.write_text('dokunma', encoding='utf-8')
    d._scout_yaz('U23', None, {}, [])
    assert not eski.exists() and baska.exists() and d._scout_yolu('U23', None).exists()


class _Iz:
    def __init__(self, yol):
        self.yol = yol

    def __reduce__(self):
        return (Path(self.yol).write_text, ('calisti',))


@pytest.mark.parametrize('icerik', ['', 'bozuk{', '[]', '"metin"', '{"surum": 1}', '{"surum": 2}',
                                    '{"surum": 2, "adaylar": 5, "zamanlar": {}, "zaman": 1}'])
def test_bozuk_ya_da_yanlis_surumlu_dosya_onbellek_kacirmasidir(tmp_path, icerik):
    d = depo_olustur(tmp_path)
    yol = d._scout_yolu('U23', None)
    yol.parent.mkdir(parents=True)
    yol.write_text(icerik, encoding='utf-8')
    assert d.scout_havuzu_oku('U23', None) is None


def test_scout_yazimi_yarim_dosya_birakmaz(tmp_path):
    d = depo_olustur(tmp_path)
    with pytest.raises(TypeError):
        d._scout_yaz('U23', None, {}, [{'x': {1, 2}}])
    yol = d._scout_yolu('U23', None)
    assert not yol.exists()
    assert list(yol.parent.glob('*')) == []  # geçici dosya da kalmaz


def test_scout_yolu_json_uzantili(tmp_path):
    d = depo_olustur(tmp_path)
    assert d._scout_yolu('U23', 5_000_000).name == 'havuz-U23-5000000.json'
    assert d._scout_yolu(None, None).name == 'havuz-hepsi-hepsi.json'


def test_depo_kaynaginda_pickle_kalmadi():
    kaynak = inspect.getsource(depo_modulu)
    assert 'pickle' not in kaynak


# ------------------------------------------------------------ değer önbelleği dosya adları

def test_dosya_adi_gecerli_lig_anahtarlarini_degistirmez():
    from mac_tahmin.sezon import LIGLER
    assert all(depo_modulu.dosya_adi(l[0]) == l[0] for l in LIGLER)  # eski önbellek dosyaları geçerli kalır


def test_degerler_onbellegi_okuma_ve_yazma_ayni_dosya_adini_kullanir(tmp_path):
    d = depo_olustur(tmp_path)
    d._degerler = {}
    klasor = tmp_path / 'ham' / 'degerler'
    klasor.mkdir(parents=True)
    (klasor / '___evil.json').write_text('{"7": 5}', encoding='utf-8')  # dosya_adi('../evil')
    assert d.degerler_onbellek('../evil') == {7: 5}
    (klasor / '___evil-kadro.json').write_text('{"A": 3}', encoding='utf-8')
    assert d.kadro_degerleri('../evil', ['A'], indir=False) == {'A': 3}


def test_kadro_tara_dosyalari_dosya_adiyla_yazar(tmp_path, monkeypatch):
    from mac_tahmin import takim
    d = depo_olustur(tmp_path)
    d.takim_kimligi = lambda lig, ad: 1
    monkeypatch.setattr(takim, 'takim_sayfasi', lambda tid, ham: {'kadro': [{'id': 7, 'deger': 5}]})
    d._kadro_tara('../evil', ['A'])
    assert sorted(f.name for f in (tmp_path / 'ham' / 'degerler').iterdir()) == ['___evil-kadro.json', '___evil.json']
