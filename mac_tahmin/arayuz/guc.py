"""Güç sıralaması sekmesi: Elo gelişimi ve takımların hücum/savunma gücü."""
from nicegui import ui

from .ortak import fmt, takim_link, takim_logo, takim_tiklama

ID, AD = 'guc', 'Güç'
TEMBEL = True  # yalnızca sekme açıkken çizilir
RENKLER =['#1c5b3e', '#c9960f', '#35598a', '#b0413e', '#7b4fa0', '#2a8c8c']


def kur(G):
    secili = []
    with ui.column().classes('panel'):
        ui.html('<h3>Elo gelişimi</h3>', sanitize=False)
        ui.label('Elo, her maçtan sonra sonuca ve rakibin gücüne göre güncellenir; sezonlar arasında taşınır. '
                 'En fazla altı takım seçilebilir.').classes('lead')
        cipler = ui.row().classes('w-full gap-1')
        elo = ui.echart({
            'animation': False, 'tooltip': {'trigger': 'axis', 'order': 'valueDesc'}, 'legend': {'bottom': 0},
            'grid': {'left': 50, 'right': 16, 'top': 16, 'bottom': 50},
            'xAxis': {'type': 'category', 'name': 'Oynanan maç', 'nameLocation': 'middle', 'nameGap': 26, 'data': []},
            'yAxis': {'type': 'value', 'name': 'Elo', 'scale': True},
            'series': [],
        }).classes('w-full').style('height:360px')
    with ui.row().classes('w-full gap-4 items-start'):
        with ui.column().classes('panel').style('flex:2 1 420px;width:auto'):
            ui.html('<h3>Hücum ve savunma</h3>', sanitize=False)
            ui.label('Maç başına atılan ve yenen golün lig ortalamasına oranı. Sağ üst köşe: çok gol atan, az gol yiyen takımlar.').classes('lead')
            hs = ui.echart({
                'animation': False, 'tooltip': {'trigger': 'item'},
                'grid': {'left': 60, 'right': 20, 'top': 16, 'bottom': 50},
                'xAxis': {'type': 'value', 'name': 'Hücum gücü (sağ = çok gol atar)', 'nameLocation': 'middle', 'nameGap': 28, 'scale': True},
                'yAxis': {'type': 'value', 'name': 'Yenen gol çarpanı (üst = sağlam savunma)', 'nameLocation': 'middle',
                          'nameGap': 44, 'inverse': True, 'scale': True},
                'series': [{'type': 'scatter', 'symbolSize': 11, 'itemStyle': {'color': '#1c5b3e'},
                            'label': {'show': True, 'position': 'right', 'fontSize': 10, 'formatter': '{b}'}, 'data': []}],
            }).classes('w-full').style('height:420px')
        with ui.column().classes('panel').style('flex:1 1 280px;width:auto'):
            ui.html('<h3>Elo sıralaması</h3>', sanitize=False)
            sira = takim_tiklama(ui.html('', sanitize=False).classes('kaydir'), G)

    def elo_ciz():
        S = G.S
        uzun = max(len(h) for h in S.hist)
        elo.options['xAxis']['data'] = list(range(uzun + 1))
        # takımın rengi seçildiği sırada kalır (yeni takım eklenince renkler kaymasın); çizgiler, açıklama ve üstüne
        # gelince çıkan liste güncel Elo'ya göre sıralı
        renk = {i: RENKLER[k % len(RENKLER)] for k, i in enumerate(secili)}
        elo.options['series'] = [{'type': 'line', 'name': S.T[i], 'showSymbol': False, 'smooth': True,
                                  'lineStyle': {'width': 2.5}, 'itemStyle': {'color': renk[i]},
                                  'data': [round(x, 1) for x in [S.elo_bas[i], *S.hist[i]]]}
                                 for i in sorted(secili, key=lambda i: -S.elo[i])]
        elo.update()
        cipler.clear()
        with cipler:
            for r in S.reyting:
                on = r['i'] in secili
                ui.button(r['name'], on_click=lambda _, i=r['i']: degistir(i)).props(
                    f'dense no-caps unelevated {"color=primary" if on else "outline color=grey-8"}').classes(
                    'text-sm').style('padding:3px 10px')

    def degistir(i):
        if i in secili:
            secili.remove(i)
        else:
            secili.append(i)
            del secili[:-6]
        elo_ciz()

    def yenile():
        S = G.S
        secili[:] = [r['i'] for r in S.reyting[:4]]
        elo_ciz()
        hs.options['series'][0]['data'] = [{'name': r['name'], 'value': [round(r['hucum'], 3), round(r['savunma'], 3)]}
                                           for r in S.reyting]
        hs.update()
        sira.content = ('<table class="tb"><thead><tr><th>#</th><th>Takım</th><th>Elo</th><th>Hücum</th><th>Savunma</th></tr></thead><tbody>'
                        + ''.join(f'<tr><td>{k + 1}</td><td class="takim-hucre">{takim_logo(G.depo.takim_kimligi(S.lig, r["name"]))}'
                                  f'{takim_link(r["name"], r["name"])}</td><td class="hi">{round(r["elo"])}</td>'
                                  f'<td>{fmt(r["hucum"])}</td><td>{fmt(r["savunma"])}</td></tr>' for k, r in enumerate(S.reyting))
                        + '</tbody></table>')

    return yenile
