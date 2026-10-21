"""Güvenlik ve dayanıklılık testleri: HTML öznitelikleri, ses yükleme, elle yenileme sınırı, sunucu adresi, günlük."""
import logging
import re
from pathlib import Path

import pytest

ZARARLI_KIMLIK = '1)" onclick="alert(1)" x="'


# ------------------------------------------------------------ HTML öznitelikleri ve CSS url()

def test_sayi_kimlik():
    from mac_tahmin.arayuz.ortak import sayi_kimlik
    assert sayi_kimlik(8634) == '8634'
    assert sayi_kimlik('8634') == '8634'
    for kotu in (None, '', ' ', '12a', '1)"x', '²', '٣', '-5', 1.5, True, '1/2', '../x'):
        assert sayi_kimlik(kotu) == '', kotu


def test_takim_logo_zararli_kimlik_bos_logo():
    from mac_tahmin.arayuz.ortak import takim_logo
    assert 'teamlogo/8634_xsmall.png' in takim_logo(8634)
    assert takim_logo(ZARARLI_KIMLIK) == '<span class="logo"></span>'
    assert takim_logo(None) == '<span class="logo"></span>'


def test_takim_karti_logo_ve_saha_kacisli():
    from mac_tahmin.arayuz import takim_karti
    assert takim_karti._logo(ZARARLI_KIMLIK) == ''
    assert takim_karti._logo(0) == ''
    assert 'teamlogo/77_xsmall.png' in takim_karti._logo(77)
    assert 'teamlogo/77_small.png' in takim_karti._logo('77', kucuk=False)
    oyuncular = [{'ad': 'Ali Veli', 'no': '9', 'x': 0.5, 'y': 0.5, 'id': '1"><img src=x onerror=alert(1)>'},
                 {'ad': 'Can', 'no': '1', 'x': 0.2, 'y': 0.2, 'idx': '2"><b>'}]
    h = takim_karti._saha(oyuncular, '<script>alert(1)</script> "not"')
    assert '<script>' not in h and '<img' not in h and '<b>' not in h
    assert '&lt;script&gt;' in h
    assert h.count('data-oyuncu="') == 2
    assert re.findall(r'data-oyuncu="([^"]*)"', h) == ['fm:1&quot;&gt;&lt;img src=x onerror=alert(1)&gt;',
                                                       'idx:2&quot;&gt;&lt;b&gt;']


def test_mac_karti_saha_ve_yedek_kacisli():
    from mac_tahmin.arayuz import mac_karti
    p = {'x': 0.5, 'y': 0.5, 'no': 1, 'ad': 'A B', 'puan': 7.0, 'id': '5"><script>x</script>'}
    kadro = {'ev': {'ilk11': [p]}, 'dep': {'ilk11': []}}
    h = mac_karti._saha_html(kadro)
    assert '<script>' not in h
    yedek = {'yedek': [{'ad': 'Y', 'id': '7" onmouseover="x', 'puan': 6.5, 'no': 12}], 'dizilis': '4-4-2'}
    h2 = mac_karti._yedek_html(yedek, 'Ev')
    assert 'onmouseover="x' not in h2 and 'data-oyuncu="7&quot; onmouseover=&quot;x"' in h2


def test_avrupa_ve_canli_logo_kimlik_denetimi():
    from mac_tahmin.arayuz import avrupa_sekme, canli_sekme
    assert avrupa_sekme._logo(ZARARLI_KIMLIK) == ''
    assert 'teamlogo/9_xsmall.png' in avrupa_sekme._logo(9)
    m = {'durum': 'bitti', 'ev': 'A', 'dep': 'B', 'evGol': 1, 'depGol': 0, 'baslangic': None,
         'evId': ZARARLI_KIMLIK, 'depId': 10}
    h = canli_sekme._satir(m)
    assert 'onclick' not in h and 'teamlogo/10_xsmall.png' in h


