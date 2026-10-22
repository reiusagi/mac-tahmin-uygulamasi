"""masaustu_paketle: ham/ önbelleği olmayan ortamda (GitHub Actions) başlangıç önbelleği boş da olsa kurulur."""
import masaustu_paketle


def test_ham_klasoru_yokken_baslangic_onbellegi_kurulur(tmp_path, monkeypatch):
    monkeypatch.setattr(masaustu_paketle, 'KOK', tmp_path)  # proje klasörü: ham/ yok
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'yerel'))  # masaüstü önbelleği de yok

    hedef = masaustu_paketle.baslangic_onbellegi()

    assert hedef == tmp_path / 'build' / 'ham_baslangic'
    assert (hedef / 'surum.txt').read_text(encoding='utf-8').isdigit()
