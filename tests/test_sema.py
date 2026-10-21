"""Dış kaynak yanıt biçimi denetimi (sema.py) ve sözleşme testleri: gerçek yanıtlardan kırpılmış örnekler
(tests/fixtures/kaynak/) hem şemayı geçmeli hem de ayrıştırıcılar onlarla çalışmalı. FotMob bir alanı yeniden
adlandırırsa bu testler değil, çalışma anındaki kontrol() uyarır; buradakiler uyarının doğru çalıştığını sınar."""
import copy
import json
import logging
import re
from pathlib import Path

import pytest

from mac_tahmin import avrupa, canli, dogum, hakem, lig_maclari, mac_ozeti, milli, sema, takim, veri
from mac_tahmin.sezon import Sezon

KLASOR = Path(__file__).parent / 'fixtures' / 'kaynak'
# örnek dosya -> geçmesi gereken yanıt türleri
ORNEKLER = {
    'lig': ['lig', 'kupa'], 'kupa': ['kupa'], 'oyuncu_liste': ['oyuncu_liste'], 'takim_liste': ['takim_liste'],
    'understat': ['understat'], 'takim': ['takim', 'takim_stadyum'], 'canli': ['canli'], 'mac': ['mac'],
    'oyuncu': ['oyuncu'],
}
SIL = object()


def yukle(ad):
    return json.loads((KLASOR / f'{ad}.json').read_text(encoding='utf-8'))


def degistir(veri_, yol, deger=SIL):
    """veri_'nin kopyası; yol (anahtar/indeks dizisi) deger ile değiştirilir ya da (SIL) silinir."""
    v = copy.deepcopy(veri_)
    hedef = v
    for k in yol[:-1]:
        hedef = hedef[k]
    if deger is SIL:
        del hedef[yol[-1]]
    else:
        hedef[yol[-1]] = deger
    return v


@pytest.fixture(autouse=True)
def _temiz():
    sema.temizle()
    yield
    sema.temizle()


# ---------------------------------------------------------------- şema: örnekler geçer, bozuk yanıt yakalanır

def test_her_tur_icin_ornek_var_ve_tersi():
    assert {t for ts in ORNEKLER.values() for t in ts} == set(sema.TURLER)


@pytest.mark.parametrize('ornek,tur', [(o, t) for o, ts in ORNEKLER.items() for t in ts])
def test_ornek_yanit_temiz_gecer(ornek, tur):
    assert sema.denetle(tur, yukle(ornek)) == []


