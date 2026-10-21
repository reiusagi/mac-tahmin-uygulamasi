"""Kaynak Python 3.11'de de çalışmalı (README 3.11+): PEP 701'e (3.12) özgü f-string yazımı kullanılmaz."""
import tokenize
from pathlib import Path

from conftest import KOK

KAPALI = ('__pycache__', 'vendor')


def pep701_sorunlari(yol):
    """[(satır, ne)]: f-string ifadesinde aynı tırnağın yeniden kullanılması, ters bölü, yorum ya da tek tırnaklı
    f-string'de satır sonu. Python 3.12+ ayrıştırıcısıyla çalışır (FSTRING_* belirteçleri)."""
    with open(yol, 'rb') as f:
        belirtecler = list(tokenize.tokenize(f.readline))
    out, yigin = [], []  # yigin: [açılış tırnağı, süslü parantez derinliği]
    for t in belirtecler:
        if t.type == tokenize.FSTRING_START:
            tirnak = t.string.lstrip('fFrRbBuU')
            if yigin and yigin[-1][1] > 0 and any(y[0] == tirnak for y in yigin):
                out.append((t.start[0], 'iç içe aynı tırnak'))
            yigin.append([tirnak, 0])
        elif t.type == tokenize.FSTRING_END:
            yigin.pop()
        elif not yigin:
            continue
        elif t.type == tokenize.OP and t.string in '{}':
            yigin[-1][1] += 1 if t.string == '{' else -1
        elif yigin[-1][1] > 0:
            if t.type == tokenize.STRING:
                govde = t.string.lstrip('rRbBuUfF')
                tirnak = govde[:3] if govde[:3] in ('"""', "'''") else govde[:1]
                if any(y[0] == tirnak for y in yigin):
                    out.append((t.start[0], 'iç içe aynı tırnak'))
                if chr(92) in t.string:
                    out.append((t.start[0], 'ifade içinde ters bölü'))
            elif t.type in (tokenize.NL, tokenize.NEWLINE) and len(yigin[-1][0]) == 1:
                out.append((t.start[0], 'tek tırnaklı f-string ifadesinde satır sonu'))
            elif t.type == tokenize.COMMENT:
                out.append((t.start[0], 'ifade içinde yorum'))
    return out


def test_denetci_pep701_yazimini_yakalar(tmp_path):
    kotu = tmp_path / 'k.py'
    kotu.write_text('x = f"{d["k"]}"\ny = f"{chr(1)}{\'a\\n\'.join(z)}"\n', encoding='utf-8')
    iyi = tmp_path / 'i.py'
    iyi.write_text('x = f"{d[\'k\']}"\ny = f\'\'\'{d[\'k\']}\'\'\'\nz = f"{a:{w}} {{}}"\n', encoding='utf-8')
    assert [s for s, _ in pep701_sorunlari(kotu)] == [1, 2]
    assert pep701_sorunlari(iyi) == []


def test_kaynakta_pep701_yazimi_yok():
    dosyalar = [p for k in ('mac_tahmin', 'tests') for p in (KOK / k).rglob('*.py') if not set(p.parts) & set(KAPALI)]
    dosyalar += [KOK / 'MacTahmin.pyw', KOK / 'masaustu_paketle.py']
    sorunlar = [f'{Path(p).relative_to(KOK)}:{s}: {ne}' for p in dosyalar for s, ne in pep701_sorunlari(p)]
    assert not sorunlar, sorunlar