def test_takimlarim_mac_satiri_kacisli():
    from mac_tahmin.arayuz import takimlarim
    m = {'zaman': None, 'id': '5"><i>', 'ev': 'A', 'dep': 'B', 'evId': 1, 'depId': 2, 'turnuva': 'T', 'skor': None,
         'sonuc': None, 'canli': False}
    h = takimlarim._mac(m, 1)
    assert '<i>' not in h.replace('<i class', '')
    assert 'data-mac="5&quot;&gt;&lt;i&gt;"' in h


# ------------------------------------------------------------ hata metinleri arayüze sızmaz

def test_hata_ozeti_ayrinti_sizdirmaz():
    import urllib.error
    from mac_tahmin.veri import hata_ozeti
    ag = hata_ozeti(urllib.error.URLError(r'C:\gizli\yol [Errno 11001] getaddrinfo failed'))
    assert 'internet' in ag and 'gizli' not in ag
    assert 'internet' in hata_ozeti(TimeoutError('zaman aşımı'))
    assert 'internet' in hata_ozeti(ConnectionResetError())
    diger = hata_ozeti(KeyError(r'C:\gizli\dosya.json'))
    assert 'gizli' not in diger and 'KeyError' not in diger and diger


def test_ortak_hata_metni_gunluge_yazar_ve_gizler(caplog):
    from mac_tahmin.arayuz.ortak import hata_metni
    with caplog.at_level(logging.WARNING):
        metin = hata_metni(PermissionError(r'C:\Users\gizli\ham\x.json'), 'maç ayrıntısı')
    assert 'gizli' not in metin
    assert 'gizli' in caplog.text and 'maç ayrıntısı' in caplog.text


# ------------------------------------------------------------ "Şimdi güncelle" sınırı

def _guncelleyici(tmp_path):
    from mac_tahmin.guncelleme import Guncelleyici
    return Guncelleyici(tmp_path / 'd', tmp_path / 'ham', yaz=lambda s: None)


def test_simdi_guncelle_aralik_siniri(tmp_path, monkeypatch):
    from mac_tahmin import guncelleme
    g = _guncelleyici(tmp_path)
    an = [1000.0]
    monkeypatch.setattr(guncelleme.time, 'monotonic', lambda: an[0])
    assert g.simdi_kalan_sn() == 0
    assert g.simdi_guncelle() is True and g._simdi.is_set()
    g._simdi.clear()
    an[0] += 10
    assert g.simdi_guncelle() is False and not g._simdi.is_set()  # sınırlandı: istek iletilmez
    assert 49 <= g.simdi_kalan_sn() <= 50
    an[0] += guncelleme.SIMDI_ARALIK_SN
    assert g.simdi_kalan_sn() == 0
    assert g.simdi_guncelle() is True and g._simdi.is_set()


def test_simdi_guncelle_es_zamanli_cagrilarda_tek_istek(tmp_path):
    import threading
    g = _guncelleyici(tmp_path)
    sonuc = []
    ipler = [threading.Thread(target=lambda: sonuc.append(g.simdi_guncelle())) for _ in range(20)]
    [t.start() for t in ipler]
    [t.join() for t in ipler]
    assert sonuc.count(True) == 1


def test_canli_hata_ayrinti_icermez(tmp_path, monkeypatch):
    from mac_tahmin import guncelleme
    g = _guncelleyici(tmp_path)
    kayit = []
    g.yaz = kayit.append

    def patla(*a, **k):
        raise OSError(r'C:\Users\gizli\x')

    class Dur(Exception):
        pass

    def uyku(_):
        raise Dur
    monkeypatch.setattr(guncelleme, 'canli_skorlar', patla)
    monkeypatch.setattr(guncelleme, 'stadyum_oku', lambda *a: {})
    monkeypatch.setattr(guncelleme.time, 'sleep', uyku)
    with pytest.raises(Dur):
        g._canli_dongu()
    assert g.canli_hata and 'gizli' not in g.canli_hata
    assert kayit and all('gizli' not in k for k in kayit)


# ------------------------------------------------------------ bildirim sesi yükleme

MP3_ID3 = b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'\x00' * 64
MP3_CERCEVE = b'\xff\xfb\x90\x00' + b'\x00' * 64
WAV = b'RIFF\x24\x00\x00\x00WAVEfmt ' + b'\x00' * 32


