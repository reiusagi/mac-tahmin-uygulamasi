"""Maç öncesi tahmin hatırlatması (arayuz/bildirim.py): kime, ne zaman hatırlatılır; tekrar bildirilmez."""
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip('nicegui')

from mac_tahmin.arayuz import bildirim  # noqa: E402
from mac_tahmin.arayuz.bildirim import hatirlatilacaklar, hatirlatma_metni, tahmin_kimlikleri  # noqa: E402

SIMDI = datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc)


def mac(id_, saat_sonra, ev='Galatasaray', dep='Fenerbahçe', ev_id=1, dep_id=2, durum='baslamadi'):
    bas = (SIMDI + timedelta(hours=saat_sonra)).isoformat().replace('+00:00', 'Z')
    return {'id': id_, 'lig': 'Super_Lig', 'ev': ev, 'dep': dep, 'evId': ev_id, 'depId': dep_id, 'baslangic': bas,
            'durum': durum}


def idler(sonuc):
    return [m['id'] for m in sonuc]


def test_takip_edilen_takimin_yaklasan_maci_hatirlatilir():
    assert idler(hatirlatilacaklar([mac('a', 2.5)], {'1'}, [], SIMDI, 3)) == ['a']


def test_deplasman_takimi_takipteyse_de_hatirlatilir():
    assert idler(hatirlatilacaklar([mac('a', 2)], {'2'}, [], SIMDI, 3)) == ['a']


def test_id_sayi_ya_da_yazi_olabilir():
    assert idler(hatirlatilacaklar([mac('a', 2)], {1}, [], SIMDI, 3)) == ['a']


def test_takip_edilmeyen_takim_hatirlatilmaz():
    assert hatirlatilacaklar([mac('a', 2)], {'9'}, [], SIMDI, 3) == []
    assert hatirlatilacaklar([mac('a', 2)], set(), [], SIMDI, 3) == []


def test_pencere_disindaki_mac_hatirlatilmaz():
    assert hatirlatilacaklar([mac('a', 3.5)], {'1'}, [], SIMDI, 3) == []
    assert idler(hatirlatilacaklar([mac('a', 3)], {'1'}, [], SIMDI, 3)) == ['a']  # sınır dahil
    assert idler(hatirlatilacaklar([mac('a', 3.5)], {'1'}, [], SIMDI, 4)) == ['a']  # saat ayarı


def test_baslamis_ya_da_baslama_aninda_mac_hatirlatilmaz():
    assert hatirlatilacaklar([mac('a', -0.5)], {'1'}, [], SIMDI, 3) == []
    assert hatirlatilacaklar([mac('a', 0)], {'1'}, [], SIMDI, 3) == []
    assert hatirlatilacaklar([mac('a', 1, durum='canli')], {'1'}, [], SIMDI, 3) == []
    assert hatirlatilacaklar([mac('a', 1, durum='iptal')], {'1'}, [], SIMDI, 3) == []


@pytest.mark.parametrize('saat', [0, -1, None])
def test_saat_sifir_ya_da_bos_ise_kapali(saat):
    assert hatirlatilacaklar([mac('a', 1)], {'1'}, [], SIMDI, saat) == []


@pytest.mark.parametrize('baslangic', [None, '', 'bozuk', 12])
def test_baslangic_bozuksa_atlanir(baslangic):
    m = {**mac('a', 1), 'baslangic': baslangic}
    assert hatirlatilacaklar([m, mac('b', 1)], {'1'}, [], SIMDI, 3) == [mac('b', 1)]


def test_tahmin_girilmisse_hatirlatilmaz():
    m = mac('a', 2)
    tahmin = {'evId': '1', 'depId': '2', 'baslama': m['baslangic']}
    assert hatirlatilacaklar([m], {'1'}, [tahmin], SIMDI, 3) == []


def test_ayni_ciftin_baska_tarihli_tahmini_sayilmaz():
    # aynı çift sezonda birkaç kez oynar: haftalar önceki maçın tahmini bugünkünü örtmez
    eski = {'evId': '1', 'depId': '2', 'baslama': (SIMDI - timedelta(days=60)).isoformat()}
    assert idler(hatirlatilacaklar([mac('a', 2)], {'1'}, [eski], SIMDI, 3)) == ['a']


def test_ters_fiksturun_tahmini_sayilmaz():
    ters = {'evId': '2', 'depId': '1', 'baslama': mac('a', 2)['baslangic']}
    assert idler(hatirlatilacaklar([mac('a', 2)], {'1'}, [ters], SIMDI, 3)) == ['a']


def test_tahminin_saati_kaymissa_bile_ayni_gun_eslesir():
    tahmin = {'evId': '1', 'depId': '2', 'baslama': (SIMDI + timedelta(hours=14)).isoformat()}
    assert hatirlatilacaklar([mac('a', 2)], {'1'}, [tahmin], SIMDI, 3) == []


def test_baslamasi_bilinmeyen_tahmin_tarihten_eslesir():
    tahmin = {'evId': '1', 'depId': '2', 'baslama': None, 'tarih': '2026-03-01'}
    assert hatirlatilacaklar([mac('a', 2)], {'1'}, [tahmin], SIMDI, 3) == []


