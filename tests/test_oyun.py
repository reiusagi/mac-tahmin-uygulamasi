"""Tahmin oyunu (arayuz/oyun.py): puanlama, oynanan maçla kaydın eşleşmesi ve ertelenen maçın yetim kaydı."""
import pytest

pytest.importorskip('nicegui')

from mac_tahmin.arayuz import oyun  # noqa: E402
from mac_tahmin.arayuz.oyun import KESIN, SONUC, puan, sonuc_esle, yetim_kayitlar  # noqa: E402


# ---------------------------------------------------------------- puan

@pytest.mark.parametrize('tahmin,sonuc,beklenen', [
    ([2, 1], [2, 1], KESIN), ([0, 0], [0, 0], KESIN), ([1, 1], [1, 1], KESIN),
    ([2, 0], [1, 0], SONUC), ([3, 1], [1, 0], SONUC), ([1, 1], [2, 2], SONUC), ([0, 2], [1, 3], SONUC),
    ([2, 0], [0, 2], 0), ([1, 0], [1, 1], 0), ([0, 0], [0, 1], 0), ([2, 2], [3, 1], 0),
    ((2, 1), [2, 1], KESIN), ([2, 1], (1, 0), SONUC)])
def test_puan(tahmin, sonuc, beklenen):
    assert puan(tahmin, sonuc) == beklenen


@pytest.mark.parametrize('tahmin,sonuc', [(None, [1, 0]), ([1, 0], None), (None, None), ([], [1, 0]), ([1, 0], [])])
def test_puan_eksik_veride_none(tahmin, sonuc):
    assert puan(tahmin, sonuc) is None


def test_puan_degerleri():
    assert (KESIN, SONUC) == (3, 1)


# ---------------------------------------------------------------- model_skoru

def test_model_skoru_en_olasi_sonucun_en_olasi_skoru():
    t = {'p': [0.5, 0.3, 0.2], 'hucreler': [(1, 1, 0.20), (1, 0, 0.12), (2, 0, 0.10), (0, 1, 0.08), (0, 0, 0.1)]}
    assert oyun.model_skoru(t) == [1, 0]  # 1-1 en olası skor ama ev kazanır diyen modelin skoru 1-0
    t = {'p': [0.2, 0.5, 0.3], 'hucreler': [(1, 1, 0.20), (0, 0, 0.25), (0, 1, 0.1)]}
    assert oyun.model_skoru(t) == [0, 0]


# ---------------------------------------------------------------- sonuc_esle

def _kayit(tarih, ev='A', dep='B', lig='Premiership', sonuc=None):
    return {'lig': lig, 'yil': 2026, 'tarih': tarih, 'ev': ev, 'dep': dep, 'baslama': tarih + 'T14:00:00+00:00',
            'sen': [1, 0], 'model': [1, 0], 'sonuc': sonuc}


# İskoçya gibi aynı çiftin sezonda dört kez oynadığı lig
OYNANAN = [('2026-08-10', 'A', 'B', 2, 1), ('2026-09-14', 'A', 'B', 0, 0), ('2026-10-19', 'A', 'B', 1, 3),
           ('2026-09-20', 'B', 'A', 4, 4), ('2026-08-10', 'C', 'D', 7, 7)]


def test_ayni_cift_birden_cok_oynadiysa_tarihi_yakin_olan_secilir():
    bek = {'k1': _kayit('2026-10-19')}
    assert sonuc_esle(bek, OYNANAN) == {'k1': ('2026-10-19', 1, 3)}


def test_her_kayit_kendi_macinin_sonucunu_alir():
    bek = {'k1': _kayit('2026-08-10'), 'k2': _kayit('2026-09-14'), 'k3': _kayit('2026-10-19')}
    s = sonuc_esle(bek, OYNANAN)
    assert {k: v[1:] for k, v in s.items()} == {'k1': (2, 1), 'k2': (0, 0), 'k3': (1, 3)}


def test_henuz_oynanmamis_mac_onceki_karsilasmanin_skorunu_almaz():
    # 14 Eylül maçı oynanmadı (ileride 28 Eylül'e ertelenecek); 10 Ağustos'ta oynanan eski maç ona verilmemeli
    bek = {'k2': _kayit('2026-09-14')}
    assert sonuc_esle(bek, [OYNANAN[0]]) == {}


def test_erteleme_toleransi_icinde_eslesir():
    bek = {'k': _kayit('2026-09-14')}
    assert sonuc_esle(bek, [('2026-10-05', 'A', 'B', 3, 2)]) == {'k': ('2026-10-05', 3, 2)}  # 21 gün sonra
    assert sonuc_esle(bek, [('2026-10-06', 'A', 'B', 3, 2)]) == {}  # 22 gün: eşleşmez, bekler


def test_biraz_erken_oynanan_mac_eslesir_ama_bir_hafta_erken_olan_eslesmez():
    bek = {'k': _kayit('2026-09-14')}
    assert sonuc_esle(bek, [('2026-09-12', 'A', 'B', 1, 1)]) == {'k': ('2026-09-12', 1, 1)}
    assert sonuc_esle(bek, [('2026-09-07', 'A', 'B', 1, 1)]) == {}