@pytest.fixture
def ses_klasoru(tmp_path, monkeypatch):
    from mac_tahmin.arayuz import bildirim
    klasor = tmp_path / 'sesler'
    monkeypatch.setattr(bildirim, 'SES_KLASORU', klasor)
    return klasor


@pytest.mark.parametrize('uzanti,icerik,beklenen', [
    ('.mp3', MP3_ID3, True), ('.mp3', MP3_CERCEVE, True), ('.MP3', MP3_ID3, True), ('.wav', WAV, True),
    ('.wav', b'RIFF\x00\x00\x00\x00AVI LIST' + b'\x00' * 20, False),   # RIFF ama WAVE değil
    ('.mp3', WAV, False), ('.wav', MP3_ID3, False),                     # uzantı ile içerik uyuşmuyor
    ('.mp3', b'MZ\x90\x00' + b'\x00' * 60, False),                      # çalıştırılabilir dosya
    ('.mp3', b'<html><script>', False), ('.mp3', b'', False), ('.wav', b'RIFF', False), ('.mp3', b'\xff', False),
    ('.mp3', b'\xff\xe0\x00\x00' + b'\x00' * 20, False),                # eşleme biti var ama katman 00 (geçersiz)
    ('.ogg', MP3_ID3, False), ('', MP3_ID3, False),
])
def test_ses_icerigi_gecerli_mi(uzanti, icerik, beklenen):
    from mac_tahmin.arayuz.bildirim import ses_icerigi_gecerli_mi
    assert ses_icerigi_gecerli_mi(uzanti, icerik) is beklenen


def test_ses_ekle_gecerli_dosyayi_kaydeder(ses_klasoru):
    from mac_tahmin.arayuz import bildirim
    assert bildirim.ses_ekle('Düdük.mp3', MP3_ID3) == 'Düdük.mp3'
    assert bildirim.ses_ekle('Düdük.mp3', MP3_ID3) == 'Düdük 2.mp3'
    assert bildirim.ses_ekle('gol.WAV', WAV) == 'gol.wav'
    assert (ses_klasoru / 'gol.wav').read_bytes() == WAV


def test_ses_ekle_sahte_icerigi_reddeder(ses_klasoru):
    from mac_tahmin.arayuz import bildirim
    with pytest.raises(ValueError, match='geçerli'):
        bildirim.ses_ekle('virus.mp3', b'MZ' + b'\x00' * 100)
    with pytest.raises(ValueError):
        bildirim.ses_ekle('x.mp3', WAV)
    with pytest.raises(ValueError):
        bildirim.ses_ekle('x.exe', MP3_ID3)
    assert not ses_klasoru.exists() or list(ses_klasoru.iterdir()) == []


def test_ses_ekle_yol_gezintisi_dosya_adi_klasore_hapsolur(ses_klasoru):
    from mac_tahmin.arayuz import bildirim
    ad = bildirim.ses_ekle(r'..\..\kotu.mp3', MP3_ID3)
    assert (ses_klasoru / ad).exists() and ad == 'kotu.mp3'
    assert [f.name for f in ses_klasoru.parent.iterdir()] == ['sesler']


def test_ses_ekle_dosya_sayisi_sinirli(ses_klasoru, monkeypatch):
    from mac_tahmin.arayuz import bildirim
    monkeypatch.setattr(bildirim, 'SES_EN_COK_DOSYA', 3)
    for i in range(3):
        bildirim.ses_ekle(f's{i}.mp3', MP3_ID3)
    with pytest.raises(ValueError, match='En çok 3'):
        bildirim.ses_ekle('fazla.mp3', MP3_ID3)
    assert len(list(ses_klasoru.iterdir())) == 3


def test_ses_ekle_toplam_boyut_sinirli(ses_klasoru, monkeypatch):
    from mac_tahmin.arayuz import bildirim
    monkeypatch.setattr(bildirim, 'SES_TOPLAM_EN_BUYUK', 300)
    bildirim.ses_ekle('a.mp3', MP3_ID3 + b'\x00' * 130)   # 204 bayt
    with pytest.raises(ValueError, match='toplam'):
        bildirim.ses_ekle('b.mp3', MP3_ID3 + b'\x00' * 130)
    assert [f.name for f in ses_klasoru.iterdir()] == ['a.mp3']


