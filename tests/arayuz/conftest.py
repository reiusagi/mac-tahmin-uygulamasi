"""Arayüz (NiceGUI) testleri: sayfa(depo) sahte tarayıcıyla (nicegui.testing.User) açılır.

Güvenlik: Depo, d/'nin küçük bir geçici kopyasına bakar (gerçek d/ ve ham/'a yazılmaz); Guncelleyici başlatılmaz
(ağ yok); app.storage.general NiceGUI'nin geçici dizinine yazar (.nicegui/'a dokunulmaz).
pytest-asyncio kurulu olmadığından asenkron testler anyio eklentisiyle (yalnızca asyncio) çalışır.
"""
import asyncio
import json
import logging
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from nicegui import app, ui
from nicegui.storage import Storage
from nicegui.testing.user_simulation import user_simulation

from mac_tahmin.arayuz.depo import Depo
from mac_tahmin.arayuz.sayfa import sayfa
from mac_tahmin.guncelleme import Guncelleyici
from mac_tahmin.sezon import SON_SEZON

KOK = Path(__file__).resolve().parents[2]
VERI = KOK / 'd'

# NiceGUI depolaması (app.storage.general) geçici dizine: gerçek .nicegui/storage-general.json'a yazılmasın.
# Eklenti (user_plugin) yüklü olmadığından NiceGUI'nin pytest_configure'unun yaptığı iş burada, içe aktarmada yapılır.
_DEPO_DIZINI = Path(tempfile.mkdtemp(prefix='mt-nicegui-storage-')).resolve()
Storage.path = _DEPO_DIZINI
app.storage = Storage()

LIG = 'Super_Lig'
DIGER_LIG = 'EPL'
GELECEK_GUN = 5  # sahte "oynanmamış" maçların başlama zamanı: şimdiden bu kadar gün sonra


def pytest_configure(config):
    config.addinivalue_line('markers', 'arayuz: NiceGUI sahte tarayıcı testi (yavaş, birkaç saniye)')


@pytest.fixture(scope='session')
def anyio_backend():
    return 'asyncio'


def _gelecege_tasi(yol):
    """Oynanmamış maçları (u) bugünden sonraya al: veri eskise de 'yaklaşan maç' hep vardır."""
    d = json.loads(yol.read_text(encoding='utf-8'))
    simdi = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0)
    for i, u in enumerate(d['u'][:12]):
        t = simdi + timedelta(days=GELECEK_GUN + i // 4)
        u[0], u[3] = t.date().isoformat(), t.isoformat().replace('+00:00', 'Z')
    d['u'] = d['u'][:12]
    yol.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')


@pytest.fixture(scope='session')
def veri_kopyasi(tmp_path_factory):
    """d/'den birkaç küçük dosyanın geçici kopyası: (veri klasörü, ham klasörü)."""
    kok = tmp_path_factory.mktemp('arayuz')
    d, ham = kok / 'd', kok / 'ham'
    d.mkdir()
    ham.mkdir()
    istenen = [f'{LIG}-{y}.json' for y in range(SON_SEZON - 3, SON_SEZON + 1)]
    istenen += [f'{DIGER_LIG}-{y}.json' for y in range(SON_SEZON - 1, SON_SEZON + 1)]
    istenen += ['milli.json', 'karne.json', 'stadyumlar.json']
    eksik = [a for a in istenen if not (VERI / a).exists()]
    if f'{LIG}-{SON_SEZON}.json' in eksik:
        pytest.skip('d/ klasöründe Super_Lig verisi yok')
    for a in istenen:
        if (VERI / a).exists():
            shutil.copy2(VERI / a, d / a)
    _gelecege_tasi(d / f'{LIG}-{SON_SEZON}.json')
    return d, ham


@pytest.fixture
def depo(veri_kopyasi):
    d, ham = veri_kopyasi
    # Guncelleyici.baslat() çağrılmaz: arka plan iş parçacığı ve ağ yok
    return Depo(d, Guncelleyici(d, ham, 60, 6, lambda *a, **k: None))


@pytest.fixture
async def user(anyio_backend, caplog, depo):
    """'/' adresinde sayfa(depo) olan sahte tarayıcı. Test sırasında loglanan her ERROR testi başarısız kılar."""
    caplog.set_level(logging.ERROR)
    async with user_simulation(root=lambda: sayfa(depo)) as kullanici:
        yield kullanici
        await asyncio.sleep(0)
        hatalar = [f'{r.name}: {r.getMessage()}\n{r.exc_text or ""}' for r in caplog.get_records('call') if r.levelname == 'ERROR']
        if hatalar:
            pytest.fail('Beklenmeyen ERROR kayıtları:\n' + '\n---\n'.join(hatalar), pytrace=False)


ILK_YUKLEME = 400  # should_see yeniden deneme sayısı (x0.1 sn)


@pytest.fixture
async def acik(user):
    """Sayfa açık ve Super_Lig / son sezon verisi yüklenmiş sahte tarayıcı."""
    await user.open('/')
    await user.should_see('sezon sürüyor', retries=ILK_YUKLEME)
    return user


# ---------------------------------------------------------------- yardımcılar (testlerde `from .conftest import ...` yerine fixture)
import re  # noqa: E402


class Yardimci:
    """Sahte tarayıcı üstünde küçük gözlem ve bekleme işlevleri."""

    def __init__(self, user):
        self.user = user

    def ogeler(self, tur):
        return [e for e in self.user.client.elements.values() if isinstance(e, tur)]

    def secim(self, etiket):
        """Etiketine göre ui.select (ör. 'Lig', 'Sezon')."""
        return next(e for e in self.ogeler(ui.select) if e._props.get('label') == etiket)

    def panel(self, sekme_id):
        return next(e for e in self.ogeler(ui.tab_panel) if e._props.get('name') == sekme_id)

    def metin(self, kok):
        """Bir öğenin ve altındakilerin görünen metni (HTML etiketleri atılmış)."""
        parcalar = []
        for e in [kok, *kok.descendants()]:
            for ad in ('text', 'content'):
                v = getattr(e, ad, None)
                if isinstance(v, str) and v:
                    parcalar.append(re.sub(r'<[^>]+>', ' ', v))
        return ' '.join(parcalar)

    def panel_metni(self, sekme_id):
        return self.metin(self.panel(sekme_id))

    def alt_baslik(self):
        return next((e.text for e in self.ogeler(ui.label) if re.search(r'\(.+\) · \d{4}/\d{2}', e.text or '')), '')

    async def bekle(self, kosul, sn=30, ne='koşul'):
        """kosul() doğru olana kadar bekler (asenkron arka plan işleri için); olmazsa AssertionError."""
        son = asyncio.get_running_loop().time() + sn
        while asyncio.get_running_loop().time() < son:
            deger = kosul()
            if deger:
                return deger
            await asyncio.sleep(0.1)
        raise AssertionError(f'{sn} sn içinde gerçekleşmedi: {ne}')

    async def sekme_ac(self, sekme_id, ad):
        self.user.find(ad).click()
        await self.bekle(lambda: self.ogeler(ui.tabs)[0].value == sekme_id, 5, f'{ad} sekmesi açılsın')


@pytest.fixture
def yardimci(acik):
    return Yardimci(acik)
