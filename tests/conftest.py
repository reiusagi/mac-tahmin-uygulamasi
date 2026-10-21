"""Ortak test ayarları. Testler ağa çıkmaz; d/ ve ham/ klasörlerine yazmaz."""
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
VERI = KOK / 'd'


@pytest.fixture(autouse=True)
def _ag_yok(monkeypatch):
    """Bir test yanlışlıkla ağa çıkmaya kalkarsa hemen başarısız olsun."""
    import urllib.request

    def engel(*a, **k):
        raise RuntimeError('testlerde ağ erişimi yok')
    monkeypatch.setattr(urllib.request, 'urlopen', engel)
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', engel)  # veri.ac ve her açıcı buradan geçer