def test_ses_ekle_tek_dosya_siniri(ses_klasoru, monkeypatch):
    from mac_tahmin.arayuz import bildirim
    monkeypatch.setattr(bildirim, 'SES_EN_BUYUK', 100)
    with pytest.raises(ValueError, match='5 MB|en çok'):
        bildirim.ses_ekle('b.mp3', MP3_ID3 + b'\x00' * 100)


def test_varsayilan_sinirlar_makul():
    from mac_tahmin.arayuz import bildirim
    assert bildirim.SES_EN_COK_DOSYA == 20
    assert bildirim.SES_TOPLAM_EN_BUYUK == 50 * 1024 * 1024


# ------------------------------------------------------------ sunucu adresi (127.0.0.1) ve isteğe bağlı erişim anahtarı

@pytest.mark.parametrize('host,beklenen', [('127.0.0.1', True), ('localhost', True), ('LOCALHOST', True), ('::1', True),
                                           ('[::1]', True), ('127.0.0.2', True), ('0.0.0.0', False), ('', False),
                                           (None, False), ('192.168.1.5', False), ('::', False), ('mac.example', False),
                                           ('127.0.0.1.evil.com', False)])
def test_loopback_mi(host, beklenen):
    from mac_tahmin.arayuz.erisim import loopback_mi
    assert loopback_mi(host) is beklenen


def test_adres_uyarisi():
    from mac_tahmin.arayuz.erisim import adres_uyarisi
    assert adres_uyarisi('127.0.0.1', False) == ''
    uyari = adres_uyarisi('0.0.0.0', False)
    assert 'parola' in uyari and 'ağ' in uyari and 'MAC_TAHMIN_ANAHTAR' in uyari
    korumali = adres_uyarisi('192.168.1.5', True)
    assert 'anahtar' in korumali and 'MAC_TAHMIN_ANAHTAR' not in korumali


def _calistir_kaydi(monkeypatch):
    kayit = {}

    def sahte(veri, ham, **kw):
        kayit.update(kw, veri=veri, ham=ham)
    import mac_tahmin.arayuz as arayuz
    monkeypatch.setattr(arayuz, 'calistir', sahte)
    return kayit


@pytest.mark.parametrize('komut,pencere', [('sunucu', False), ('uygulama', True)])
def test_komut_satiri_varsayilan_host_loopback(monkeypatch, capsys, komut, pencere):
    from mac_tahmin import __main__ as ana
    kayit = _calistir_kaydi(monkeypatch)
    monkeypatch.delenv('MAC_TAHMIN_ANAHTAR', raising=False)
    ana.main([komut, '--port', '8099', '--tarayici-acma'])
    assert kayit['host'] == '127.0.0.1' and kayit['port'] == 8099 and kayit['pencere'] is pencere
    cikti = capsys.readouterr().out
    assert 'UYARI' not in cikti
    if not pencere:
        assert 'http://localhost:8099/' in cikti


def test_komut_satiri_host_secenegi_uyari_yazar(monkeypatch, capsys):
    from mac_tahmin import __main__ as ana
    monkeypatch.delenv('MAC_TAHMIN_ANAHTAR', raising=False)
    kayit = _calistir_kaydi(monkeypatch)
    ana.main(['sunucu', '--host', '0.0.0.0', '--port', '8099', '--tarayici-acma'])
    assert kayit['host'] == '0.0.0.0'
    cikti = capsys.readouterr().out
    assert 'UYARI' in cikti and 'parola' in cikti
    assert 'http://localhost:8099/' not in cikti and 'http://0.0.0.0:8099/' in cikti