@pytest.mark.parametrize('tur,ornek,yol,beklenen', [
    ('lig', 'lig', ('fixtures', 'allMatches', 0, 'home', 'name'), 'fixtures.allMatches[].home.name:s (eksik)'),
    ('lig', 'lig', ('details', 'selectedSeason'), 'details.selectedSeason:s (eksik)'),
    ('lig', 'lig', ('fixtures', 'allMatches'), 'fixtures.allMatches:l (eksik)'),
    ('lig', 'lig', ('stats', 'players', 0, 'fetchAllUrl'), 'stats.players[].fetchAllUrl:s (eksik)'),
    ('kupa', 'kupa', ('fixtures', 'allMatches', 0, 'status', 'utcTime'), 'fixtures.allMatches[].status.utcTime:s (eksik)'),
    ('kupa', 'kupa', ('playoff', 'rounds', 0, 'matchups', 0, 'matches', 0, 'matchId'),
     'playoff.rounds[].matchups[].matches[].matchId (eksik)'),
    ('oyuncu_liste', 'oyuncu_liste', ('TopLists', 0, 'StatList', 0, 'ParticiantId'), 'TopLists[].StatList[].ParticiantId (eksik)'),
    ('oyuncu_liste', 'oyuncu_liste', ('TopLists',), 'TopLists:l (eksik)'),
    ('takim_liste', 'takim_liste', ('TopLists', 0, 'StatList', 0, 'TeamId'), 'TopLists[].StatList[].TeamId (eksik)'),
    ('understat', 'understat', ('dates', 0, 'xG'), ['dates[].xG.h (eksik)', 'dates[].xG.a (eksik)']),
    ('understat', 'understat', ('players', 0, 'xGChain'), 'players[].xGChain:n (eksik)'),
    ('understat', 'understat', ('teams',), 'teams:d (eksik)'),
    ('takim', 'takim', ('fixtures', 'allFixtures', 'fixtures', 0, 'tournament'),
     'fixtures.allFixtures.fixtures[].tournament.leagueId (eksik)'),
    ('takim', 'takim', ('details', 'name'), 'details.name:s (eksik)'),
    ('takim', 'takim', ('squad', 'squad', 0, 'members', 0, 'name'), 'squad.squad[].members[].name:s (eksik)'),
    ('takim_stadyum', 'takim', ('overview', 'venue', 'widget', 'name'), 'overview.venue.widget.name:s (eksik)'),
    ('canli', 'canli', ('leagues', 0, 'matches', 0, 'home', 'name'), 'leagues[].matches[].home.name:s (eksik)'),
    ('canli', 'canli', ('leagues', 0, 'primaryId'), 'leagues[].primaryId (eksik)'),
    ('mac', 'mac', ('header', 'teams'), 'header.teams:l (eksik)'),
    ('mac', 'mac', ('content', 'matchFacts', 'infoBox', 'Referee', 'text'), 'content.matchFacts.infoBox.Referee.text:s (eksik)'),
    ('oyuncu', 'oyuncu', ('birthDate', 'utcTime'), 'birthDate.utcTime:s (eksik)'),
    ('oyuncu', 'oyuncu', ('recentMatches', 0, 'matchDate'), 'recentMatches[].matchDate:d (eksik)'),
])
def test_eksik_ya_da_yeniden_adlandirilmis_alan_yakalanir(tur, ornek, yol, beklenen):
    # Act
    sorunlar = sema.denetle(tur, degistir(yukle(ornek), yol))
    # Assert
    assert sorunlar == (beklenen if isinstance(beklenen, list) else [beklenen])


def test_alan_yeniden_adlandirilinca_eskisi_eksik_sayilir():
    v = yukle('canli')
    m = v['leagues'][0]['matches'][0]
    m['homeTeam'] = m.pop('home')
    assert sema.denetle('canli', v) == ['leagues[].matches[].home.id (eksik)', 'leagues[].matches[].home.name:s (eksik)']


def test_turu_tutmayan_alan_yakalanir():
    v = degistir(yukle('lig'), ('fixtures', 'allMatches', 0, 'status', 'finished'), 'evet')
    assert sema.denetle('lig', v) == ['fixtures.allMatches[].status.finished:b (beklenen mantıksal, gelen str)']


def test_liste_beklenirken_sozluk_gelirse_yakalanir():
    v = degistir(yukle('lig'), ('fixtures', 'allMatches'), {'a': 1})
    assert sema.denetle('lig', v) == ['fixtures.allMatches:l (beklenen liste, gelen dict)']  # altındakiler yinelenmez


def test_tipli_alan_none_ise_bos_deger_sayilir():
    v = degistir(yukle('lig'), ('details', 'selectedSeason'), None)
    assert sema.denetle('lig', v) == ['details.selectedSeason:s (boş değer)']


def test_tipsiz_alan_none_olabilir():
    # oynanmamış Understat maçında gol ve xG anahtarı vardır ama değeri None
    v = yukle('understat')
    assert v['dates'][1]['goals'] == {'h': None, 'a': None}
    assert sema.denetle('understat', v) == []


def test_understat_sayilari_yazi_olarak_gelebilir_ama_sayi_degilse_yakalanir():
    v = yukle('understat')
    assert isinstance(v['players'][0]['xG'], str)
    bozuk = degistir(v, ('players', 0, 'xG'), 'yok')
    assert sema.denetle('understat', bozuk) == ['players[].xG:n (beklenen sayı, gelen str)']
    assert sema.denetle('understat', degistir(v, ('players', 0, 'xG'), 1.5)) == []


