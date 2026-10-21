"""milli.py: Elo sıfır toplamlı, mezban ülke ev sahibi avantajı alır, gol modeli."""
import json
import math
import os
import threading
import time

import pytest

from mac_tahmin.milli import EV_AVANTAJI, DosyaOnbellegi, MilliElo, mezban_yonu, sezon_maclari


def kimlik(ad):
    return sum(map(ord, ad))


def mac(i, zaman, ev, dep, hg, ag):
    # derlenmiş satır: id, zaman, ev id, dep id, ev, dep, ev golü, dep golü, grup, tur, başladı mı
    return [str(i), zaman, kimlik(ev), kimlik(dep), ev, dep, hg, ag, 'A', 1, False]


def veri(*turnuvalar):
    return {'turnuvalar': {str(tid): {sezon: {'maclar': ms, 'gruplar': []}} for tid, sezon, ms in turnuvalar}}


def test_elo_sifir_toplamli():
    v = veri((114, '2026', [mac(1, '2026-03-01T18:00:00Z', 'France', 'Spain', 2, 0),
                            mac(2, '2026-03-05T18:00:00Z', 'Spain', 'Italy', 1, 1),
                            mac(3, '2026-03-09T18:00:00Z', 'Italy', 'France', 0, 4)]))
    E = MilliElo(v)
    assert sum(E.R.values()) == pytest.approx(1500 * len(E.R), abs=1e-9)
    assert E.n_mac == 3
    assert E.R[kimlik('France')] > 1500 > E.R[kimlik('Italy')]


def test_ayni_mac_iki_turnuvada_bir_kez_sayilir():
    m = mac(1, '2026-03-01T18:00:00Z', 'France', 'Spain', 2, 0)
    assert MilliElo(veri((114, '2026', [m]), (50, '2024', [m]))).n_mac == 1


def test_oynanmamis_mac_sayilmaz():
    E = MilliElo(veri((114, '2026', [mac(1, '2026-03-01T18:00:00Z', 'France', 'Spain', None, None)])))
    assert E.n_mac == 0 and E.R == {}
    assert (E.a, E.b) == (math.log(1.3), 0.6)


@pytest.mark.parametrize('tid,zaman,ev,dep,beklenen', [
    (77, '2022-11-20T16:00:00Z', 'Qatar', 'Ecuador', 1), (77, '2022-11-25T16:00:00Z', 'Senegal', 'Qatar', -1),
    (77, '2014-06-12T20:00:00Z', 'Brazil', 'Croatia', 1), (77, '2018-06-14T15:00:00Z', 'Saudi Arabia', 'Russia', -1),
    (77, '2022-11-21T13:00:00Z', 'England', 'Iran', 0), (77, '2026-06-13T01:00:00Z', 'USA', 'Paraguay', 1),
    (77, '2026-06-18T01:00:00Z', 'Canada', 'Qatar', 1), (77, '2026-06-20T01:00:00Z', 'USA', 'Mexico', 0),
    (50, '2024-06-14T19:00:00Z', 'Germany', 'Scotland', 1), (50, '2021-06-11T19:00:00Z', 'Turkiye', 'Italy', 0),
    (50, '2016-06-10T19:00:00Z', 'France', 'Romania', 1), (44, '2019-06-14T19:00:00Z', 'Brazil', 'Bolivia', 1),
    (114, '2024-03-01T19:00:00Z', 'Germany', 'France', 0), (77, '', 'Brazil', 'Chile', 0),
    (77, '2022-11-20T16:00:00Z', 'Katar', 'Ekvador', 1)])  # Türkçe adlar da tanınır (mac_sozlugu çevirir)
def test_mezban_yonu(tid, zaman, ev, dep, beklenen):
    assert mezban_yonu(tid, zaman, ev, dep) == beklenen


@pytest.mark.parametrize('tid,sezon,zaman,ev,dep,beklenen', [
    (289, '2021', '2022-01-09T16:00:00Z', 'Cameroon', 'Burkina Faso', 1),  # turnuva yıl başında oynandı, sezon 2021
    (289, '2023', '2024-01-13T20:00:00Z', 'Ivory Coast', 'Guinea-Bissau', 1),
    (289, '2025', '2026-01-04T20:00:00Z', 'Mali', 'Morocco', -1),
    (290, '2023', '2024-01-12T16:00:00Z', 'Qatar', 'Lebanon', 1),
    (289, '2025', '2025-12-21T16:00:00Z', 'Morocco', 'Comoros', 1),
    (289, '2025', '2026-01-04T20:00:00Z', 'Mali', 'Senegal', 0)])
def test_mezban_yonu_sezonla_yil_asan_turnuva(tid, sezon, zaman, ev, dep, beklenen):
    assert mezban_yonu(tid, zaman, ev, dep, sezon) == beklenen
    assert mezban_yonu(tid, zaman, ev, dep) == (beklenen if zaman[:4] == sezon else 0)  # sezonsuz: takvim yılı (eski davranış)


def test_mezban_ocak_maci_elo_ve_sezon_maclarinda():
    kam, bf = 'Cameroon', 'Burkina Faso'
    v = veri((289, '2021', [mac(1, '2022-01-09T16:00:00Z', kam, bf, 0, 0)]))
    assert MilliElo(v).R[kimlik(kam)] < 1500 < MilliElo(v).R[kimlik(bf)]  # mezban +60 ile beraberlik: Elo kaybeder
    assert sezon_maclari(v, 289, '2021')[0]['sezon'] == '2021'


