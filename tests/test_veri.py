"""veri.py güvenlik yardımcıları: adres izni, yanıt boyutu sınırı, kimlik doğrulama. Ağa çıkılmaz (veri.ac sahte)."""
import email
import gzip
import io
import json
import urllib.error
import urllib.request
import urllib.response

import pytest

from mac_tahmin import transfermarkt, veri


class SahteYanit:
    def __init__(self, govde, url='https://www.fotmob.com/api/x', status=200):
        self._b, self._url, self.status = io.BytesIO(govde), url, status

    def read(self, n=-1):
        return self._b.read(n)

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sahte_ag(monkeypatch, govde, url=None):
    cagrilar = []

    def urlopen(istek, timeout=None):
        cagrilar.append(istek.full_url)
        return SahteYanit(govde, url or istek.full_url)
    monkeypatch.setattr(veri, 'ac', urlopen)
    return cagrilar


# ------------------------------------------------------------ adres izni

@pytest.mark.parametrize('url', [
    'https://www.fotmob.com/api/data/leagues?id=47',
    'https://fotmob.com/x',
    'https://images.fotmob.com/a.png',
    'https://understat.com/getLeagueData/EPL/2025',
    'https://www.transfermarkt.com/schnellsuche',
    'https://api.open-meteo.com/v1/forecast?latitude=1',
])
def test_izinli_adresler_gecer(url):
    assert veri.url_guvenli_mi(url)


@pytest.mark.parametrize('url', [
    'http://www.fotmob.com/api',                 # https değil
    'ftp://www.fotmob.com/api',
    'file:///C:/Windows/win.ini',
    'https://evil.com/fotmob.com',
    'https://fotmob.com.evil.com/x',
    'https://notfotmob.com/x',
    'https://www.fotmob.com@evil.com/x',          # kullanıcı bilgisi tuzağı
    'https://evil.com\\@www.fotmob.com/x',
    'https://localhost/x',
    'https://127.0.0.1/x',
    'https://www.fotmob.com:8443/x',
    '', None, 5, 'fotmob.com',
])
def test_izinsiz_adresler_reddedilir(url):
    assert not veri.url_guvenli_mi(url)


def test_json_getir_izinsiz_adrese_istek_atmaz(monkeypatch):
    cagrilar = sahte_ag(monkeypatch, b'{}')
    with pytest.raises(ValueError):
        veri.json_getir('http://www.fotmob.com/api')
    with pytest.raises(ValueError):
        veri.json_getir('https://evil.example/api')
    assert cagrilar == []


def test_json_getir_normal_yanit(monkeypatch):
    sahte_ag(monkeypatch, json.dumps({'a': 'ş'}).encode())
    assert veri.json_getir('https://www.fotmob.com/api') == {'a': 'ş'}


def test_json_getir_gzip_acar(monkeypatch):
    sahte_ag(monkeypatch, gzip.compress(json.dumps({'a': 1}).encode()))
    assert veri.json_getir('https://understat.com/x') == {'a': 1}


def test_json_getir_baska_adrese_yonlendirilen_yaniti_reddeder(monkeypatch):
    sahte_ag(monkeypatch, b'{}', url='https://evil.example/x')
    with pytest.raises(ValueError):
        veri.json_getir('https://www.fotmob.com/api')


# ------------------------------------------------------------ yönlendirme

_ASIL_ACMA = urllib.request.OpenerDirector.open  # conftest testlerde engeller; sahte işleyicili açıcılar için geri konur


@pytest.fixture
def acici_acik(monkeypatch):
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', _ASIL_ACMA)


class SahteYonlendirme(urllib.request.BaseHandler):
    """https isteğine 302 + Location döner (ağa çıkmadan); Location sonrası gidilen adresleri de kaydeder."""
    handler_order = 100

    def __init__(self, hedef):
        self.hedef, self.istekler = hedef, []

    def https_open(self, istek):
        self.istekler.append(istek.full_url)
        if len(self.istekler) == 1:
            r = urllib.response.addinfourl(io.BytesIO(b''), email.message_from_string(f'Location: {self.hedef}' + chr(10)),
                                           istek.full_url, 302)
            r.msg = 'Found'
            return r
        r = urllib.response.addinfourl(io.BytesIO(b'{}'), email.message_from_string(''), istek.full_url, 200)
        r.msg = 'OK'
        return r


def test_izinsiz_adrese_yonlendirme_istek_atmadan_reddedilir(acici_acik):
    sahte = SahteYonlendirme('https://evil.example/x')
    acici = veri.guvenli_acici(sahte)
    with pytest.raises(ValueError):
        acici.open(urllib.request.Request('https://www.fotmob.com/api/data/x'))
    assert sahte.istekler == ['https://www.fotmob.com/api/data/x']  # yönlendirilen siteye ikinci istek gitmedi


@pytest.mark.parametrize('hedef', ['http://www.fotmob.com/x', 'https://fotmob.com.evil.com/x', 'https://localhost/x',
                                   'https://www.fotmob.com:8443/x', 'file:///C:/Windows/win.ini'])