def test_calistir_ui_run_a_host_gecirir(monkeypatch, tmp_path):
    """ui.run'a host verilir (verilmezse NiceGUI tarayıcı modunda 0.0.0.0 açar). Sunucu başlatılmaz, ağa çıkılmaz."""
    from types import SimpleNamespace

    from nicegui import app, ui

    import mac_tahmin.arayuz as arayuz
    from mac_tahmin import guncelleme
    from mac_tahmin.arayuz import bildirim, depo, takip
    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagrilar = []
    monkeypatch.setattr(ui, 'run', lambda *a, **k: cagrilar.append(k))
    monkeypatch.setattr(app, 'on_startup', lambda f: None)
    monkeypatch.setattr(app, 'add_static_files', lambda *a, **k: None)
    monkeypatch.setattr(ui, 'add_head_html', lambda *a, **k: None)
    monkeypatch.setattr(app, 'add_middleware', lambda *a, **k: cagrilar.append({'ara_katman': a}))
    monkeypatch.setattr(guncelleme.Guncelleyici, 'baslat', lambda self: self)
    monkeypatch.setattr(depo, 'Depo', lambda *a, **k: SimpleNamespace(scout_on_hazirla=lambda: None))
    monkeypatch.setattr(takip, 'baslat', lambda: None)
    monkeypatch.setattr(bildirim, 'kaydet', lambda *a: None)
    monkeypatch.delenv('MAC_TAHMIN_ANAHTAR', raising=False)
    arayuz.calistir(tmp_path / 'd', tmp_path / 'ham', tarayici_ac=False)
    assert len(cagrilar) == 2 and cagrilar[-1]['host'] == '127.0.0.1' and cagrilar[-1]['native'] is False  # + yerel Host koruması
    cagrilar.clear()
    arayuz.calistir(tmp_path / 'd', tmp_path / 'ham', tarayici_ac=False, host='0.0.0.0')
    assert cagrilar[-1]['host'] == '0.0.0.0'
    assert not any(c.get('ara_katman', [0])[0] is AnahtarKorumasi for c in cagrilar)  # anahtar tanımlı değil: katman yok
    cagrilar.clear()
    monkeypatch.setenv('MAC_TAHMIN_ANAHTAR', 'gizli-anahtar-123')
    arayuz.calistir(tmp_path / 'd', tmp_path / 'ham', tarayici_ac=False, host='0.0.0.0')
    assert any(c.get('ara_katman', [0])[0] is AnahtarKorumasi for c in cagrilar)  # dışa açık + anahtar: koruma devrede
    cagrilar.clear()
    arayuz.calistir(tmp_path / 'd', tmp_path / 'ham', tarayici_ac=False)  # yerel adres: anahtar gerekmez
    assert not any(c.get('ara_katman', [0])[0] is AnahtarKorumasi for c in cagrilar)


# ---- ASGI ara katmanı

async def _asgi(katman, tur='http', yol='/', sorgu=b'', cerezler=None, ek_basliklar=()):
    gonderilen = []
    basliklar = ([(b'cookie', cerezler.encode())] if cerezler else []) + list(ek_basliklar)

    async def al():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def gonder(m):
        gonderilen.append(m)
    scope = {'type': tur, 'path': yol, 'query_string': sorgu, 'headers': basliklar, 'method': 'GET'}
    await katman(scope, al, gonder)
    return gonderilen


def _uygulama(cagri):
    async def uyg(scope, receive, send):
        cagri.append(scope['type'])
        if scope['type'] == 'http':
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'tamam'})
    return uyg


def test_katman_anahtarsiz_istegi_reddeder():
    import asyncio

    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagri = []
    katman = AnahtarKorumasi(_uygulama(cagri), 'sir')
    cikti = asyncio.run(_asgi(katman))
    assert cikti[0]['status'] == 401 and cagri == []
    assert b'sir' not in b''.join(m.get('body', b'') for m in cikti)
    yanlis = asyncio.run(_asgi(katman, sorgu=b'anahtar=yanlis', cerezler='mac_tahmin_anahtar=baska'))
    assert yanlis[0]['status'] == 401 and cagri == []


def test_katman_websocketi_anahtarsiz_kapatir():
    import asyncio

    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagri = []
    cikti = asyncio.run(_asgi(AnahtarKorumasi(_uygulama(cagri), 'sir'), tur='websocket'))
    assert cikti == [{'type': 'websocket.close', 'code': 1008}] and cagri == []


