"""Görünüm menüsü: klasik / modern stil seçimi (body'deki stil-modern sınıfı ve kalıcı ayar)."""
import pytest
from nicegui import app, ui
from nicegui.elements.query import QueryElement

from mac_tahmin.arayuz.ortak import STILLER
from mac_tahmin.arayuz.stil_modern import CSS_MODERN

pytestmark = [pytest.mark.anyio, pytest.mark.arayuz]


def _body_siniflari(yardimci):
    return next(e for e in yardimci.ogeler(QueryElement) if e.props['selector'] == 'body').props['classes']


def _stil_dugmesi(yardimci):
    return next(t for t in yardimci.ogeler(ui.toggle) if t.options == list(STILLER) or set(t.options) == set(STILLER))


async def test_varsayilan_stil_modern(yardimci):
    assert 'stil-modern' in _body_siniflari(yardimci)
    assert _stil_dugmesi(yardimci).value == 'modern'
    assert 'stil' not in (app.storage.general.get('gorunum') or {})


async def test_klasik_secilince_body_sinifi_ve_ayar(yardimci):
    dugme = _stil_dugmesi(yardimci)
    dugme.set_value('klasik')
    await yardimci.bekle(lambda: 'stil-modern' not in _body_siniflari(yardimci), 5, 'stil-modern kalksın')
    assert app.storage.general['gorunum']['stil'] == 'klasik'
    assert 'palet-saha' in _body_siniflari(yardimci)  # palet sınıfı korunur
    dugme.set_value('modern')
    await yardimci.bekle(lambda: 'stil-modern' in _body_siniflari(yardimci), 5, 'body.stil-modern')
    assert app.storage.general['gorunum']['stil'] == 'modern'


async def test_kayitli_klasik_stil_acilista_uygulanir(user):
    app.storage.general['gorunum'] = {'stil': 'klasik'}
    try:
        await user.open('/')
        siniflar = next(e for e in user.client.elements.values()
                        if isinstance(e, QueryElement) and e.props['selector'] == 'body').props['classes']
        assert 'stil-modern' not in siniflar
    finally:
        app.storage.general.pop('gorunum', None)


async def test_kayitli_modern_stil_acilista_uygulanir(user):
    app.storage.general['gorunum'] = {'palet': 'gece', 'tema': 'koyu', 'stil': 'modern'}
    try:
        await user.open('/')
        siniflar = next(e for e in user.client.elements.values()
                        if isinstance(e, QueryElement) and e.props['selector'] == 'body').props['classes']
        assert 'stil-modern' in siniflar and 'palet-gece' in siniflar
    finally:
        app.storage.general.pop('gorunum', None)


def test_modern_css_yalnizca_stil_modern_altinda():
    """Modern kuralları klasik görünümü değiştirmesin: her seçici body.stil-modern ile başlar (gizli eklenen öğeler hariç)."""
    import re
    govde = re.sub(r'/\*.*?\*/', '', CSS_MODERN, flags=re.S)
    serbest = {'.md-ust', '.md-lejant'}
    for blok in re.findall(r'([^{}]+)\{[^{}]*\}', govde):
        for secici in blok.split(','):
            secici = secici.strip()
            if not secici or secici.startswith(('@', 'from', 'to')) or secici in serbest:
                continue
            assert 'stil-modern' in secici, secici
