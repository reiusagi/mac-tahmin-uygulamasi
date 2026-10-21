"""Temizlik turunda birleştirilen yardımcılar: FotMob adresleri, logo adresleri, para/yüzde biçimleri."""
from mac_tahmin import bicim, logo
from mac_tahmin.veri import fotmob_url

API = 'https://www.fotmob.com/api/data'


# ------------------------------------------------------------ FotMob adresleri (eski elle yazılmış dizgelerle aynı)

def test_fotmob_url_lig_sezon_eski_bicimlerle_ayni():
    lid, yil, sezon = 47, 2025, '2025/2026'
    assert fotmob_url('leagues', id=lid, season=f'{yil}/{yil + 1}') == f'{API}/leagues?id=47&season=2025%2F2026'
    assert fotmob_url('leagues', id=lid, season=sezon) == f'{API}/leagues?id={lid}&season={sezon.replace("/", "%2F")}'
    assert fotmob_url('leagues', id=lid, season='2025') == f'{API}/leagues?id=47&season=2025'
    assert fotmob_url('leagues', id=9806, season=None) == f'{API}/leagues?id=9806'


def test_fotmob_url_diger_yollar():
    assert fotmob_url('leagues', id=71) == f'{API}/leagues?id=71'
    assert fotmob_url('teams', id=8634) == f'{API}/teams?id=8634'
    assert fotmob_url('playerData', id='961995') == f'{API}/playerData?id=961995'
    assert fotmob_url('matchDetails', matchId=4506789) == f'{API}/matchDetails?matchId=4506789'
    assert fotmob_url('matches', date='20261021', timezone='Europe/Istanbul') == f'{API}/matches?date=20261021&timezone=Europe%2FIstanbul'


def test_fotmob_url_ozel_karakterler_kodlanir():
    assert fotmob_url('leagues', id='1&x=2') == f'{API}/leagues?id=1%26x%3D2'


# ------------------------------------------------------------ logo adresleri

def test_logo_adresleri_eski_dizgelerle_ayni():
    kok = 'https://images.fotmob.com/image_resources/logo'
    assert logo.takim_logo_url(8634) == f'{kok}/teamlogo/8634_xsmall.png'
    assert logo.takim_logo_url('8634', 'small') == f'{kok}/teamlogo/8634_small.png'
    assert logo.lig_logo_url(42) == f'{kok}/leaguelogo/42.png'
    assert logo.TAKIM_LOGO.format(1) == f'{kok}/teamlogo/1_xsmall.png'


def test_logo_adresi_gecersiz_kimlikte_bos():
    for kotu in (None, '', '1)"x', '../x', 1.5, True):
        assert logo.takim_logo_url(kotu) == ''
        assert logo.lig_logo_url(kotu) == ''


def test_logo_html():
    assert logo.logo_html('u', 'a', 'w:1;') == '<span class="a" style="w:1;background-image:url(u)"></span>'
    assert logo.logo_html('') == ''
    assert logo.logo_html('', bos='-') == '-'


def test_takim_logo_boyutu():
    from mac_tahmin.arayuz.ortak import takim_logo
    assert '/8695_xsmall.png' in takim_logo(8695)  # küçük satır logoları (35 px)
    assert '/8695_small.png' in takim_logo(8695, 'small')  # büyük gösterilenler (150 px; 76 px başlıkta keskin)


def test_mac_tahmini_basligi_buyuk_logo_kullanir():
    from mac_tahmin.arayuz import tahmin_metin
    kaynak = open(tahmin_metin.__file__, encoding='utf-8').read()
    ust = kaynak[kaynak.index("ust = (f'<div class=\"md-ust\">"):]
    ust = ust[:ust.index('return')]
    assert ust.count('"small")') == 2


def test_eski_logo_adlari_duruyor():
    from mac_tahmin import avrupa, milli
    assert avrupa.LOGO == milli.LOGO == logo.LIG_LOGO
    assert avrupa.TAKIM_LOGO == logo.TAKIM_LOGO


# ------------------------------------------------------------ biçimler

def test_para_biçimleri():
    assert bicim.para(12_500_000) == '12,5 M€'
    assert bicim.para(800_000) == '800 B€'
    assert bicim.para(0) == '0 B€'
    assert bicim.para(0, '–') == '–' and bicim.para(None, '–') == '–'
    assert bicim.para(800_000, '–', yalniz_m=True) == '0,8 M€'
    assert bicim.para(12_500_000, yalniz_m=True) == '12,5 M€'


def test_fmt_ve_yuzde():
    assert bicim.fmt(1.234) == '1,23' and bicim.fmt(None) == '–' and bicim.fmt(-0.001) == '0,00'
    assert bicim.yuzde(0.456) == '%46'


def test_ortak_eski_adlari_duruyor():
    from mac_tahmin.arayuz import ortak
    assert ortak.fmt is bicim.fmt and ortak.yuzde is bicim.yuzde and ortak.sayi_kimlik is bicim.sayi_kimlik


def test_lig_adi_tek_yerde():
    from mac_tahmin import canli, sezon, takim
    from mac_tahmin.arayuz import scout
    assert canli.LIG_ADI is sezon.LIG_ADI is scout.LIG_ADI
    assert takim.AVRUPA == {42, 73, 10216, 10611, 10613, 10615}
    assert takim.AVRUPA_ADI[10611] == 'Şampiyonlar Ligi Elemeleri' and takim.AVRUPA_ADI[42] == 'Şampiyonlar Ligi'