def test_katman_dogru_anahtar_cerez_birakip_yonlendirir():
    import asyncio

    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagri = []
    katman = AnahtarKorumasi(_uygulama(cagri), 'sir')
    cikti = asyncio.run(_asgi(katman, yol='/sayfa', sorgu=b'anahtar=sir&x=1'))
    bas = cikti[0]
    basliklar = dict(bas['headers'])
    assert bas['status'] == 303 and cagri == []
    assert basliklar[b'location'] == b'/sayfa?x=1'  # anahtar adres çubuğunda kalmaz
    assert b'mac_tahmin_anahtar=sir' in basliklar[b'set-cookie']
    assert b'HttpOnly' in basliklar[b'set-cookie'] and b'SameSite=Strict' in basliklar[b'set-cookie']


def test_katman_cerezle_gecer_http_ve_websocket():
    import asyncio

    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagri = []
    katman = AnahtarKorumasi(_uygulama(cagri), 'sir')
    cikti = asyncio.run(_asgi(katman, cerezler='baska=1; mac_tahmin_anahtar=sir'))
    assert cikti[0]['status'] == 200 and cagri == ['http']
    asyncio.run(_asgi(katman, tur='websocket', cerezler='mac_tahmin_anahtar=sir'))
    assert cagri == ['http', 'websocket']


def test_katman_lifespan_gecer():
    import asyncio

    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagri = []
    asyncio.run(_asgi(AnahtarKorumasi(_uygulama(cagri), 'sir'), tur='lifespan'))
    assert cagri == ['lifespan']


def test_katman_bearer_basligiyla_gecer():
    import asyncio

    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagri = []
    katman = AnahtarKorumasi(_uygulama(cagri), 'sir')
    cikti = asyncio.run(_asgi(katman, ek_basliklar=[(b'authorization', b'Bearer sir')]))
    assert cikti[0]['status'] == 200 and cagri == ['http']  # çerez ve sorgu gerekmez, yönlendirme olmaz
    asyncio.run(_asgi(katman, tur='websocket', ek_basliklar=[(b'authorization', b'bearer sir')]))
    assert cagri == ['http', 'websocket']


@pytest.mark.parametrize('baslik', [b'Bearer yanlis', b'Bearer', b'Bearer ', b'Basic sir', b'sir', b'Bearer sir extra'])
def test_katman_yanlis_bearer_reddeder(baslik):
    import asyncio

    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    cagri = []
    cikti = asyncio.run(_asgi(AnahtarKorumasi(_uygulama(cagri), 'sir'), ek_basliklar=[(b'authorization', baslik)]))
    assert cikti[0]['status'] == 401 and cagri == []


def test_anahtar_gunluk_maskeleme():
    from mac_tahmin.arayuz.erisim import AnahtarMaskeleme
    f = AnahtarMaskeleme()
    kayit = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                              ('127.0.0.1:5', 'GET', '/sayfa?x=1&anahtar=gizli.Sir~1&y=2', '1.1', 303), None)
    assert f.filter(kayit) is True
    yazi = kayit.getMessage()
    assert 'gizli' not in yazi and 'anahtar=***' in yazi and 'x=1' in yazi and 'y=2' in yazi
    duz = logging.LogRecord('x', logging.WARNING, __file__, 1, 'GET /?anahtar=gizli HTTP/1.1 ve ?ANAHTAR=Gizli2', None, None)
    assert f.filter(duz) is True and 'izli' not in duz.getMessage()
    temiz = logging.LogRecord('x', logging.INFO, __file__, 1, 'sıradan %s', ('mesaj',), None)
    f.filter(temiz)
    assert temiz.getMessage() == 'sıradan mesaj'


