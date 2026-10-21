"""Modeller sekmesinin disk önbelleği: aynı veri ve model kodunda eğitim tekrarlanmaz, veri değişince yeniden hesaplanır."""
import json
import os

from yardimci import cift_devre, ham_sezon

from mac_tahmin.arayuz import model_sekme
from mac_tahmin.sezon import Sezon

TAKIMLAR = [f'T{i}' for i in range(12)]  # çift devre: 132 maç (model karşılaştırması için en az 120)


def _veri(klasor, kayma=0):
    raw = ham_sezon(TAKIMLAR, cift_devre(TAKIMLAR, lambda h, a, t: ((int(h[1:]) * 7 + int(a[1:]) + kayma) % 4,
                                                                     (int(a[1:]) * 3 + int(h[1:])) % 3)))
    (klasor / 'EPL-2026.json').write_text(json.dumps(raw), encoding='utf-8')
    return raw


def _kur(klasor):
    return Sezon(json.loads((klasor / 'EPL-2026.json').read_text(encoding='utf-8')), 'EPL', 2026)


def _dizinler(tmp_path):
    d, ham = tmp_path / 'd', tmp_path / 'ham'
    d.mkdir()
    return d, ham


def test_ilk_seferde_hesaplar_sonra_onbellekten_okur(tmp_path):
    d, ham = _dizinler(tmp_path)
    _veri(d)
    ev, onb = model_sekme.degerlendir_onbellekli(_kur(d), d, ham)
    assert not onb and ev['n_test'] > 0
    assert len(list((ham / model_sekme.ONBELLEK_KLASOR).glob('*.json'))) == 1
    S2 = _kur(d)
    ev2, onb2 = model_sekme.degerlendir_onbellekli(S2, d, ham)
    assert onb2 and S2._ev is None  # yeniden eğitilmedi
    assert ev2['sonuclar'] == ev['sonuclar'] and ev2['onem'] == ev['onem']
    assert [(t['ev'], t['dep'], t['sonuc'], t['p']) for t in ev2['test']] == \
        [(t['ev'], t['dep'], t['sonuc'], t['p']) for t in ev['test']]
    m, m2 = ev['test'][0]['mac'], ev2['test'][0]['mac']
    assert (m2.d, m2.hg, m2.ag) == (m.d, m.hg, m.ag)


def test_veri_dosyasi_degisince_yeniden_hesaplar(tmp_path):
    d, ham = _dizinler(tmp_path)
    _veri(d)
    model_sekme.degerlendir_onbellekli(_kur(d), d, ham)
    _veri(d, kayma=1)
    yol = d / 'EPL-2026.json'
    st = yol.stat()
    os.utime(yol, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    _, onb = model_sekme.degerlendir_onbellekli(_kur(d), d, ham)
    assert not onb


def test_model_surumu_degisince_yeniden_hesaplar(tmp_path):
    d, ham = _dizinler(tmp_path)
    _veri(d)
    model_sekme.degerlendir_onbellekli(_kur(d), d, ham, surum='a')
    assert model_sekme.degerlendir_onbellekli(_kur(d), d, ham, surum='a')[1]
    assert not model_sekme.degerlendir_onbellekli(_kur(d), d, ham, surum='b')[1]


def test_bozuk_onbellek_yok_sayilir(tmp_path):
    d, ham = _dizinler(tmp_path)
    _veri(d)
    model_sekme.degerlendir_onbellekli(_kur(d), d, ham)
    for f in (ham / model_sekme.ONBELLEK_KLASOR).glob('*.json'):
        f.write_text('{bozuk', encoding='utf-8')
    ev, onb = model_sekme.degerlendir_onbellekli(_kur(d), d, ham)
    assert not onb and ev['n_test'] > 0


def test_az_macta_none_ve_dosya_yazilmaz(tmp_path):
    d, ham = _dizinler(tmp_path)
    raw = ham_sezon(TAKIMLAR[:4], cift_devre(TAKIMLAR[:4], lambda h, a, t: (1, 0)))
    (d / 'EPL-2026.json').write_text(json.dumps(raw), encoding='utf-8')
    assert model_sekme.degerlendir_onbellekli(_kur(d), d, ham) == (None, False)
    assert not (ham / model_sekme.ONBELLEK_KLASOR).exists()


def test_surum_model_kodundan_turer():
    s = model_sekme.model_surumu()
    assert isinstance(s, str) and len(s) >= 8 and s == model_sekme.model_surumu()
