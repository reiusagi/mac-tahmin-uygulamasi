"""Modeller sekmesi: tahmin modellerinin bu sezonun son %30'undaki başarısı, özellik önemleri ve test maçları."""
import logging

from nicegui import run, ui

from .ortak import e, fmt, tarih_uzun, yuzde

logger = logging.getLogger(__name__)

ID, AD = 'modeller', 'Modeller'
TEMBEL = True  # modellerin eğitimi saniyeler sürer: yalnızca sekme açıkken hesaplanır
SONUC = ['Ev', 'Beraberlik', 'Deplasman']
EN_AZ_MAC = 120  # model karşılaştırması için sezonda en az bu kadar maç (azsa aynı ligin geçen sezonu gösterilir)


def kur(G):
    with ui.column().classes('panel'):
        ui.html('<h3>Model karşılaştırması</h3>', sanitize=False)
        lead = ui.label().classes('lead')
        tablo = ui.html('', sanitize=False).classes('kaydir')
    with ui.row().classes('w-full gap-4 items-start') as alt:
        with ui.column().classes('panel').style('flex:1 1 340px;width:auto'):
            ui.html('<h3>Random Forest: hangi bilgi önemli?</h3>', sanitize=False)
            onem = ui.echart({
                'animation': False, 'grid': {'left': 120, 'right': 20, 'top': 10, 'bottom': 30},
                'xAxis': {'type': 'value'}, 'yAxis': {'type': 'category', 'inverse': True, 'data': []},
                'series': [{'type': 'bar', 'itemStyle': {'color': '#2f7a57'}, 'data': []}], 'tooltip': {},
            }).classes('w-full').style('height:340px')
        with ui.column().classes('panel').style('flex:2 1 460px;width:auto'):
            ui.html('<h3>Test maçları</h3>', sanitize=False)
            test_not = ui.label().classes('cap')
            test = ui.html('', sanitize=False).classes('kaydir').style('max-height:420px;overflow-y:auto')

    async def yenile():
        S, onceki_not = G.S, ''
        if len(S.M) < EN_AZ_MAC:
            # süren sezonda henüz yeterli maç yoksa aynı ligin geçen sezonu gösterilir (seçim değiştirmeye gerek kalmasın)
            n = len(S.M)
            try:
                S2 = await run.io_bound(G.depo.sezon, S.lig, S.yil - 1)
            except Exception:
                logger.debug('geçen sezon kurulamadı: %s', S.lig, exc_info=True)
                S2 = None
            if G.S is not S:
                return
            if S2 is None or len(S2.M) < EN_AZ_MAC:
                lead.text = f'Model karşılaştırması için sezonda en az {EN_AZ_MAC} maç oynanmış olmalı (şu an {n}).'
                tablo.content = ''
                alt.set_visibility(False)
                return
            S = S2
            onceki_not = (f'Bu sezon henüz {n} maç oynandı (en az {EN_AZ_MAC} gerekiyor); aşağıdaki sonuçlar aynı ligin '
                          'geçen sezonundan. ')
        if S._ev is None:
            lead.text = 'Modeller eğitiliyor ve test ediliyor… (birkaç saniye sürebilir)'
            tablo.content = ''
            alt.set_visibility(False)
            await run.io_bound(S.degerlendir)
            if G.S.lig != S.lig:
                return
        ev = S.degerlendir()
        alt.set_visibility(True)
        bu = 'o' if onceki_not else 'bu'
        lead.text = onceki_not + (f'Test: {bu} sezonun son {ev["n_test"]} maçı. Tek sezon: modeller yalnızca {bu} sezonun ilk {ev["n_egitim"]} maçıyla eğitildi.'
                     + (f' Önceki sezonlarla: buna önceki {ev["n_onceki"]} sezonun {ev["n_gecmis"]} maçı eklendi, Elo ve takım '
                        'güçleri sezondan sezona taşındı' + (', maçların xG değerleri de özellik olarak kullanıldı' if ev['xg'] else '') + '.'
                        if ev['n_onceki'] else ' Bu lig için önceki sezon verisi yok.')
                     + ' Log-loss olasılıkların kalitesini ölçer: düşük olan daha iyi.')
        son = lambda r: r['cok'] or r['tek']
        en_iyi = min(son(r)['log_loss'] for r in ev['sonuclar'])
        cok_var = bool(ev['n_onceki'])

        def fark(r):
            if not r['cok']:
                return '–'
            d = r['cok']['log_loss'] - r['tek']['log_loss']
            return f'<span class="{"ok" if d < -0.0005 else "no" if d > 0.0005 else ""}">{"+" if d > 0 else ""}{fmt(d, 3)}</span>'

        tablo.content = ('<table class="tb"><thead><tr><th>Model</th><th>Doğruluk</th><th>Log-loss (tek sezon)</th>'
                         + ('<th>Log-loss (önceki sezonlarla)</th><th>Fark</th>' if cok_var else '') + '</tr></thead><tbody>'
                         + ''.join(f'<tr class="{"best-row" if son(r)["log_loss"] == en_iyi else ""}"><td>{e(r["model"])}</td>'
                                   f'<td>{yuzde(son(r)["dogruluk"])}</td><td>{fmt(r["tek"]["log_loss"], 3)}</td>'
                                   + (f'<td>{fmt(r["cok"]["log_loss"], 3)}</td><td>{fark(r)}</td>' if cok_var else '') + '</tr>'
                                   for r in ev['sonuclar'])
                         + '</tbody></table>')
        onem.options['yAxis']['data'] = [o['f'] for o in ev['onem']]
        onem.options['series'][0]['data'] = [round(o['v'], 4) for o in ev['onem']]
        onem.update()
        test_not.text = ('Lojistik regresyonun' + (' (önceki sezonlarla eğitilmiş)' if cok_var else '')
                         + ' her test maçı için verdiği olasılıklar; en yüksek olasılık tahmin sayılır.')
        satirlar = []
        for t in reversed(ev['test']):
            p, m = t['p'], t['mac']
            sec = p.index(max(p))
            ok = sec == t['sonuc']
            satirlar.append(f'<tr><td>{e(t["ev"])} – {e(t["dep"])}</td><td>{tarih_uzun(m.d)}</td><td>{m.hg}-{m.ag}</td>'
                            f'<td>{yuzde(p[0])}</td><td>{yuzde(p[1])}</td><td>{yuzde(p[2])}</td>'
                            f'<td class="{"ok" if ok else "no"}">{SONUC[sec]} {"✓" if ok else "✗"}</td></tr>')
        test.content = ('<table class="tb"><thead><tr><th>Maç</th><th>Tarih</th><th>Skor</th><th>Ev</th><th>X</th><th>Dep.</th>'
                        '<th>Tahmin</th></tr></thead><tbody>' + ''.join(satirlar) + '</tbody></table>')

    return yenile
