"""Seçiciler, arama, tahmin oyunu ve takım kartı: kullanıcı etkileşimleri."""
import pytest
from nicegui import app, ui
from nicegui.testing.user_interaction import UserInteraction

pytestmark = [pytest.mark.anyio, pytest.mark.arayuz]


async def test_sezon_degisince_alt_baslik_yenilenir(yardimci):
    onceki = yardimci.alt_baslik()
    assert '2026/27' in onceki and 'sezon sürüyor' in onceki
    yardimci.secim('Sezon').set_value(2025)
    await yardimci.bekle(lambda: '2025/26' in yardimci.alt_baslik(), 30, 'alt başlık 2025/26')
    assert 'sezon sürüyor' not in yardimci.alt_baslik()
    assert app.storage.general['son']['yil'] == 2025  # seçim hatırlanır


async def test_lig_degisince_alt_baslik_ve_tablo_yenilenir(yardimci):
    yardimci.secim('Lig').set_value('EPL')
    await yardimci.bekle(lambda: 'Premier League' in yardimci.alt_baslik(), 30, 'alt başlık Premier League')
    await yardimci.sekme_ac('tablo', 'Puan durumu')
    await yardimci.bekle(lambda: 'Arsenal' in yardimci.panel_metni('tablo'), 30, 'EPL puan tablosu')
    assert 'Galatasaray' not in yardimci.panel_metni('tablo')
    assert app.storage.general['son']['lig'] == 'EPL'


async def test_arama_kutusuna_takim_adi_yazinca_acilir_listede_gorunur(acik, yardimci):
    acik.find(kind=ui.input).type('Galatasaray')
    await yardimci.bekle(lambda: any('Galatasaray' in yardimci.metin(i) for i in yardimci.ogeler(ui.item)), 30,
                         'arama sonucu')
    await acik.should_see('Takım · ')


async def test_arama_sonucuna_tiklayinca_takim_karti_acilir(acik, yardimci):
    acik.find(kind=ui.input).type('Galatasaray')
    await yardimci.bekle(lambda: any('Galatasaray' in yardimci.metin(i) for i in yardimci.ogeler(ui.item)), 30,
                         'arama sonucu')
    oge = next(i for i in yardimci.ogeler(ui.item) if 'Galatasaray' in yardimci.metin(i))
    UserInteraction(acik, {oge}, None).click()  # find() yalnızca öğenin kendi metnini süzer; Item'ın metni alt öğelerinde
    # Ağ kapalı (conftest): kart açılır, takım sayfası indirilemeyince hata metnini gösterir (çökmez).
    await yardimci.bekle(lambda: any(d.value for d in yardimci.ogeler(ui.dialog)), 10, 'takım kartı penceresi açılsın')
    await yardimci.bekle(lambda: any(d.value and 'Takım bilgisi' in yardimci.metin(d) for d in yardimci.ogeler(ui.dialog)),
                         30, 'takım kartı durum metni')
    acik_dialog = next(d for d in yardimci.ogeler(ui.dialog) if d.value)
    assert 'Takım bilgisi alınamadı' in yardimci.metin(acik_dialog)


async def test_tahmin_oyununda_skor_kaydedilir(acik, yardimci):
    assert not app.storage.general.get('tahmin_oyunu')
    await yardimci.sekme_ac('oyun', 'Tahmin oyunu')
    await yardimci.bekle(lambda: 'Kaydet' in yardimci.panel_metni('oyun'), 30, 'yaklaşan maç listesi')
    sayilar = [n for n in yardimci.panel('oyun').descendants() if isinstance(n, ui.number)]
    assert len(sayilar) >= 2
    sayilar[0].set_value(2)
    sayilar[1].set_value(1)
    kaydet = next(b for b in yardimci.panel('oyun').descendants() if isinstance(b, ui.button) and b.text == 'Kaydet')
    acik.find(kind=ui.button, content='Kaydet').click()
    kayitlar = await yardimci.bekle(lambda: app.storage.general.get('tahmin_oyunu'), 10, 'tahmin kaydı')
    assert kaydet  # düğme vardı
    assert len(kayitlar) == 1
    kayit = next(iter(kayitlar.values()))
    assert kayit['sen'] == [2, 1]
    assert kayit['lig'] == 'Super_Lig' and kayit['yil'] == 2026
    assert kayit['sonuc'] is None and len(kayit['model']) == 2
    await acik.should_see('Güncelle')  # liste yeniden çizildi
