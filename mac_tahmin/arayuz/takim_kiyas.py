"""Takım kıyasla: Kıyasla sekmesinin altındaki panel (kiyas.kur çağırır). Açık ligin iki takımı yan yana: puan, gol, xG,
hak edilen puan, Elo, form, kadro değeri, sahadaki yaş ortalaması, kalan fikstürün zorluğu; altında aralarındaki maçın
tahmini ve geçmiş karşılaşmalar. Her satırda daha iyi olan vurgulanır.

Yeni ölçüt eklemek: olcutler() içindeki listeye (başlık, A'nın değeri, B'nin değeri, biçim, yüksek mi iyi) satırı ekle."""
from nicegui import run, ui

from ..bicim import para
from ..sezon import ELO_EV, FIKSTUR_SONRAKI, SON_SEZON, fikstur_zorlugu, hak_edilen_puan
from .ortak import e, fmt, form, takim_logo, yuzde

FORM_PUAN = {'G': 3, 'B': 1, 'M': 0}


def _para(x):
    return para(x, '–', yalniz_m=True)


def sahadaki_yas(S, i):
    """Takımın bu sezon ligde sahaya çıkan oyuncularının dakikaya göre ağırlıklı yaş ortalaması."""
    oy = [p for p in S.PLY if S.T[i] in p['t'].split(' / ') and p.get('yas') and p['min'] > 0]
    dk = sum(p['min'] for p in oy)
    return sum(p['yas'] * p['min'] for p in oy) / dk if dk else None


def olcutler(S, a, b, xp):
    """Kıyas satırları: (başlık, A'nın değeri, B'nin değeri, biçim, yüksek mi iyi). xp: hak_edilen_puan sonucu (ya da None)."""
    ra, rb = S.tb[a], S.tb[b]
    mac = lambda r: r['O'] or 1  # noqa: E731
    fm = form(S)
    fz = {r['i']: r for r in fikstur_zorlugu(S)} if S.yil == SON_SEZON and S.U else {}
    xp = xp or {}
    satir = [
        ('Puan (maç başına)', ra['P'] / mac(ra), rb['P'] / mac(rb), 2, True),
        ('Attığı gol (maç başına)', ra['AG'] / mac(ra), rb['AG'] / mac(rb), 2, True),
        ('Yediği gol (maç başına)', ra['YG'] / mac(ra), rb['YG'] / mac(rb), 2, False),
    ]
    if S.xg_var:
        satir += [('xG (maç başına)', ra['xG'] / mac(ra), rb['xG'] / mac(rb), 2, True),
                  ('Verdiği xG (maç başına)', ra['xGA'] / mac(ra), rb['xGA'] / mac(rb), 2, False)]
    if S.T[a] in xp and S.T[b] in xp:
        xa, xb = xp[S.T[a]], xp[S.T[b]]
        satir.append(('Hak edilen puan (maç başına)', xa['xP'] / xa['mac'], xb['xP'] / xb['mac'], 2, True))
    satir += [('Elo puanı', S.elo[a], S.elo[b], 0, True),
              ('Form (son 5 maç puanı)', sum(FORM_PUAN[x] for x in fm[a]), sum(FORM_PUAN[x] for x in fm[b]), 0, True)]
    if S.kadro_degeri:
        satir.append(('Kadro değeri', S.kadro_degeri[a], S.kadro_degeri[b], 'para', True))
    ya, yb = sahadaki_yas(S, a), sahadaki_yas(S, b)
    if ya and yb:
        satir.append(('Sahadaki yaş ortalaması', ya, yb, 1, None))  # iyisi yok: bilgi
    if a in fz and b in fz:
        satir.append((f'Fikstür zorluğu: sıradaki {FIKSTUR_SONRAKI} maç', fz[a]['zorluk5'], fz[b]['zorluk5'], 0, False))
        satir.append(('Fikstür zorluğu: kalan bütün maçlar', fz[a]['zorluk'], fz[b]['zorluk'], 0, False))
    return satir