def test_bir_mac_en_cok_bir_kayda_puan_verir():
    # 14 Eylül maçı 28 Eylül'e ertelendi: eski kayıt (14 Eylül) ve yeni kayıt (28 Eylül) aynı maça uyar; yeni kayıt alır
    oy = [('2026-09-28', 'A', 'B', 2, 0)]
    bek = {'eski': _kayit('2026-09-14'), 'yeni': _kayit('2026-09-28')}
    s = sonuc_esle(bek, oy)
    assert s == {'yeni': ('2026-09-28', 2, 0)}


def test_esit_uzaklikta_belirlenimci():
    oy = [('2026-09-14', 'A', 'B', 1, 0)]
    bek = {'b': _kayit('2026-09-14'), 'a': _kayit('2026-09-14')}
    ilk = sonuc_esle(bek, oy)
    assert len(ilk) == 1
    assert sonuc_esle(dict(reversed(list(bek.items()))), oy) == ilk


def test_ters_fikstur_ve_baska_cift_eslesmez():
    assert sonuc_esle({'k': _kayit('2026-09-20')}, OYNANAN) == {}  # (A, B) 20 Eylül'de oynanmadı; (B, A) oynandı
    assert sonuc_esle({'k': _kayit('2026-08-10', ev='B', dep='A')}, OYNANAN) == {}
    assert sonuc_esle({'k': _kayit('2026-08-10', ev='C', dep='D')}, OYNANAN) == {'k': ('2026-08-10', 7, 7)}


def test_baska_kayda_verilmis_mac_alinmaz():
    bek = {'k': _kayit('2026-10-19')}
    assert sonuc_esle(bek, OYNANAN, alinmis={('2026-10-19', 'A', 'B')}) == {}


def test_en_cok_tahmini_eslestirir():
    """En yakın tarihi açgözlü seçmek ikinci tahmini yetim bırakmasın (Codex bulgusu): k1 1 Ocak'a, k2 4 Ocak'a."""
    bek = {'k1': _kayit('2026-01-03'), 'k2': _kayit('2026-01-06')}
    oy = [('2026-01-04', 'A', 'B', 1, 0), ('2026-01-01', 'A', 'B', 2, 0)]
    assert sonuc_esle(bek, oy) == {'k1': ('2026-01-01', 2, 0), 'k2': ('2026-01-04', 1, 0)}


def test_bos_girdiler():
    assert sonuc_esle({}, OYNANAN) == {}
    assert sonuc_esle({'k': _kayit('2026-10-19')}, []) == {}


def test_eski_bicimli_kayit_yilsiz_da_calisir():
    r = _kayit('2026-10-19')
    del r['yil']
    del r['baslama']
    assert sonuc_esle({'k': r}, OYNANAN) == {'k': ('2026-10-19', 1, 3)}


# ---------------------------------------------------------------- yetim_kayitlar

def _tum(*kayitlar):
    return {f'{r["lig"]}|{r["tarih"]}|{r["ev"]}|{r["dep"]}': r for r in kayitlar}


def test_ertelenen_macin_eski_kaydi_yetimdir():
    eski, yeni = _kayit('2026-09-14'), _kayit('2026-09-28')
    tum = _tum(eski, yeni)
    assert yetim_kayitlar(tum, yeni, kalan=set(), oynanan=[]) == ['Premiership|2026-09-14|A|B']


def test_fikstur_listesinde_hala_olan_kayit_yetim_degildir():
    # iki ayrı karşılaşma da ileride: ikisi de geçerli
    eski, yeni = _kayit('2026-09-14'), _kayit('2026-09-28')
    assert yetim_kayitlar(_tum(eski, yeni), yeni, kalan={('2026-09-14', 'A', 'B'), ('2026-09-28', 'A', 'B')}, oynanan=[]) == []


def test_oynanmis_macin_kaydi_yetim_degildir():
    eski, yeni = _kayit('2026-09-14'), _kayit('2026-09-28')
    assert yetim_kayitlar(_tum(eski, yeni), yeni, kalan=set(), oynanan=[('2026-09-14', 'A', 'B', 1, 0)]) == []


def test_puanlanmis_kayit_yetim_degildir():
    eski, yeni = _kayit('2026-09-14', sonuc=[1, 0]), _kayit('2026-09-28')
    assert yetim_kayitlar(_tum(eski, yeni), yeni, kalan=set(), oynanan=[]) == []


def test_baska_lig_sezon_veya_takim_yetim_sayilmaz():
    yeni = _kayit('2026-09-28')
    digerleri = [_kayit('2026-09-14', lig='Bundesliga'), {**_kayit('2026-09-15'), 'yil': 2025},
                 _kayit('2026-09-16', ev='C'), _kayit('2026-09-17', dep='C')]
    assert yetim_kayitlar(_tum(yeni, *digerleri), yeni, kalan=set(), oynanan=[]) == []


def test_cok_uzak_tarihli_kayit_yetim_sayilmaz():
    # 22+ gün sonraki maç büyük olasılıkla bir sonraki karşılaşmadır; sonucu henüz yazılmamış maçın kaydı korunur
    eski, yeni = _kayit('2026-09-14'), _kayit('2026-10-20')
    assert yetim_kayitlar(_tum(eski, yeni), yeni, kalan=set(), oynanan=[]) == []


def test_kendisi_ve_ayni_tarihli_kayit_silinmez():
    yeni = _kayit('2026-09-28')
    assert yetim_kayitlar(_tum(yeni), yeni, kalan=set(), oynanan=[]) == []
