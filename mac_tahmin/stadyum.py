"""Takımların iç saha stadyumları (FotMob). Maçın stadyumu ev sahibinin stadyumu kabul edilir.

d/stadyumlar.json biçimi:
  fotmob: {FotMob takım id: {ad, sehir, kapasite, takim, konum ([enlem, boylam] ya da None)}}
  ligler: {lig anahtarı: {uygulamadaki takım adı: FotMob takım id}}
"""
import difflib
import json
import unicodedata
from pathlib import Path

from . import sema
from .sezon import FOTMOB_ID as FOTMOB_LIG_ID, LIGLER, SON_SEZON
from .veri import fotmob_url, onbellekli
# Understat adı ile FotMob adı benzerlikle eşleşmeyen takımlar
ELLE = {
    'Wolverhampton Wanderers': 'Wolves', 'Nottingham Forest': 'Nottm Forest', 'Bayern Munich': 'Bayern München',
    'Borussia M.Gladbach': 'Borussia Mönchengladbach', 'FC Cologne': '1. FC Köln', 'Paris Saint Germain': 'Paris Saint-Germain',
    'Athletic Club': 'Athletic Club', 'Atletico Madrid': 'Atlético Madrid', 'Inter': 'Inter', 'AC Milan': 'AC Milan',
}
_EK = {'fc', 'afc', 'cf', 'ac', 'as', 'ss', 'sc', 'ssc', 'cd', 'ud', 'rc', 'rcd', 'sd', 'vfb', 'vfl', 'tsg', 'sv', 'fsv', 'ogc', 'osc', 'losc', 'calcio', 'club', 'de', 'and', 'hove', 'albion', '1', '1.', 'bk', 'sk', 'fk', 'jk'}


def _sade(s):
    s = unicodedata.normalize('NFD', s.lower().replace('ı', 'i'))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('-', ' ').replace('.', ' ')
    return ' '.join(w for w in s.split() if w not in _EK)


def eslestir(bizim, fotmob):
    """Uygulamadaki takım adlarını FotMob adlarına eşler: önce elle verilenler, sonra en benzer olan."""
    sonuc, kalan = {}, dict(fotmob)  # ad -> id
    for ad in bizim:
        hedef = ELLE.get(ad)
        if hedef and hedef in kalan:
            sonuc[ad] = kalan.pop(hedef)
    adaylar = []
    for ad in bizim:
        if ad in sonuc:
            continue
        for fad in kalan:
            a, b = _sade(ad), _sade(fad)
            puan = difflib.SequenceMatcher(None, a, b).ratio()
            if a and (a in b or b in a):
                puan += 0.5
            adaylar.append((puan, ad, fad))
    for puan, ad, fad in sorted(adaylar, reverse=True):
        if ad not in sonuc and fad in kalan and puan >= 0.5:
            sonuc[ad] = kalan.pop(fad)
    return sonuc


def _konum(v):
    """FotMob'un stadyum konumu (["enlem", "boylam"] yazı olarak) → [enlem, boylam] ya da None."""
    try:
        return [float(v[0]), float(v[1])]
    except (TypeError, ValueError, IndexError):
        return None


def stadyumlar_indir(veri_klasoru, ham, yenile=False, yaz=print):
    fotmob, ligler = {}, {}
    for anahtar, ad, *_ in LIGLER:
        lid = FOTMOB_LIG_ID[anahtar]
        lg = onbellekli(Path(ham) / f'fm-lig-{lid}.json', fotmob_url('leagues', id=lid), yenile=yenile)
        sema.kontrol('lig', lg)
        takimlar = {}
        for m in lg['fixtures']['allMatches']:
            for t in (m['home'], m['away']):
                takimlar[t['name']] = int(t['id'])
        bizim_dosya = Path(veri_klasoru) / f'{anahtar}-{SON_SEZON}.json'
        bizim = json.loads(bizim_dosya.read_text(encoding='utf-8'))['t'] if bizim_dosya.exists() else list(takimlar)
        eslesme = eslestir(bizim, takimlar)
        ligler[anahtar] = eslesme
        for tad, tid in takimlar.items():
            t = onbellekli(Path(ham) / f'fm-takim-{tid}.json', fotmob_url('teams', id=tid), yenile=yenile)
            sema.kontrol('takim_stadyum', t)
            v = (t.get('overview') or {}).get('venue') or {}
            w = v.get('widget') or {}
            kap = next((p[1] for p in v.get('statPairs') or [] if p and p[0] == 'Capacity'), None)
            if w.get('name'):
                fotmob[str(tid)] = {'ad': w['name'], 'sehir': w.get('city') or '', 'kapasite': kap, 'takim': tad,
                                    'konum': _konum(w.get('location'))}
        eksik = [b for b in bizim if b not in eslesme]
        yaz(f'{anahtar}: {len(eslesme)}/{len(bizim)} takım eşleşti' + (f'; eşleşmeyen: {", ".join(eksik)}' if eksik else ''))
        for b, tid in sorted(eslesme.items()):
            fad = next(k for k, v in takimlar.items() if v == tid)
            if _sade(b) != _sade(fad):
                yaz(f'    {b} -> {fad} ({(fotmob.get(str(tid)) or {}).get("ad", "stadyum yok")})')
    yol = Path(veri_klasoru) / 'stadyumlar.json'
    yol.write_text(json.dumps({'fotmob': fotmob, 'ligler': ligler}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    yaz(f'{len(fotmob)} stadyum yazıldı: {yol}')


def stadyum_oku(veri_klasoru):
    yol = Path(veri_klasoru) / 'stadyumlar.json'
    return json.loads(yol.read_text(encoding='utf-8')) if yol.exists() else {'fotmob': {}, 'ligler': {}}


def stadyum_bul(st, lig, takim_adi):
    tid = (st['ligler'].get(lig) or {}).get(takim_adi)
    return st['fotmob'].get(str(tid)) if tid is not None else None