def test_anahtar_maskeleme_uvicorn_erisim_gunlugunde_ve_dosya_gunlugunde(tmp_path):
    import copy
    import logging.config

    from uvicorn.config import LOGGING_CONFIG

    from mac_tahmin import masaustu
    from mac_tahmin.arayuz import erisim
    erisim.gunlukte_anahtari_gizle()
    logging.config.dictConfig(copy.deepcopy(LOGGING_CONFIG))  # uvicorn sunucu başlarken yapar: süzgeç korunmalı
    kayitlar = []

    class Topla(logging.Handler):
        def emit(self, kayit):
            kayitlar.append(kayit.getMessage())
    topla = Topla()
    erisim_gunlugu = logging.getLogger('uvicorn.access')
    erisim_gunlugu.addHandler(topla)
    try:
        erisim_gunlugu.setLevel(logging.INFO)
        erisim_gunlugu.info('%s - "%s %s HTTP/%s" %d', '1.2.3.4:5', 'GET', '/?anahtar=sirrr', '1.1', 303)
    finally:
        erisim_gunlugu.removeHandler(topla)
    assert kayitlar and 'sirrr' not in kayitlar[0] and 'anahtar=***' in kayitlar[0]
    akis, isleyici = masaustu.gunluk_kur(tmp_path / 'u.log')
    try:
        logging.getLogger('baska.kutuphane').warning('istek: /x?anahtar=sirrr')
    finally:
        logging.getLogger().removeHandler(isleyici)
        isleyici.close()
    yazi = (tmp_path / 'u.log').read_text(encoding='utf-8')
    assert 'istek: /x?anahtar=***' in yazi and 'sirrr' not in yazi


# ---- DNS yeniden bağlama (yerel kipte Host denetimi)

@pytest.mark.parametrize('host,gecer', [
    (b'localhost', True), (b'localhost:8080', True), (b'127.0.0.1:8080', True), (b'127.0.0.1', True),
    (b'[::1]:8080', True), (b'[::1]', True), (b'LOCALHOST:1', True),
    (b'evil.com', False), (b'evil.com:8080', False), (b'localhost.evil.com', False), (b'127.0.0.1.evil.com:80', False),
    (b'127.0.0.2:8080', False), (b'localhost:abc', False), (b'[::2]:80', False), (b'localhost@evil.com', False),
    (b'', False), (b'0.0.0.0:8080', False)])
def test_host_korumasi_http_ve_websocket(host, gecer):
    import asyncio

    from mac_tahmin.arayuz.erisim import YerelHostKorumasi
    cagri = []
    katman = YerelHostKorumasi(_uygulama(cagri))
    http = asyncio.run(_asgi(katman, ek_basliklar=[(b'host', host)]))
    ws = asyncio.run(_asgi(katman, tur='websocket', ek_basliklar=[(b'host', host)]))
    if gecer:
        assert http[0]['status'] == 200 and cagri == ['http', 'websocket']
    else:
        assert http[0]['status'] == 403 and ws == [{'type': 'websocket.close', 'code': 1008}] and cagri == []


def test_host_korumasi_basliksiz_istegi_reddeder_lifespan_gecer():
    import asyncio

    from mac_tahmin.arayuz.erisim import YerelHostKorumasi
    cagri = []
    katman = YerelHostKorumasi(_uygulama(cagri))
    assert asyncio.run(_asgi(katman))[0]['status'] == 403 and cagri == []
    asyncio.run(_asgi(katman, tur='lifespan'))
    assert cagri == ['lifespan']