def test_bos_liste_ve_bos_ust_halka_sessizce_gecilir():
    # kadrosu olmayan takım: squad None; maçı olmayan gün: leagues boş
    assert sema.denetle('takim', degistir(yukle('takim'), ('squad',), None)) == []
    assert sema.denetle('canli', {'leagues': []}) == []
    assert sema.denetle('oyuncu', {}) == []  # oyuncu sayfasında her alan isteğe bağlı


def test_istege_bagli_yolda_arada_eksik_sessiz_son_halka_eksik_hatali():
    v = yukle('takim')
    del v['overview']['venue']
    assert sema.denetle('takim_stadyum', v) == []  # stadyumu olmayan takım
    v['overview']['venue'] = {'widget': {'city': 'X'}}
    assert 'overview.venue.widget.name:s (eksik)' in sema.denetle('takim_stadyum', v)


@pytest.mark.parametrize('kok', [None, [], 'metin', 5])
def test_kok_sozluk_degilse_hata_listesi_doner(kok):
    assert sema.denetle('lig', kok) == [f'(kök) beklenen sözlük, gelen {type(kok).__name__}']


def test_bilinmeyen_tur_denetle_icinde_hata_verir_kontrol_icinde_vermez():
    with pytest.raises(KeyError):
        sema.denetle('yok', {})
    assert sema.kontrol('yok', {}) == []
    assert sema.sorunlar() == {}


def test_denetle_ornegi_degistirmez():
    v = yukle('lig')
    kopya = copy.deepcopy(v)
    sema.denetle('lig', v)
    assert v == kopya


def test_buyuk_yanit_hizli_denetlenir():
    # yalnızca ilk öğe örneklenir: 20 bin maçlık liste de tek öğe kadar iş yapar
    v = yukle('lig')
    v['fixtures']['allMatches'] = v['fixtures']['allMatches'] * 10000
    assert sema.denetle('lig', v) == []


def test_kaynak_kodundaki_butun_kontrol_cagrilari_bilinen_tur_kullanir():
    kok = Path(__file__).resolve().parent.parent / 'mac_tahmin'
    turler = set()
    for f in kok.rglob('*.py'):
        turler |= set(re.findall(r"sema\.kontrol\(\s*'([a-z_]+)'", f.read_text(encoding='utf-8')))
        for cift in re.findall(r"sema\.kontrol\(\s*'([a-z_]+)' if \w+ == '\w+' else '([a-z_]+)'", f.read_text(encoding='utf-8')):
            turler |= set(cift)
    assert turler  # çağrılar bulundu
    assert turler <= set(sema.TURLER)


# ---------------------------------------------------------------- kayıt (sorunlar) ve uyarı metni

def test_kontrol_sorunu_kaydeder_ve_temiz_yanit_siler():
    bozuk = degistir(yukle('canli'), ('leagues', 0, 'matches', 0, 'home', 'name'))
    # Act + Assert
    assert sema.kontrol('canli', bozuk) == ['leagues[].matches[].home.name:s (eksik)']
    zaman, eksik = sema.sorunlar()['canli']
    assert eksik == ['leagues[].matches[].home.name:s (eksik)'] and zaman is not None
    assert sema.kontrol('canli', yukle('canli')) == []
    assert sema.sorunlar() == {}


def test_turler_birbirinin_kaydini_silmez():
    sema.kontrol('canli', {'leagues': 5})
    sema.kontrol('lig', yukle('lig'))  # başka tür temiz geldi
    assert set(sema.sorunlar()) == {'canli'}


def test_sorunlar_kopya_doner():
    sema.kontrol('canli', {})
    sema.sorunlar().clear()
    assert 'canli' in sema.sorunlar()