def kur(G):
    d = {'S': None, 'xp': None}
    with ui.column().classes('panel'):
        ui.html('<h3>Takım kıyasla</h3>', sanitize=False)
        ui.label('Açık ligin iki takımı yan yana; her satırda daha iyi olan yeşil. Aralarındaki maçın tahmini ve geçmiş '
                 'karşılaşmalar altta.').classes('lead')
        with ui.row().classes('w-full items-end gap-3'):
            a_sec = ui.select({}, label='Takım 1', with_input=True).props('outlined dense options-dense').style('min-width:220px')
            b_sec = ui.select({}, label='Takım 2', with_input=True).props('outlined dense options-dense').style('min-width:220px')
        tablo = ui.html('', sanitize=False).classes('w-full kaydir')
        ozet = ui.html('', sanitize=False).classes('w-full')
        h2h = ui.label().classes('cap')
        notlar = ui.label().classes('cap')

    def ciz():
        S = d['S']
        a, b = a_sec.value, b_sec.value
        if S is None or a is None or b is None or a == b:
            tablo.content = ozet.content = ''
            return
        satirlar, skor = [], [0, 0]
        for baslik, va, vb, bicim, yuksek_iyi in olcutler(S, a, b, d['xp']):
            yaz = _para if bicim == 'para' else (lambda v: fmt(v, bicim))
            iyi_a = iyi_b = False
            if yuksek_iyi is not None and abs(va - vb) > 1e-9:
                iyi_a = (va > vb) == yuksek_iyi
                iyi_b = not iyi_a
                skor[0 if iyi_a else 1] += 1
            stil = lambda iyi: 'color:var(--pitch-2);font-weight:700' if iyi else ''  # noqa: E731
            satirlar.append(f'<tr><td>{e(baslik)}</td><td style="text-align:center;{stil(iyi_a)}">{yaz(va)}</td>'
                            f'<td style="text-align:center;{stil(iyi_b)}">{yaz(vb)}</td></tr>')
        logo = lambda i: takim_logo(G.depo.takim_kimligi(S.lig, S.T[i]))  # noqa: E731
        tablo.content = (f'<table class="tb"><thead><tr><th></th><th style="text-align:center">{logo(a)}{e(S.T[a])}</th>'
                         f'<th style="text-align:center">{logo(b)}{e(S.T[b])}</th></tr></thead><tbody>'
                         + ''.join(satirlar) + '</tbody></table>')
        pa, pb = S.olasilik(a, b), S.olasilik(b, a)
        ustun = S.T[a] if skor[0] > skor[1] else S.T[b] if skor[1] > skor[0] else None
        ozet.content = (
            f'<div class="lead" style="margin-top:8px">Ölçütlerin {skor[0]} tanesinde {e(S.T[a])}, {skor[1]} tanesinde '
            f'{e(S.T[b])} önde' + (f'; genel tablo <b>{e(ustun)}</b> lehine.' if ustun else '; denk görünüyorlar.') + '</div>'
            f'<div class="lead">Aralarındaki maçın tahmini · {e(S.T[a])} evinde: {e(S.T[a])} {yuzde(pa[0])}, beraberlik '
            f'{yuzde(pa[1])}, {e(S.T[b])} {yuzde(pa[2])} · {e(S.T[b])} evinde: {e(S.T[b])} {yuzde(pb[0])}, beraberlik '
            f'{yuzde(pb[1])}, {e(S.T[a])} {yuzde(pb[2])}</div>')
        h2h.text = ''
        G.arka_plan(h2h_ciz(S, a, b))
        notlar.text = ('Maç başına değerler bu sezonun lig maçlarından. Hak edilen puan, maçların xG\'sinden; Elo maç maç '
                       f'güncellenen güç puanı (ev avantajı {ELO_EV} puan); fikstür zorluğu rakiplerin ortalama Elo\'su, '
                       f'sıradaki {FIKSTUR_SONRAKI} maçta ve kalan bütün maçlarda (düşük olan daha kolay; sezon başında '
                       'herkes kalan maçlarda hemen herkesle oynadığından bütün maçlardaki fark küçüktür). Sahadaki yaş, '
                       'dakikaya göre ağırlıklı ortalama (iyisi kötüsü yok, bilgi için).')

    async def h2h_ciz(S, a, b):
        ad_a, ad_b = S.T[a], S.T[b]
        maclar = await run.io_bound(G.depo.karsilasmalar, S.lig, ad_a, ad_b)
        if d['S'] is not S or (a_sec.value, b_sec.value) != (a, b):  # bu arada başka takım seçildi
            return
        if not maclar:
            metin = 'Bu ligde (uygulamadaki sezonlarda) aralarında maç yok.'
        else:
            ga = sum(1 for m in maclar if (m[1] == ad_a and m[3] > m[4]) or (m[2] == ad_a and m[4] > m[3]))
            gb = sum(1 for m in maclar if (m[1] == ad_b and m[3] > m[4]) or (m[2] == ad_b and m[4] > m[3]))
            metin = (f'Son {len(maclar)} karşılaşma: {ad_a} {ga} galibiyet, {len(maclar) - ga - gb} beraberlik, '
                     f'{ad_b} {gb} galibiyet.')
        h2h.text = metin

    async def yenile():
        S = G.S
        d['S'], d['xp'] = S, None
        secenek = {i: S.T[i] for i in sorted(range(len(S.T)), key=lambda i: S.T[i])}
        sira = [r['i'] for r in S.tablo]
        a = a_sec.value if a_sec.value in secenek and d.get('lig') == S.lig else sira[0]
        b = b_sec.value if b_sec.value in secenek and d.get('lig') == S.lig else sira[1]
        d['lig'] = S.lig
        d['sessiz'] = True
        a_sec.set_options(secenek, value=a)
        b_sec.set_options(secenek, value=b)
        d['sessiz'] = False
        ciz()
        maclar, _ = await run.io_bound(G.depo.xg_maclari, S)
        if d['S'] is not S:
            return
        d['xp'] = hak_edilen_puan([m[1:] for m in maclar]) if maclar else {}
        ciz()

    for s in (a_sec, b_sec):
        s.on_value_change(lambda _: None if d.get('sessiz') else ciz())
    return yenile
