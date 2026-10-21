"""Haftanın maçları sekmesi: uygulamadaki bütün liglerin önümüzdeki 7 gündeki maçları, her ligin kendi modeliyle.
Öne çıkanlar: en dengeli maçlar, sürpriz kokan maçlar (modelin, puan durumunda gerideki takımı favori gördüğü),
en net favoriler ve en çok gol beklenen maçlar; altında gün gün bütün maçlar. Maça tıklanınca Maç tahmini açılır."""
from datetime import datetime, timedelta, timezone
import logging

from nicegui import run, ui

from ..sezon import LIGLER, SON_SEZON
from . import disa_aktar
from .ortak import e, fmt, kisa_gun, takim_logo, yerel, yuzde

logger = logging.getLogger(__name__)

ID, AD = 'haftanin', 'Bu hafta'
TEMBEL = True  # bütün liglerin modeli kurulur: yalnızca sekme açıkken
GUN = 7


def kur(G):
    d = {'maclar': [], 'zaman': None}
    with ui.column().classes('panel'):
        with ui.row().classes('w-full items-center'):
            ui.html('<h3>Haftanın maçları</h3>', sanitize=False)
            ui.space()
            disa_aktar.dugme('Excel\'e aktar', lambda: aktar(), 'Haftanın bütün maçları ve tahminleri İndirilenler\\MacTahmin '
                             'klasörüne CSV olarak')
            ui.button('Yenile', icon='refresh', on_click=lambda: G.arka_plan(yukle(True))).props('flat dense no-caps')
        lead = ui.label('Bütün liglerin önümüzdeki 7 gündeki maçları, her ligin kendi modeline göre. Maça tıklayınca tahmini açılır.'
                        ).classes('lead')
        durum = ui.label().classes('cap')
        one = ui.element('div').classes('w-full').style('display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px')
    with ui.column().classes('panel'):
        ui.html('<h3>Bütün maçlar</h3>', sanitize=False)
        hepsi = ui.html('', sanitize=False).classes('w-full')

    def aktar():
        basliklar = ['Tarih', 'Saat', 'Lig', 'Ev sahibi', 'Deplasman', 'Ev kazanır %', 'Beraberlik %', 'Deplasman kazanır %',
                     'Beklenen gol (ev)', 'Beklenen gol (dep.)', 'Ev sahibinin sırası', 'Deplasmanın sırası']
        satirlar = []
        for m in sorted(d['maclar'], key=lambda m: m['zaman']):
            z = yerel(m['zaman'])
            satirlar.append([f'{z:%d.%m.%Y}' if z else None, f'{z:%H:%M}' if z else None, m['lig_ad'], m['ev'], m['dep'],
                             round(m['p'][0] * 100, 1), round(m['p'][1] * 100, 1), round(m['p'][2] * 100, 1),
                             round(m['lh'], 2), round(m['la'], 2), m['sira_ev'], m['sira_dep']])
        return 'Haftanın maçları', basliklar, satirlar

    def tiklandi(ev):
        parca = str(ev.args or '').split('|')
        if len(parca) == 3:
            G.tahmin_ac(*parca)

    js = '(e) => { const t = e.target.closest("[data-mac]"); if (t) emit(t.dataset.mac); }'
    hepsi.on('click', tiklandi, js_handler=js)

    def satir(m, ek=''):
        z = yerel(m['zaman'])
        p = m['p']
        siniflar = ['kaz' if p[0] >= p[2] else 'kay', 'kaz' if p[2] > p[0] else 'kay']
        return (f'<div class="hm-mac" data-mac="{e(m["lig"])}|{e(m["ev"])}|{e(m["dep"])}">'
                f'<div class="cap">{kisa_gun(z.date()) + " " + f"{z:%H:%M}" if z else ""} · {e(m["lig_ad"])}{ek}</div>'
                f'<div class="hm-ev">{e(m["ev"])} <span class="cap">({m["sira_ev"]}.)</span> {takim_logo(m["ev_id"])}</div>'
                f'<div class="olas"><span class="{siniflar[0]}">{yuzde(p[0])}</span><span class="ber">{yuzde(p[1])}</span>'
                f'<span class="{siniflar[1]}">{yuzde(p[2])}</span></div>'
                f'<div class="hm-dep">{takim_logo(m["dep_id"])} {e(m["dep"])} <span class="cap">({m["sira_dep"]}.)</span></div></div>')

    def bolum(baslik, aciklama, maclar, ek=lambda m: ''):
        kutu = ui.html(f'<div class="disp" style="font-size:1.15rem;font-weight:700">{baslik}</div>'
                       f'<div class="cap" style="margin-bottom:4px">{aciklama}</div>'
                       + (''.join(satir(m, ek(m)) for m in maclar) or '<div class="cap">Maç yok.</div>'), sanitize=False)
        kutu.on('click', tiklandi, js_handler=js)

    def ciz():
        M = d['maclar']
        one.clear()
        with one:
            bolum('En dengeli maçlar', 'Favorinin kazanma olasılığı en düşük olanlar.',
                  sorted(M, key=lambda m: max(m['p'][0], m['p'][2]))[:6])
            surpriz = [m for m in M if (m['p'][0] > m['p'][2] and m['sira_ev'] > m['sira_dep'] + 3)
                       or (m['p'][2] > m['p'][0] and m['sira_dep'] > m['sira_ev'] + 3)]
            bolum('Sürpriz kokan maçlar', 'Model, puan durumunda en az 4 sıra gerideki takımı favori görüyor.',
                  sorted(surpriz, key=lambda m: -max(m['p'][0], m['p'][2]))[:6])
            bolum('En net favoriler', 'Favorinin kazanma olasılığı en yüksek olanlar.',
                  sorted(M, key=lambda m: -max(m['p'][0], m['p'][2]))[:6])
            bolum('En çok gol beklenen maçlar', 'İki takımın beklenen gol toplamına göre.',
                  sorted(M, key=lambda m: -(m['lh'] + m['la']))[:6], ek=lambda m: f' · beklenen {fmt(m["lh"] + m["la"], 1)} gol')
        gunler = {}
        for m in sorted(M, key=lambda m: m['zaman']):
            z = yerel(m['zaman'])
            gunler.setdefault(z.date() if z else None, []).append(m)
        hepsi.content = ''.join(f'<div class="tk-grup">{kisa_gun(g) if g else ""} · {len(ms)} maç</div>' + ''.join(satir(m) for m in ms)
                                for g, ms in gunler.items()) or '<p class="cap">Önümüzdeki 7 günde maç yok.</p>'

    async def yukle(zorla=False):
        if d['zaman'] and not zorla and datetime.now() - d['zaman'] < timedelta(minutes=30):
            ciz()
            return
        simdi = datetime.now(timezone.utc)
        sinir = simdi + timedelta(days=GUN)
        maclar = []
        for k, l in enumerate(LIGLER):
            durum.text = f'Ligler hazırlanıyor… {k + 1}/{len(LIGLER)} ({l[1]})'
            try:
                S = await run.io_bound(G.depo.sezon, l[0], SON_SEZON)
            except Exception:
                logger.debug('sezon kurulamadı: %s', l[0], exc_info=True)
                continue
            if not S.M:
                continue
            sira = {r['i']: n + 1 for n, r in enumerate(S.tablo)}
            for r in S.raw['u']:
                try:
                    z = datetime.fromisoformat(str(r[3]).replace('Z', '+00:00'))
                except (ValueError, IndexError):
                    continue
                if not simdi - timedelta(hours=2) <= z <= sinir:
                    continue
                t = S.tahmin(r[1], r[2])
                maclar.append({'lig': l[0], 'lig_ad': l[1], 'ev': S.T[r[1]], 'dep': S.T[r[2]], 'zaman': r[3], 'p': t['p'],
                               'lh': t['lh'], 'la': t['la'], 'sira_ev': sira.get(r[1]), 'sira_dep': sira.get(r[2]),
                               'ev_id': G.depo.takim_kimligi(l[0], S.T[r[1]]), 'dep_id': G.depo.takim_kimligi(l[0], S.T[r[2]])})
        d['maclar'], d['zaman'] = maclar, datetime.now()
        durum.text = f'{len(maclar)} maç · {datetime.now():%H:%M} itibarıyla. Parantez içi: puan durumundaki sıra.'
        ciz()

    return yukle