def test_yonlendirme_hedefi_url_guvenli_mi_den_gecmeli(acici_acik, hedef):
    sahte = SahteYonlendirme(hedef)
    with pytest.raises((ValueError, urllib.error.URLError)):
        veri.guvenli_acici(sahte).open(urllib.request.Request('https://www.fotmob.com/api/data/x'))
    assert len(sahte.istekler) == 1


def test_izinli_adrese_yonlendirme_izlenir(acici_acik):
    sahte = SahteYonlendirme('https://images.fotmob.com/y')
    with veri.guvenli_acici(sahte).open(urllib.request.Request('https://www.fotmob.com/api/data/x')) as r:
        assert r.read() == b'{}'
    assert sahte.istekler == ['https://www.fotmob.com/api/data/x', 'https://images.fotmob.com/y']


def test_ac_guvenli_acici_kullanir_ve_testlerde_ag_kapali():
    with pytest.raises(RuntimeError):  # conftest: OpenerDirector.open engelli
        veri.ac(urllib.request.Request('https://www.fotmob.com/api/data/x'))


# ------------------------------------------------------------ boyut sınırları

def test_govde_sinirini_asan_yanit_reddedilir(monkeypatch):
    monkeypatch.setattr(veri, 'EN_BUYUK_GOVDE', 100)
    sahte_ag(monkeypatch, b'[' + b'1,' * 200 + b'1]')
    with pytest.raises(ValueError):
        veri.json_getir('https://www.fotmob.com/api')


def test_govde_sinirinda_kabul_edilir(monkeypatch):
    govde = b'[' + b'1,' * 20 + b'1]'
    monkeypatch.setattr(veri, 'EN_BUYUK_GOVDE', len(govde))
    sahte_ag(monkeypatch, govde)
    assert len(veri.json_getir('https://www.fotmob.com/api')) == 21


def test_gzip_bombasi_reddedilir(monkeypatch):
    monkeypatch.setattr(veri, 'EN_BUYUK_ACILMIS', 10_000)
    bomba = gzip.compress(b'[' + b'0,' * 1_000_000 + b'0]')  # birkaç KB, açılınca 2 MB
    assert len(bomba) < 50_000
    sahte_ag(monkeypatch, bomba)
    with pytest.raises(ValueError):
        veri.json_getir('https://www.fotmob.com/api')


def test_gzip_ac_bozuk_ya_da_yarim_veri_hata_verir():
    tam = gzip.compress(b'merhaba' * 100)
    with pytest.raises(ValueError):
        veri.gzip_ac(tam[:-10])
    with pytest.raises(ValueError):
        veri.gzip_ac(b'\x1f\x8bbozuk')


def test_gzip_ac_dogru_acar():
    assert veri.gzip_ac(gzip.compress('çğş'.encode())) == 'çğş'.encode()


# ------------------------------------------------------------ onbellekli + fetchAllUrl

def test_onbellekli_izinsiz_adreste_dosya_yazmaz(monkeypatch, tmp_path):
    sahte_ag(monkeypatch, b'{}')
    monkeypatch.setattr(veri, 'BEKLEME', 0)
    with pytest.raises(ValueError):
        veri.onbellekli(tmp_path / 'x.json', 'https://evil.example/x')
    assert not (tmp_path / 'x.json').exists()


def test_liste_url_gecerli_ve_gecersiz():
    assert veri.liste_url({'fetchAllUrl': 'https://data.fotmob.com/stats/47/season/1/mins_played.json'}) \
        == 'https://data.fotmob.com/stats/47/season/1/mins_played.json'
    assert veri.liste_url({'fetchAllUrl': 'https://evil.example/x.json'}) is None
    assert veri.liste_url({'fetchAllUrl': 'http://data.fotmob.com/x.json'}) is None
    assert veri.liste_url({}) is None
    assert veri.liste_url(None) is None


def test_fotmob_liste_zararli_adres_icin_istek_atmaz(monkeypatch, tmp_path):
    cagrilar = sahte_ag(monkeypatch, b'{}')
    lg = {'stats': {'players': [{'name': 'goals', 'fetchAllUrl': 'https://evil.example/x.json'}]}}
    assert veri._fotmob_liste(lg, tmp_path, 47, 2025, 'goals', 'players', 'ParticiantId') == {}
    assert cagrilar == []


def test_mevki_haritasi_zararli_adreste_none(monkeypatch, tmp_path):
    cagrilar = sahte_ag(monkeypatch, b'{}')
    lg = {'details': {'selectedSeason': '2025/2026'},
          'stats': {'players': [{'name': 'mins_played', 'fetchAllUrl': 'http://169.254.169.254/x'}]}}
    (tmp_path / 'fm-47-2025.json').write_text(json.dumps(lg), encoding='utf-8')
    assert veri.fotmob_mevki_haritasi('EPL', 2025, tmp_path) is None
    assert cagrilar == []


# ------------------------------------------------------------ kimlik

@pytest.mark.parametrize('x,beklenen', [(123, '123'), ('456', '456'), ('0', '0'), (7, '7')])
def test_kimlik_gecerli(x, beklenen):
    assert veri.kimlik(x) == beklenen