def test_calistir_yerel_adreste_host_korumasi_ekler(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from nicegui import app, ui

    import mac_tahmin.arayuz as arayuz
    from mac_tahmin import guncelleme
    from mac_tahmin.arayuz import bildirim, depo, erisim, takip
    katmanlar = []
    monkeypatch.setattr(ui, 'run', lambda *a, **k: None)
    monkeypatch.setattr(app, 'on_startup', lambda f: None)
    monkeypatch.setattr(app, 'add_static_files', lambda *a, **k: None)
    monkeypatch.setattr(ui, 'add_head_html', lambda *a, **k: None)
    monkeypatch.setattr(app, 'add_middleware', lambda sinif, **k: katmanlar.append(sinif))
    monkeypatch.setattr(guncelleme.Guncelleyici, 'baslat', lambda self: self)
    monkeypatch.setattr(depo, 'Depo', lambda *a, **k: SimpleNamespace(scout_on_hazirla=lambda: None))
    monkeypatch.setattr(takip, 'baslat', lambda: None)
    monkeypatch.setattr(bildirim, 'kaydet', lambda *a: None)
    monkeypatch.delenv('MAC_TAHMIN_ANAHTAR', raising=False)
    arayuz.calistir(tmp_path / 'd', tmp_path / 'ham', tarayici_ac=False)
    assert katmanlar == [erisim.YerelHostKorumasi]
    katmanlar.clear()
    arayuz.calistir(tmp_path / 'd', tmp_path / 'ham', tarayici_ac=False, pencere=True)  # pywebview 127.0.0.1 / localhost açar
    assert katmanlar == [erisim.YerelHostKorumasi]
    katmanlar.clear()
    arayuz.calistir(tmp_path / 'd', tmp_path / 'ham', tarayici_ac=False, host='0.0.0.0')  # dışa açık: LAN adresiyle girilir
    assert katmanlar == []


def test_katman_bos_anahtarla_kurulamaz():
    from mac_tahmin.arayuz.erisim import AnahtarKorumasi
    with pytest.raises(ValueError):
        AnahtarKorumasi(_uygulama([]), '')


# ------------------------------------------------------------ dönen günlük

def test_gunluk_boyutu_sinirli_ve_yedekli(tmp_path):
    from mac_tahmin import masaustu
    yol = tmp_path / 'uygulama.log'
    akis, isleyici = masaustu.gunluk_kur(yol, en_buyuk=2000, yedek=2)
    try:
        for i in range(200):
            akis.write(f'satır {i} ' + 'x' * 50 + '\n')
        logging.getLogger('mac_tahmin.deneme').warning('uyarı kaydı')
        akis.write('yarım satır')  # satır sonu gelmeyen kısım bekler
    finally:
        logging.getLogger().removeHandler(isleyici)
        isleyici.close()
    dosyalar = sorted(f.name for f in tmp_path.iterdir())
    assert dosyalar == ['uygulama.log', 'uygulama.log.1', 'uygulama.log.2']  # en çok 2 yedek
    assert all(f.stat().st_size < 2000 + 200 for f in tmp_path.iterdir())
    son = yol.read_text(encoding='utf-8')
    assert 'uyarı kaydı' in son and 'WARNING' in son and 'yarım' not in son
    assert '\nsatır 199 ' in '\n' + son  # print çıktısı olduğu gibi (başında tarih/düzey yok)


def test_gunluk_akisi_kendi_hatasinda_sonsuz_donguye_girmez(tmp_path, monkeypatch):
    import sys
    from mac_tahmin import masaustu
    akis, isleyici = masaustu.gunluk_kur(tmp_path / 'u.log')
    monkeypatch.setattr(sys, 'stderr', akis)  # uygulamadaki gibi: logging'in kendi hata çıktısı da akışa döner
    try:
        def bozuk(metin):
            raise OSError('disk dolu')
        isleyici.stream.write = bozuk  # günlük dosyasına yazılamıyor: logging hatayı stderr'e (akışa) basar
        akis.write('merhaba\n')  # tekrar tekrar kendini çağırmamalı (RecursionError olmaz)
    finally:
        logging.getLogger().removeHandler(isleyici)
        isleyici.close()


# ------------------------------------------------------------ bağımlılık sürümleri

def test_requirements_uyumlu_surum_sabitlemesi():
    kok = Path(__file__).resolve().parent.parent
    satirlar = [s.split('#')[0].strip() for s in (kok / 'requirements.txt').read_text(encoding='utf-8').splitlines()]
    satirlar = [s for s in satirlar if s]
    adlar = {re.split(r'[~=<>]', s)[0]: s for s in satirlar}
    assert set(adlar) == {'nicegui', 'numpy', 'pywebview', 'pyinstaller', 'pillow'}
    assert all('~=' in s for s in satirlar), satirlar
    assert adlar['nicegui'] == 'nicegui~=3.17.1'
