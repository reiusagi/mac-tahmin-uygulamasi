"""Sayfa kurulumu, başlık ögeleri ve sekmeler."""
import pytest
from nicegui import ui

from mac_tahmin.arayuz.sayfa import SEKMELER

pytestmark = [pytest.mark.anyio, pytest.mark.arayuz]


async def test_baslik_ve_alt_bilgi_ogeleri(acik):
    await acik.should_see('Lig')
    await acik.should_see('Sezon')
    await acik.should_see(kind=ui.input)
    await acik.should_see('Şimdi güncelle')
    await acik.should_see('Veri kaynağı')


async def test_15_sekmenin_hepsi_gorunur(acik):
    assert len(SEKMELER) == 15
    for m in SEKMELER:
        await acik.should_see(m.AD)
