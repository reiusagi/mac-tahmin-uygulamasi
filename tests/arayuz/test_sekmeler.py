"""Veri yüklendikten sonra sekmelerin içeriği ve sekme geçişleri (hata logu = başarısızlık; bkz. conftest.user)."""
import pytest

from mac_tahmin.arayuz.sayfa import SEKMELER

pytestmark = [pytest.mark.anyio, pytest.mark.arayuz]

TAKIMLAR = ['Galatasaray', 'Fenerbahçe', 'Beşiktaş', 'Trabzonspor']


async def test_ilk_sekme_mac_tahmini_olasiliklari_yuzde_gosterir(yardimci):
    await yardimci.bekle(lambda: '%' in yardimci.panel_metni('tahmin'), 30, 'olasılıklar')
    metin = yardimci.panel_metni('tahmin')
    assert 'beraberlik %' in metin
    assert 'Sonraki hafta' in metin


async def test_puan_durumu_lig_takimlarini_listeler(yardimci):
    await yardimci.sekme_ac('tablo', 'Puan durumu')
    await yardimci.bekle(lambda: 'Galatasaray' in yardimci.panel_metni('tablo'), 30, 'puan tablosu')
    metin = yardimci.panel_metni('tablo')
    for takim in TAKIMLAR:
        assert takim in metin
    assert '69 maçın sonucundan hesaplandı' in metin


@pytest.mark.parametrize('sekme_id, ad, beklenen', [
    ('oyuncular', 'Oyuncular', 'Oyuncu rolleri'),
    ('karne', 'Karne', 'Model ne kadar doğru?'),
    ('oyun', 'Tahmin oyunu', 'Yaklaşan maçlar'),
    ('milli', 'Milli', 'milli maç'),
])
async def test_veri_sekmeleri_hatasiz_cizilir(yardimci, sekme_id, ad, beklenen):
    await yardimci.sekme_ac(sekme_id, ad)
    await yardimci.bekle(lambda: beklenen in yardimci.panel_metni(sekme_id), 30, f'{ad}: "{beklenen}"')


async def test_her_sekmeye_gecmek_hata_vermez(yardimci):
    """15 sekmenin hepsi sırayla açılır; asenkron yenilemelerin bitmesi beklenir. Hata logu conftest'te testi düşürür."""
    import asyncio
    for m in SEKMELER:
        await yardimci.sekme_ac(m.ID, m.AD)
        await yardimci.bekle(lambda m=m: yardimci.panel_metni(m.ID).strip(), 30, f'{m.AD} içeriği')
    await asyncio.sleep(3)  # tembel sekmelerin (modeller, karne…) arka plan işleri bitsin
    assert yardimci.ogeler(__import__('nicegui').ui.tabs)[0].value == SEKMELER[-1].ID