@pytest.mark.parametrize('x', [None, '', ' ', '12a', '../x', '..\\..\\win', '1/2', '-5', 1.5, '²', '٣', '1 2', '12\n',
                               True, '1' * 30, b'12', 'a.json'])
def test_kimlik_gecersiz(x):
    with pytest.raises(ValueError):
        veri.kimlik(x)


def test_kimlik_yol_gezintisini_engeller(tmp_path):
    with pytest.raises(ValueError):
        veri.kimlik('../../gizli')


# ------------------------------------------------------------ transfermarkt

def test_transfermarkt_getir_sinirli_okur(monkeypatch):
    monkeypatch.setattr(transfermarkt, 'BEKLEME_SN', 0)
    monkeypatch.setattr(transfermarkt, '_engel', [0.0])
    monkeypatch.setattr(veri, 'EN_BUYUK_GOVDE', 50)
    monkeypatch.setattr(transfermarkt, 'ac',
                        lambda istek, timeout=None: SahteYanit(b'x' * 500, 'https://www.transfermarkt.com/x'))
    with pytest.raises(ValueError):
        transfermarkt._getir('/x')


def test_transfermarkt_getir_gzip_acar(monkeypatch):
    monkeypatch.setattr(transfermarkt, 'BEKLEME_SN', 0)
    monkeypatch.setattr(transfermarkt, '_engel', [0.0])
    monkeypatch.setattr(transfermarkt, 'ac',
                        lambda istek, timeout=None: SahteYanit(gzip.compress('<p>çok güzel</p>'.encode()),
                                                               'https://www.transfermarkt.com/x'))
    assert transfermarkt._getir('/x') == '<p>çok güzel</p>'


def test_transfermarkt_getir_baska_siteye_yonlenmeyi_reddeder(monkeypatch):
    monkeypatch.setattr(transfermarkt, 'BEKLEME_SN', 0)
    monkeypatch.setattr(transfermarkt, '_engel', [0.0])
    monkeypatch.setattr(transfermarkt, 'ac',
                        lambda istek, timeout=None: SahteYanit(b'<p>x</p>', 'https://evil.example/'))
    with pytest.raises(ValueError):
        transfermarkt._getir('/x')


# ------------------------------------------------------------ önbellek yollarında kimlik denetimi

ZARARLI = ['../../gizli', '1/../../x', 'abc', '12\34', '', None]


def _agsiz(monkeypatch):
    cagrilar = sahte_ag(monkeypatch, b'{}')
    return cagrilar


@pytest.mark.parametrize('tid', ZARARLI)
def test_takim_getir_zararli_kimlikte_ne_yazar_ne_ister(monkeypatch, tmp_path, tid):
    from mac_tahmin import takim
    cagrilar = _agsiz(monkeypatch)
    with pytest.raises(ValueError):
        takim._getir(tid, tmp_path)
    assert cagrilar == []
    assert list(tmp_path.rglob('*')) == []


@pytest.mark.parametrize('pid', ZARARLI)
def test_oyuncu_sayfasi_zararli_kimlik(monkeypatch, tmp_path, pid):
    from mac_tahmin import takim
    cagrilar = _agsiz(monkeypatch)
    with pytest.raises(ValueError):
        takim._oyuncu_sayfasi(pid, tmp_path)
    assert cagrilar == [] and list(tmp_path.rglob('*')) == []


def test_onbellekteki_uyruklar_zararli_kimlik_bos_doner(tmp_path):
    from mac_tahmin import takim
    (tmp_path / 'gizli.json').write_text('{"details": {"country": "XX"}}', encoding='utf-8')
    (tmp_path / 'takim').mkdir()
    assert takim.onbellekteki_uyruklar('../gizli', tmp_path / 'takim') == (None, {})


@pytest.mark.parametrize('mid', ZARARLI)
def test_mac_ozeti_ayrinti_zararli_kimlik(monkeypatch, tmp_path, mid):
    from mac_tahmin import mac_ozeti
    cagrilar = _agsiz(monkeypatch)
    with pytest.raises(ValueError):
        mac_ozeti.ayrinti(mid, tmp_path)
    assert cagrilar == [] and list(tmp_path.rglob('*')) == []


@pytest.mark.parametrize('mid', ZARARLI)
def test_hakem_mac_detay_zararli_kimlik(monkeypatch, tmp_path, mid):
    from mac_tahmin import hakem
    cagrilar = _agsiz(monkeypatch)
    with pytest.raises(ValueError):
        hakem.mac_detay(mid, tmp_path)
    assert cagrilar == [] and list(tmp_path.rglob('*')) == []


def test_kimlik_sayi_olarak_da_calisir(monkeypatch, tmp_path):
    from mac_tahmin import takim
    yol = tmp_path / 'takim'
    yol.mkdir()
    (yol / '42.json').write_text('{"a": 1}', encoding='utf-8')
    assert takim._getir(42, tmp_path) == {'a': 1}
    assert takim._getir('42', tmp_path) == {'a': 1}