def test_saat_dilimli_baslangic_dogru_karsilastirilir():
    tr = timezone(timedelta(hours=3))
    m = {**mac('a', 1), 'baslangic': (SIMDI + timedelta(hours=1)).astimezone(tr).isoformat()}
    assert idler(hatirlatilacaklar([m], {'1'}, [], SIMDI.astimezone(tr), 3)) == ['a']


def test_bos_girdiler():
    assert hatirlatilacaklar([], {'1'}, [], SIMDI, 3) == []
    assert hatirlatilacaklar(None, {'1'}, None, SIMDI, 3) == []


def test_girdiler_degismez():
    maclar, tahminler = [mac('a', 2)], [{'evId': '1', 'depId': '2', 'baslama': '2020-01-01T00:00:00Z'}]
    once = (list(maclar), list(tahminler))
    hatirlatilacaklar(maclar, {'1'}, tahminler, SIMDI, 3)
    assert (maclar, tahminler) == once


def test_metin_saat_yerel_ve_tahmin_uyarisi():
    m = mac('a', 6.5)  # 21:30 UTC
    yerel = datetime.fromisoformat(m['baslangic'].replace('Z', '+00:00')).astimezone()
    baslik, metin = hatirlatma_metni(m)
    assert metin == f"Galatasaray – Fenerbahçe {yerel:%H:%M}'da başlıyor. Tahminini girmedin."
    assert 'ahmin' in baslik


def test_tahmin_kimlikleri_adlari_idye_cevirir():
    ligler = {'Super_Lig': {'Galatasaray': 1, 'Fenerbahçe': 2}}
    kayitlar = {'k1': {'lig': 'Super_Lig', 'tarih': '2026-03-01', 'ev': 'Galatasaray', 'dep': 'Fenerbahçe', 'baslama': 'X'},
                'k2': {'lig': 'Super_Lig', 'tarih': '2026-03-01', 'ev': 'Bilinmeyen', 'dep': 'Fenerbahçe', 'baslama': None},
                'k3': {'lig': 'Yok_Lig', 'tarih': '2026-03-01', 'ev': 'Galatasaray', 'dep': 'Fenerbahçe', 'baslama': None}}
    assert tahmin_kimlikleri(kayitlar, ligler) == [
        {'evId': '1', 'depId': '2', 'baslama': 'X', 'tarih': '2026-03-01'}]


# ---------------------------------------------------------------- gönderim (tekrarsız)

class _Depo:
    def stadyumlar(self):
        return {'ligler': {'Super_Lig': {'Galatasaray': 1, 'Fenerbahçe': 2}}}


@pytest.fixture
def ortam(monkeypatch):
    depo = {}
    gidenler = []
    monkeypatch.setattr(bildirim, 'DEPO', _Depo())
    monkeypatch.setattr(bildirim, '_depo', lambda: depo)
    monkeypatch.setattr(bildirim, 'gonder', lambda b, t, takim=None: gidenler.append((b, t, takim)))
    monkeypatch.setattr(bildirim, '_simdi', lambda: SIMDI)
    return depo, gidenler


def test_kontrol_bir_kez_gonderir_ve_kaydeder(ortam):
    depo, giden = ortam
    canli = {'maclar': [], 'yakinda': [mac('a', 2)]}
    bildirim.hatirlatma_kontrol(canli, {'1'})
    bildirim.hatirlatma_kontrol(canli, {'1'})  # bir sonraki dakikalık yenileme
    assert len(giden) == 1 and giden[0][2] == 1 and 'Tahminini girmedin' in giden[0][1]
    assert depo['hatirlatilan'] == ['a']


def test_kontrol_gonderilmisi_depodan_bilir(ortam):
    depo, giden = ortam
    depo['hatirlatilan'] = ['a']  # uygulama yeniden başladı
    bildirim.hatirlatma_kontrol({'maclar': [], 'yakinda': [mac('a', 2)]}, {'1'})
    assert giden == []


def test_kontrol_ligi_oyunda_olmayan_maci_atlar(ortam):
    depo, giden = ortam
    m = {**mac('a', 2), 'lig': 'kupa-x'}
    bildirim.hatirlatma_kontrol({'maclar': [m], 'yakinda': []}, {'1'})
    assert giden == []


def test_kontrol_tahmin_varsa_gondermez(ortam):
    depo, giden = ortam
    depo['tahmin_oyunu'] = {'k': {'lig': 'Super_Lig', 'tarih': '2026-03-01', 'ev': 'Galatasaray', 'dep': 'Fenerbahçe',
                               'baslama': mac('a', 2)['baslangic']}}
    bildirim.hatirlatma_kontrol({'maclar': [], 'yakinda': [mac('a', 2)]}, {'1'})
    assert giden == []


def test_kontrol_saat_ayari_ve_eski_kayitlar_temizlenir(ortam):
    depo, giden = ortam
    depo['hatirlatma_saat'] = 1
    depo['hatirlatilan'] = [str(i) for i in range(500)]
    bildirim.hatirlatma_kontrol({'maclar': [], 'yakinda': [mac('a', 2), mac('b', 0.5)]}, {'1'})
    assert [g[1] for g in giden] and len(giden) == 1  # yalnızca 1 saat içindeki
    assert len(depo['hatirlatilan']) <= bildirim.HATIRLATMA_KAYIT and depo['hatirlatilan'][-1] == 'b'