def test_ayni_sorun_gunluge_bir_kez_yazilir(caplog):
    with caplog.at_level(logging.INFO, logger='mac_tahmin.sema'):
        for _ in range(3):
            sema.kontrol('canli', {})
        sema.kontrol('canli', yukle('canli'))
    uyarilar = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(uyarilar) == 1
    assert 'FotMob veri biçimi değişmiş olabilir' in uyarilar[0].getMessage()
    assert 'canlı skorlar' in uyarilar[0].getMessage() and 'leagues:l (eksik)' in uyarilar[0].getMessage()
    assert any(r.levelno == logging.INFO and 'düzeldi' in r.getMessage() for r in caplog.records)


def test_degisen_sorun_yeniden_yazilir(caplog):
    with caplog.at_level(logging.WARNING, logger='mac_tahmin.sema'):
        sema.kontrol('canli', {})
        sema.kontrol('canli', {'leagues': [{}]})
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_uyari_metni_bos_ve_dolu():
    assert sema.uyari_metni() == ''
    sema.kontrol('canli', {'leagues': [{'primaryId': 1, 'matches': [{}]}]})
    metin = sema.uyari_metni()
    assert metin.startswith('FotMob veri biçimi değişmiş olabilir: canlı skorlar (')
    assert metin.endswith(' alan eksik). Ayrıntı: uygulama.log')


def test_uyari_metni_kaynaklari_ayirir_ve_alan_sayisini_gosterir():
    sema.kontrol('canli', {})  # 1 alan
    sema.kontrol('takim', {})
    sema.kontrol('understat', {})
    metin = sema.uyari_metni()
    assert 'FotMob veri biçimi değişmiş olabilir: canlı skorlar (1 alan eksik), takım sayfası (' in metin
    assert '; Understat veri biçimi değişmiş olabilir: Understat lig verisi (' in metin
    assert metin.count('Ayrıntı: uygulama.log') == 1


def test_guncelleyici_uyariyi_sema_dan_alir(tmp_path):
    from mac_tahmin.guncelleme import Guncelleyici
    g = Guncelleyici(tmp_path, tmp_path)
    assert g.bicim_uyarisi() == ''
    sema.kontrol('canli', {})
    assert g.bicim_uyarisi() == sema.uyari_metni() != ''


def test_es_zamanli_kontrol_kaydi_bozmaz():
    from concurrent.futures import ThreadPoolExecutor
    bozuk, temiz = {}, yukle('canli')
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda i: sema.kontrol('canli', bozuk if i % 2 else temiz), range(200)))
        list(ex.map(lambda i: sema.kontrol('takim', {}), range(50)))
    assert 'takim' in sema.sorunlar()
    assert set(sema.sorunlar()) <= {'canli', 'takim'}


# ---------------------------------------------------------------- sözleşme: ayrıştırıcılar örneklerle çalışır

def test_understat_donustur_sezon_uyumlu_ham_sozluk_kurar():
    # Arrange
    j = yukle('understat')
    # Act
    ham = veri.understat_donustur(j)
    # Assert
    assert ham['src'] == 'understat' and len(ham['t']) == 4
    assert len(ham['m']) == 1 and len(ham['u']) == 1
    tarih, ev, dep, hg, ag, xg_ev, xg_dep = ham['m'][0]
    assert re.fullmatch(r'\d{4}-\d\d-\d\d', tarih) and isinstance(hg, int) and isinstance(xg_ev, float)
    assert ham['u'][0][3].endswith('Z') and len(ham['p']) == 8
    assert all(len(p[13]) == 4 for p in ham['p'])  # npg, npxG, xGChain, xGBuildup
    assert isinstance(Sezon(ham, 'EPL', 2026), Sezon)


def test_understat_donustur_sema_ile_ayni_alanlari_okur():
    # şemadaki bir alan silinince ayrıştırıcı da gerçekten ona ihtiyaç duyar (sözleşme iki yönlü tutarlı)
    j = degistir(yukle('understat'), ('players', 0, 'xGChain'))
    assert sema.denetle('understat', j)
    with pytest.raises(KeyError):
        veri.understat_donustur(j)


