"""Testlerin ortak yardımcıları: küçük, uydurma sezon verisi (d/ klasörüne dokunmaz)."""
from datetime import date, timedelta

from mac_tahmin.sezon import Sezon


def ham_sezon(takimlar, oynanan, kalan=(), baslangic='2026-08-01', oyuncular=()):
    """Ham sezon sözlüğü (d/*.json biçimi). oynanan: [(ev, dep, ev golü, dep golü)] — her biri bir gün arayla oynanmış
    sayılır; kalan: [(ev, dep)] oynanmamış maçlar. Takımlar indeks (0, 1, …) ya da ad olabilir."""
    ix = {t: i for i, t in enumerate(takimlar)}
    k = lambda t: ix[t] if t in ix else t  # noqa: E731
    g0 = date.fromisoformat(baslangic)
    m = [[(g0 + timedelta(days=i)).isoformat(), k(h), k(a), hg, ag, None, None] for i, (h, a, hg, ag) in enumerate(oynanan)]
    son = g0 + timedelta(days=len(oynanan) + 6)
    u = [[(son + timedelta(days=i)).isoformat(), k(h), k(a), f'{(son + timedelta(days=i)).isoformat()}T18:00:00.000Z']
         for i, (h, a) in enumerate(kalan)]
    return {'src': 'fotmob', 't': list(takimlar), 'm': m, 'u': u, 'tx': None, 'x': [], 'p': list(oyuncular), 'skip': 0}


def sezon_kur(takimlar, oynanan, kalan=(), anahtar=None, yil=2026, oyuncular=()):
    return Sezon(ham_sezon(takimlar, oynanan, kalan, oyuncular=oyuncular), anahtar, yil)


def cift_devre(takimlar, skor, turlar=1):
    """Her takım çifti iki kez (ev ve deplasman) oynar; skor(ev, dep, tur) → (ev golü, dep golü). turlar > 1: tekrar."""
    out = []
    for tur in range(turlar):
        for h in takimlar:
            for a in takimlar:
                if h != a:
                    out.append((h, a, *skor(h, a, tur)))
    return out


def oyuncu(ad, takim, g=0, xg=0.0, a=0, xa=0.0, dk=900, mp=10, pos='F', no=None):
    """Ham oyuncu satırı (d/*.json 'p' biçimi): ad, takım, mevki, maç, dakika, gol, xG, asist, xA, şut, kilit pas, sarı, kırmızı."""
    return [ad, takim, pos, mp, dk, g, xg, a, xa, 10, 5, 1, 0, [], no, 'TUR', None, None, None]
