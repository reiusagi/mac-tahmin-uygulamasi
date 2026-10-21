"""tahmin_kadro.kadro_topla: takım sayfası alınamayınca (None) sezon verisine düşer, çökmez."""
import asyncio
from types import SimpleNamespace

from mac_tahmin.arayuz import tahmin_kadro


def test_takim_sayfasi_none_donerse_sezon_verisine_duser(monkeypatch):
    async def io_bound(f, *a, **k):
        return f(*a, **k)
    monkeypatch.setattr(tahmin_kadro.run, 'io_bound', io_bound)
    monkeypatch.setattr(tahmin_kadro.takim_veri, 'takim_sayfasi', lambda tid, ham: None)
    depo = SimpleNamespace(takim_kimligi=lambda lig, ad: 7, g=SimpleNamespace(ham='ham'))
    S = SimpleNamespace(lig='Super_Lig', T=['A', 'B'])

    kadrolar, etkiler, notlar, sayfalar = asyncio.run(tahmin_kadro.kadro_topla(depo, S, 0, 1, None))

    assert kadrolar == {0: None, 1: None}
    assert etkiler == [(1.0, []), (1.0, [])]
    assert notlar[0] == 'Güncel kadro alınamadı; sezon verisine göre.'
    assert sayfalar == {}