def test_fotmob_sezon_ornek_ham_klasorle_calisir(tmp_path):
    # Arrange: ham önbellek klasörü (lig sayfası + istatistik listeleri), ağ yok
    (tmp_path / 'fm-71-2026.json').write_text(json.dumps(yukle('lig')), encoding='utf-8')
    for ad, liste in yukle_liste_hepsi().items():
        (tmp_path / f'fm-71-2026-{ad}.json').write_text(json.dumps(liste), encoding='utf-8')
    idler = {str(it['ParticiantId']) for it in yukle('oyuncu_liste')['TopLists'][0]['StatList']}
    (tmp_path / 'dogum.json').write_text(json.dumps({i: '2000-01-01' for i in idler}), encoding='utf-8')
    # Act
    ham = veri.fotmob_sezon(2026, tmp_path, lig_id=71)
    # Assert
    assert ham['src'] == 'fotmob' and len(ham['t']) == 4
    assert len(ham['m']) == 1 and len(ham['u']) == 1 and ham['m'][0][3:5] == [2, 2]
    assert len(ham['p']) >= 1 and len(ham['p'][0]) == 19 and len(ham['p'][0][13]) == len(veri.FOTMOB_EK)
    assert sema.sorunlar() == {}
    assert isinstance(Sezon(ham, 'Super_Lig', 2026), Sezon)


def yukle_liste_hepsi():
    return yukle('liste_hepsi')


def test_fotmob_sezon_bozuk_lig_yaniti_kaydedilir(tmp_path):
    bozuk = degistir(yukle('lig'), ('fixtures', 'allMatches', 0, 'status', 'utcTime'))
    (tmp_path / 'fm-71-2026.json').write_text(json.dumps(bozuk), encoding='utf-8')
    with pytest.raises(KeyError):  # ayrıştırıcı düşer ama önce kayıt yapılmış olmalı
        veri.fotmob_sezon(2026, tmp_path, lig_id=71)
    assert 'fixtures.allMatches[].status.utcTime:s (eksik)' in sema.sorunlar()['lig'][1]


def test_canli_gunun_maclari_ornekle_calisir(monkeypatch):
    monkeypatch.setattr(canli, 'json_getir', lambda url: yukle('canli'))
    maclar = canli.gunun_maclari('20260814')
    assert [m['durum'] for m in maclar] == ['bitti', 'canli', 'baslamadi']
    assert maclar[0]['ev'] == 'Galatasaray' and maclar[0]['evGol'] == 2 and maclar[1]['dakika'] == "39'"
    assert maclar[2]['evGol'] is None
    assert sema.sorunlar() == {}


def test_canli_bozuk_yanit_kaydedilir(monkeypatch):
    bozuk = degistir(yukle('canli'), ('leagues', 0, 'matches', 0, 'home', 'name'))
    monkeypatch.setattr(canli, 'json_getir', lambda url: bozuk)
    with pytest.raises(KeyError):
        canli.gunun_maclari('20260814')
    assert 'canli' in sema.sorunlar()


def test_mac_ayrinti_ornekle_calisir(monkeypatch, tmp_path):
    monkeypatch.setattr(mac_ozeti, 'json_getir', lambda url: yukle('mac'))
    a = mac_ozeti.ayrinti(123, tmp_path)
    assert a['durum'] == 'bitti' and a['ev']['ad'] == 'Galatasaray' and a['ev']['skor'] == 2
    assert [o['tur'] for o in a['olaylar']] == ['gol', 'sari', 'degisiklik', 'devre']
    assert a['olaylar'][0]['asist'] == 'Mauro Icardi'
    assert a['istatistik'] and a['kadro']['ev']['dizilis'] == '4-2-3-1'
    assert a['oyuncular']['603669']['kaleci'] and a['oyuncular']['603669']['dk'] == 90
    assert (tmp_path / 'mac_tam' / '123.json').exists() and sema.sorunlar() == {}