def test_mezban_ev_sahibi_avantaji_elo_ve_gecmiste():
    kat, ekv = 'Qatar', 'Ecuador'
    E = MilliElo(veri((77, '2022', [mac(1, '2022-11-20T16:00:00Z', kat, ekv, 0, 0)])))
    # eşit güçte iki takım, 0-0: mezban +60 avantajla beklenenin altında kaldığından Elo kaybeder (tarafsız olsa değişmezdi)
    assert E.R[kimlik(kat)] < 1500 < E.R[kimlik(ekv)]
    beklenen = 1 / (10 ** (-EV_AVANTAJI / 400) + 1)
    assert E.R[kimlik(kat)] - 1500 == pytest.approx(60 * (0.5 - beklenen))  # Dünya Kupası K = 60
    assert E.gecmis[kimlik(kat)][0]['tarafsiz'] is False


def test_mezban_olmayan_turnuva_maci_tarafsiz():
    E = MilliElo(veri((77, '2022', [mac(1, '2022-11-21T13:00:00Z', 'England', 'Iran', 1, 1)])))
    assert E.R[kimlik('England')] == pytest.approx(1500.0)
    assert E.gecmis[kimlik('England')][0]['tarafsiz'] is True


def test_mezban_deplasman_yazilmissa_avantaj_ona_gider():
    E = MilliElo(veri((77, '2022', [mac(1, '2022-11-25T16:00:00Z', 'Senegal', 'Qatar', 1, 1)])))
    assert E.R[kimlik('Qatar')] < 1500 < E.R[kimlik('Senegal')]


def test_hazirlik_macinda_ev_avantaji_normal():
    E = MilliElo(veri((114, '2026', [mac(1, '2026-03-01T18:00:00Z', 'France', 'Spain', 1, 1)])))
    assert E.R[kimlik('France')] < 1500  # ev sahibi berabere kalınca kaybeder


def test_tahmin_avantaj_parametresi():
    E = MilliElo(veri((114, '2026', [mac(1, '2026-03-01T18:00:00Z', 'France', 'Spain', 1, 0)])))
    f, s = kimlik('France'), kimlik('Spain')
    ev, tarafsiz = E.tahmin(f, s)['p'], E.tahmin(f, s, True)['p']
    assert ev[0] > tarafsiz[0]
    assert E.tahmin(f, s, False, 0)['p'] == tarafsiz
    assert E.tahmin(f, s, True, 1)['p'] == ev
    assert E.tahmin(f, s, False, -1)['p'][0] < tarafsiz[0]
    assert sum(E.tahmin(f, s)['p']) == pytest.approx(1.0)
    assert sum(c for _, _, c in E.tahmin(f, s)['hucreler']) == pytest.approx(1.0)


def test_gol_modeli_guclu_takim_daha_cok_gol():
    maclar = [mac(i, f'2026-03-{i + 1:02d}T18:00:00Z', 'France', f'Takim{i}', 4, 0) for i in range(1, 10)]
    E = MilliElo(veri((114, '2026', maclar)))
    assert E.b > 0
    t = E.tahmin(kimlik('France'), kimlik('Takim1'))
    assert t['lh'] > t['la']


# ---------------------------------------------------------------- DosyaOnbellegi

def _onbellek_dosyasi(tmp_path, icerik):
    yol = tmp_path / 'milli.json'
    yol.write_text(json.dumps(icerik), encoding='utf-8')
    return yol


def test_onbellek_elo_hesabi_oku_cagrilarini_bloklamaz(tmp_path):
    yol = _onbellek_dosyasi(tmp_path, {'a': 1})
    ob = DosyaOnbellegi()
    ob.oku(yol)
    basladi, birak, sonuc = threading.Event(), threading.Event(), []

    def yavas_kur(veri):
        basladi.set()
        assert birak.wait(5)
        return ('elo', veri['a'])
    t = threading.Thread(target=lambda: sonuc.append(ob.elo(yavas_kur)))
    t.start()
    try:
        assert basladi.wait(5)
        okuyan = []
        o = threading.Thread(target=lambda: okuyan.append(ob.oku(yol)))
        o.start()
        o.join(2)  # Elo hesabı sürerken oku beklememeli
        assert not o.is_alive() and okuyan == [{'a': 1}]
    finally:
        birak.set()
        t.join(5)
    assert sonuc == [('elo', 1)] and ob.elo(lambda v: 1 / 0) == ('elo', 1)  # önbelleğe yazıldı, yeniden hesaplanmaz


def test_onbellek_es_zamanli_elo_istekleri_bir_kez_hesaplar(tmp_path):
    ob = DosyaOnbellegi()
    ob.oku(_onbellek_dosyasi(tmp_path, {'a': 1}))
    sayac, birak = [], threading.Event()

    def kur(veri):
        sayac.append(1)
        birak.wait(5)
        return object()
    sonuclar = []
    ts = [threading.Thread(target=lambda: sonuclar.append(ob.elo(kur))) for _ in range(4)]
    for t in ts:
        t.start()
    birak.set()
    for t in ts:
        t.join(5)
    assert len(sayac) == 1 and len(sonuclar) == 4 and all(s is sonuclar[0] for s in sonuclar)


def test_onbellek_hesap_sirasinda_dosya_degisirse_eski_sonuc_saklanmaz(tmp_path):
    yol = _onbellek_dosyasi(tmp_path, {'a': 1})
    ob = DosyaOnbellegi()
    ob.oku(yol)

    def kur(veri):
        if veri['a'] == 1:  # hesap sürerken dosya yenilenir ve biri okur
            yol.write_text(json.dumps({'a': 2}), encoding='utf-8')
            os.utime(yol, (time.time() + 10, time.time() + 10))
            ob.oku(yol)
        return ('elo', veri['a'])
    assert ob.elo(kur) == ('elo', 1)  # çağıranın okuduğu veriye göre
    ob.oku(yol)
    assert ob.elo(kur) == ('elo', 2)  # eski veriden hesaplanan sonuç yeni verinin önbelleğine yazılmadı