def test_hakem_mac_detay_ornekle_calisir(monkeypatch, tmp_path):
    monkeypatch.setattr(hakem, 'json_getir', lambda url: yukle('mac'))
    monkeypatch.setattr(hakem.time, 'sleep', lambda s: None)
    d = hakem.mac_detay(123, tmp_path)
    assert d['hakem']['ad'] == 'Halil Umut Meler' and d['hakem']['mac'] == 12
    assert d['stadyum']['ad'] == 'RAMS Park' and d['stadyum']['konum'] == [41.10339, 28.99106]
    assert sema.sorunlar() == {}


def test_hakem_bozuk_mac_yaniti_kaydedilir(monkeypatch, tmp_path):
    monkeypatch.setattr(hakem, 'json_getir', lambda url: degistir(yukle('mac'), ('header',)))
    monkeypatch.setattr(hakem.time, 'sleep', lambda s: None)
    hakem.mac_detay(123, tmp_path)  # ayrıştırıcı boş sonuç verir (eski davranış) ama sorun artık kayıtlı
    assert 'header.status:d (eksik)' in sema.sorunlar()['mac'][1]


def test_takim_sayfasi_ornekle_calisir(monkeypatch, tmp_path):
    monkeypatch.setattr(takim, 'json_getir', lambda url: yukle('takim'))
    t = takim.takim_sayfasi(8637, tmp_path)
    assert t['ad'] == 'Galatasaray' and t['teknik'] and len(t['kadro']) == 3 and len(t['maclar']) == 2
    assert t['kadro'][0]['ad'] and t['en_iyiler']['puan'] and t['son_ilk11']['dizilis'] == '4-2-3-1'
    assert sema.sorunlar() == {}


def test_oyuncu_sayfasi_ornekle_calisir(monkeypatch, tmp_path):
    monkeypatch.setattr(takim, 'json_getir', lambda url: yukle('oyuncu'))
    assert takim.sozlesme_bitisi(1282008, tmp_path) == '2029-06-30'
    deger, sutlar = takim.deger_ve_sutlar(1282008, tmp_path)
    assert deger == [['2026-06-01', 30000000, 'Roma']] and sutlar[0]['sonuc'] == 'Goal'
    assert takim.oyuncu_son_maclar(1282008, tmp_path)
    assert takim.oyuncu_kariyeri(1282008, tmp_path)
    assert sema.sorunlar() == {}


def test_dogum_cek_ornekle_calisir(monkeypatch):
    monkeypatch.setattr(dogum, 'json_getir', lambda url: yukle('oyuncu'))
    assert dogum._cek(1282008) == '2005-01-12'
    assert sema.sorunlar() == {}


def test_kupa_ayristiricilari_ornekle_calisir():
    j = yukle('kupa')
    assert len(avrupa._maclar(j)) == 1 and avrupa._tablo(j)[0][1][0][1]
    assert avrupa._eleme(j)[0][5]  # eleme ağacında ayaklar
    assert len(milli._maclar(j, 10216)) == 1 and milli.gruplar(j)[0][1][0]['ad']


def test_lig_fikstur_okuyucu_ornekle_calisir(tmp_path):
    yol = tmp_path / 'fm-71-2026.json'
    yol.write_text(json.dumps(yukle('lig')), encoding='utf-8')
    f = lig_maclari._fikstur_oku(yol)
    assert [m['bitti'] for m in f] == [True, False] and f[0]['skor'] == (2, 2)
    assert sema.sorunlar() == {}


def test_istatistik_listesi_okuyucular_ornekle_calisir():
    L = {ad: {str(it['ParticiantId']): it for it in x['TopLists'][0]['StatList']} for ad, x in yukle_liste_hepsi().items()
         if ad in veri.LISTELER}
    v, sv = veri._okuyucular(L)
    i = next(iter(L['mins_played']))
    assert v('mins_played', i) > 0 and len(veri._fotmob_ek(v, sv, i, 0)) == len(veri.FOTMOB_EK)


def test_liste_hepsi_ornegi_sema_ile_uyumlu():
    for ad, x in yukle_liste_hepsi().items():
        tur = 'takim_liste' if ad.endswith('_team') else 'oyuncu_liste'
        assert sema.denetle(tur, x) == [], ad
