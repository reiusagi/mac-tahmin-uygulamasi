"""Milli takımlar sekmesi: turnuva ve sezon seçimi, grup tabloları (renklerin anlamıyla), maçlar (sıradakiler
tahminli), iki milli takım arasında maç tahmini, milli takım Elo sıralaması ve takım kartı (maç geçmişi). Hesaplar
milli.py'de. Bir takımın adına tıklanınca kartı açılır."""
from datetime import datetime, timezone

from nicegui import app, run, ui

from .. import milli
from ..logo import lig_logo_url
from . import mac_tahmini
from .ortak import e, fmt, kisa_gun, tarih_uzun, tr_anahtar, yerel, yuzde

ID, AD = 'milli', 'Milli'
TUR_ADI = {'Round of 32': 'Son 32', 'Round of 16': 'Son 16', 'Quarter-Finals': 'Çeyrek final', 'Semi-Finals': 'Yarı final',
           'Bronze Final': 'Üçüncülük maçı', 'Final': 'Final'}
TEMBEL = True  # Elo bütün milli maçlardan hesaplanır: yalnızca sekme açıkken
VARSAYILAN_TURNUVA = 9806


def _sonuc(atilan, yenilen):
    return 'G' if atilan > yenilen else 'B' if atilan == yenilen else 'M'


def _tablo(basliklar, satirlar, tikla):
    """Satırları tıklanabilir tablo. satirlar: [(anahtar, [(hücre HTML'i, sınıf, stil)])]; tikla(anahtar)."""
    with ui.element('table').classes('tb'):
        with ui.element('thead'), ui.element('tr'):
            for b in basliklar:
                with ui.element('th'):
                    ui.html(b, sanitize=False)
        with ui.element('tbody'):
            for anahtar, hucreler in satirlar:
                with ui.element('tr').style('cursor:pointer').on('click', lambda _, a=anahtar: tikla(a)):
                    for icerik, sinif, stil in hucreler:
                        with ui.element('td').classes(sinif).style(stil):
                            ui.html(icerik, sanitize=False)


def _rozet(s):
    return f'<i class="{s}" title="{ {"G": "Galibiyet", "B": "Beraberlik", "M": "Mağlubiyet"}[s]}">{s}</i>'


def kur(G):
    hafiza = app.storage.general.get('milli', {})
    d = {'tid': hafiza.get('tid', VARSAYILAN_TURNUVA), 'sezon': None, 'E': None, 'v': None}
    turnuva_sec = {tid: ad for tid, ad, *_ in milli.TURNUVALAR}

    with ui.row().classes('w-full items-end gap-3'):
        turnuva = ui.select(turnuva_sec, value=d['tid'] if d['tid'] in turnuva_sec else VARSAYILAN_TURNUVA,
                            label='Turnuva').props('outlined dense options-dense').style('min-width:300px')
        with turnuva.add_slot('prepend'):  # seçili turnuvanın logosu, kutunun solunda
            turnuva_logo = ui.html('', sanitize=False)
        sezon = ui.select({}, label='Sezon').props('outlined dense options-dense').style('min-width:140px')
        durum = ui.label().classes('cap')

    with ui.column().classes('panel') as grup_panel:
        grup_baslik = ui.html('<h3>Gruplar</h3>', sanitize=False)
        ui.label('Takımın kartını ve maç geçmişini görmek için adına tıkla.').classes('cap')
        grup_izgara = ui.element('div').classes('w-full').style(
            'display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px')

    with ui.row().classes('w-full gap-4 items-start'):
        with ui.column().classes('panel').style('flex:3 1 460px;width:auto'):
            ui.html('<h3>Maçlar</h3>', sanitize=False)
            ui.label('Oynanmamış maçlarda olasılıklar (ev · beraberlik · deplasman) milli takım Elo\'suna göredir. Maça '
                     'tıklayınca ayrıntılı tahmin açılır (skor olasılıkları, goller, elemede turu kim geçer, son maçlar); '
                     'takımın adına tıklayınca kartı açılır.').classes('cap')
            mac_kutu = ui.column().classes('w-full gap-0').style('max-height:640px;overflow-y:auto')
        with ui.column().classes('panel').style('flex:2 1 340px;width:auto'):
            ui.html('<h3>Maç tahmini</h3>', sanitize=False)
            ev = ui.select({}, label='Ev sahibi', with_input=True).props('outlined dense options-dense').classes('w-full')
            dep = ui.select({}, label='Deplasman', with_input=True).props('outlined dense options-dense').classes('w-full')
            tarafsiz = ui.checkbox('Tarafsız saha (turnuva finalleri)')
            tahmin_kutu = ui.html('', sanitize=False).classes('w-full')
            ui.button('Ayrıntılı tahmin', icon='insights', on_click=lambda: serbest_ayrinti()).props(
                'flat dense no-caps')

    with ui.column().classes('panel'):
        ui.html('<h3>Milli takım güç sıralaması (Elo)</h3>', sanitize=False)
        elo_not = ui.label().classes('lead')
        siralama = ui.element('div').classes('kaydir w-full').style('max-height:520px;overflow-y:auto')

    # ---------------------------------------------------------------- takım kartı
    with ui.dialog() as kart, ui.card().classes('w-full gap-3').style('max-width:900px;background:var(--panel);color:var(--ink)'):
        with ui.row().classes('w-full items-start no-wrap'):
            with ui.column().classes('gap-0 grow'):
                kart_ad = ui.label().classes('disp').style('font-size:2rem;font-weight:700;line-height:1.1')
                kart_meta = ui.label().classes('cap')
            kart_elo = ui.html('', sanitize=False).style('text-align:center')
            ui.button(icon='close', on_click=kart.close).props('flat round dense')
        kart_ozet = ui.html('', sanitize=False).classes('w-full')
        kart_grafik = ui.echart({
            'animation': False, 'tooltip': {'trigger': 'axis'}, 'grid': {'left': 50, 'right': 16, 'top': 10, 'bottom': 30},
            'xAxis': {'type': 'category', 'data': []}, 'yAxis': {'type': 'value', 'scale': True, 'name': 'Elo'},
            'series': [{'type': 'line', 'showSymbol': False, 'data': [], 'itemStyle': {'color': '#1c5b3e'}}],
        }).classes('w-full').style('height:220px')
        ui.label('Sıradaki maçlar').classes('disp text-lg font-bold')
        kart_gelecek = ui.column().classes('w-full gap-0')
        with ui.row().classes('w-full items-center'):
            ui.label('Maç geçmişi').classes('disp text-lg font-bold')
            ui.space()
            kart_filtre = ui.select({'': 'Bütün turnuvalar'}, value='', label='Turnuva').props('outlined dense options-dense').style('min-width:240px')
        kart_gecmis = ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:420px;overflow-y:auto')
        ui.label('Elo değişimi: maçın takımın Elo puanına etkisi. Kaynak FotMob; resmî maçlar 2008\'den, hazırlık maçları '
                 '2026\'dan itibaren.').classes('cap')
    kd = {'takim': None}

    def takim_ac(t):
        E = d['E']
        if not E or t not in E.R:
            return
        kd['takim'] = t
        g = E.gecmis.get(t, [])
        sira = next((k for k, r in enumerate(E.siralama(), 1) if r['id'] == t), None)
        kart_ad.text = E.ad[t]
        kart_meta.text = (f'{len(g)} maç (2008\'den bu yana)' + (f' · son maç {tarih_uzun(g[-1]["zaman"][:10])}' if g else ''))
        kart_elo.content = (f'<div class="disp" style="font-size:2rem;font-weight:700;color:var(--pitch)">{round(E.R[t])}</div>'
                            f'<div class="cap">Elo{f" · {sira}. sırada" if sira else ""}</div>')
        sonuclar = [_sonuc(x['atilan'], x['yenilen']) for x in g]
        son4 = [x for x in g if x['zaman'][:4] >= str(datetime.now(timezone.utc).year - 4)]
        s4 = [_sonuc(x['atilan'], x['yenilen']) for x in son4]
        kart_ozet.content = (
            '<div class="tiles">' + ''.join(f'<div class="tile"><span class="num">{v}</span><small>{l}</small></div>' for l, v in (
                ('Maç', len(g)), ('Galibiyet', sonuclar.count('G')), ('Beraberlik', sonuclar.count('B')),
                ('Mağlubiyet', sonuclar.count('M')), ('Atılan', sum(x['atilan'] for x in g)), ('Yenilen', sum(x['yenilen'] for x in g))))
            + '</div>'
            + f'<div class="lead" style="margin-top:8px">Son 10 maç: <span class="form">{"".join(_rozet(s) for s in sonuclar[-10:])}</span>'
            + (f' · Son 4 yıl: {s4.count("G")}G {s4.count("B")}B {s4.count("M")}M' if s4 else '') + '</div>')
        kart_grafik.options['xAxis']['data'] = [x['zaman'][:10] for x in g]
        kart_grafik.options['series'][0]['data'] = [round(x['sonra']) for x in g]
        kart_grafik.update()
        kart_gelecek.clear()
        with kart_gelecek:
            gelecek = milli.gelecek_maclar(d['v'], t)[:8]
            if not gelecek:
                ui.label('Planlanmış maç yok.').classes('cap')
            for m in gelecek:
                mac_satiri(m, turnuva_adi=True)
        filtre = {'': 'Bütün turnuvalar', **{tid: milli.TURNUVA[tid][1] for tid in dict.fromkeys(x['tid'] for x in reversed(g))}}
        kart_filtre.set_options(filtre, value='')
        gecmis_ciz()
        kart.open()

    def gecmis_ciz(_=None):
        E, t = d['E'], kd['takim']
        if t is None:
            return
        g = [x for x in reversed(E.gecmis.get(t, [])) if not kart_filtre.value or x['tid'] == kart_filtre.value]
        satirlar = []
        for x in g:
            s = _sonuc(x['atilan'], x['yenilen'])
            fark = x['sonra'] - x['once']
            yer = 'tarafsız' if x['tarafsiz'] else ('ev' if x['ev'] else 'deplasman')
            satirlar.append(
                f'<tr><td>{x["zaman"][8:10]}.{x["zaman"][5:7]}.{x["zaman"][:4]}</td><td>{e(milli.TURNUVA[x["tid"]][1])}'
                f'{" · " + e(milli.grup_adi(x["tid"], x["grup"])) if x.get("grup") else ""}</td><td>{e(x["rakip_ad"])} <span class="cap">({yer})</span></td>'
                f'<td class="hi">{x["atilan"]}–{x["yenilen"]}</td><td><span class="form">{_rozet(s)}</span></td>'
                f'<td class="{"ok" if fark > 0.05 else "no" if fark < -0.05 else ""}">{"+" if fark > 0 else ""}{fmt(fark, 1)}</td></tr>')
        kart_gecmis.content = ('<table class="tb"><thead><tr><th>Tarih</th><th>Turnuva</th><th>Rakip</th><th>Skor</th><th></th>'
                               '<th>Elo</th></tr></thead><tbody>' + ''.join(satirlar) + '</tbody></table>'
                               if satirlar else '<p class="cap">Bu turnuvada maç yok.</p>')

    kart_filtre.on_value_change(gecmis_ciz)

    # ---------------------------------------------------------------- tahmin
    def tahmin_ciz(_=None):
        E = d['E']
        if not E or ev.value is None or dep.value is None:
            tahmin_kutu.content = ''
            return
        if ev.value == dep.value:
            tahmin_kutu.content = '<p class="cap">İki farklı takım seç.</p>'
            return
        t = E.tahmin(ev.value, dep.value, tarafsiz.value)
        p = t['p']
        ilk = t['skorlar'][0][2]
        tahmin_kutu.content = (
            f'<div class="bar" style="margin-top:6px"><div class="h" style="flex-basis:{p[0] * 100:.1f}%">{yuzde(p[0]) if p[0] > .1 else ""}</div>'
            f'<div class="d" style="flex-basis:{p[1] * 100:.1f}%">{yuzde(p[1]) if p[1] > .1 else ""}</div>'
            f'<div class="a" style="flex-basis:{p[2] * 100:.1f}%">{yuzde(p[2]) if p[2] > .1 else ""}</div></div>'
            f'<div class="lead" style="margin:8px 0">{e(E.ad[ev.value])} kazanır {yuzde(p[0])} · beraberlik {yuzde(p[1])} · '
            f'{e(E.ad[dep.value])} kazanır {yuzde(p[2])}<br>Beklenen gol: {e(E.ad[ev.value])} <b>{fmt(t["lh"])} – '
            f'{fmt(t["la"])}</b> {e(E.ad[dep.value])} · Elo: '
            f'{round(E.R[ev.value])} – {round(E.R[dep.value])}</div>'
            '<div class="liste">' + ''.join(
                f'<div class="satir"><span class="disp" style="font-size:1.1rem;font-weight:700">{i} – {j}</span>'
                f'<div class="track"><i style="width:{pr / ilk * 100:.0f}%"></i></div><span class="pv">{fmt(pr * 100, 1)}%</span></div>'
                for i, j, pr in t['skorlar']) + '</div>')

    for s in (ev, dep, tarafsiz):
        s.on_value_change(tahmin_ciz)

    def serbest_ayrinti():
        """Yandaki panelde seçilen iki takım için ayrıntılı tahmin (belli bir maça bağlı değil)."""
        E = d['E']
        if not E or ev.value is None or dep.value is None or ev.value == dep.value:
            ui.notify('Önce iki farklı takım seç.')
            return
        G.ayrintili_tahmin({'E': E, 'ev': ev.value, 'dep': dep.value, 'ev_ad': E.ad[ev.value], 'dep_ad': E.ad[dep.value],
                            'tarafsiz': tarafsiz.value, 'baslik': 'Serbest eşleşme', 'eleme': None, 'kulup': False})

    def _avantaj(m):
        """Turnuva finalinde mezban ülkenin maçı: +1 / -1; mezban yoksa ya da turnuva tarafsız değilse None (E.tahmin kendi karar verir)."""
        return milli.mezban_yonu(m['tid'], m['zaman'], m['ev'], m['dep'], m.get('sezon')) or None

    def mac_sec(m):
        if m['evId'] in ev.options and m['depId'] in dep.options:
            ev.set_value(m['evId'])
            dep.set_value(m['depId'])
            tarafsiz.set_value(milli.TURNUVA[m['tid']][3])

    def ayrintili(m):
        """Maçın ayrıntılı tahmin penceresi. Eleme maçı: grubu olmayan, adı sayı olmayan tur (Çeyrek final gibi)."""
        E, v = d['E'], d['v']
        if not E or m['evId'] not in E.R or m['depId'] not in E.R:
            ui.notify('Bu takımların Elo puanı yok (yeterli maç kaydı bulunmuyor).')
            return
        tur = milli.TURNUVA[m['tid']]
        eleme = tur[2] != 'hazirlik' and not m.get('grup') and isinstance(m.get('tur'), str) and not m['tur'].isdigit()
        ayni_tur = [(x['zaman'], x['evId'], x['depId'], x['skor']) for s in milli.sezonlar(v, m['tid'])[:2]
                    for x in milli.sezon_maclari(v, m['tid'], s) if x.get('tur') == m.get('tur') and not x.get('grup')]
        ek = milli.grup_adi(m['tid'], m.get('grup')) if m.get('grup') else TUR_ADI.get(m.get('tur'), m.get('tur') or '')
        G.ayrintili_tahmin({
            'E': E, 'ev': m['evId'], 'dep': m['depId'], 'ev_ad': m['ev'], 'dep_ad': m['dep'], 'tarafsiz': tur[3] and not _avantaj(m), 'avantaj': _avantaj(m),
            'baslik': ' · '.join(x for x in (tur[1], ek) if x), 'zaman': m['zaman'], 'turnuva_logo': lig_logo_url(m['tid']),
            'skor': m['skor'], 'eleme': mac_tahmini.eslesme_turu(ayni_tur, m['evId'], m['depId'], m['zaman'], eleme),
            'kulup': False})

    def mac_satiri(m, secilebilir=False, turnuva_adi=False):
        """Bir maç satırı: üstte tarih (ve grup), altında ev sahibi · skor ya da olasılıklar · deplasman.
        Olasılıklarda favori taraf yeşil, diğer taraf kırmızı, beraberlik açık gri. Takım adına tıklanınca kart açılır."""
        E = d['E']
        z = yerel(m['zaman'])
        zaman = f'{kisa_gun(z.date())} {z:%H:%M}' if z else ''
        ek = ' · '.join(x for x in (zaman, milli.TURNUVA[m['tid']][1] if turnuva_adi else '',
                                    milli.grup_adi(m['tid'], m.get('grup'))) if x)
        if m['skor'] is None and E and m['evId'] in E.R and m['depId'] in E.R:
            p = E.tahmin(m['evId'], m['depId'], milli.TURNUVA[m['tid']][3], _avantaj(m))['p']
            ev_sinif, dep_sinif = ('kaz', 'kay') if p[0] >= p[2] else ('kay', 'kaz')
            orta = (f'<div class="olas"><span class="{ev_sinif}" title="{e(m["ev"])} kazanır">{yuzde(p[0])}</span>'
                    f'<span class="ber" title="Beraberlik">{yuzde(p[1])}</span>'
                    f'<span class="{dep_sinif}" title="{e(m["dep"])} kazanır">{yuzde(p[2])}</span></div>')
        elif m['skor'] is None:
            orta = '<span class="cap">–</span>'
        else:
            orta = f'<b class="disp" style="font-size:1.2rem">{m["skor"][0]} – {m["skor"][1]}</b>'
        satir = ui.element('div').classes('mm secilebilir' + (' done' if m['skor'] else '')).tooltip('Ayrıntılı tahmin')
        # satıra tıklayınca ayrıntılı tahmin (ve sekmedeki listede yandaki tahmin de o maça geçer)
        satir.on('click', lambda _, m=m, s=secilebilir: (mac_sec(m) if s else None, ayrintili(m)))
        with satir:
            ui.label(ek).classes('st')
            ui.label(m['ev']).classes('h link').on('click.stop', lambda _, t=m['evId']: takim_ac(t))
            ui.html(orta, sanitize=False).classes('orta')
            ui.label(m['dep']).classes('a link').on('click.stop', lambda _, t=m['depId']: takim_ac(t))

    # ---------------------------------------------------------------- turnuva sezonu
    def sezon_ciz():
        v, tid, s = d['v'], d['tid'], d['sezon']
        gruplar = milli.sezon_gruplari(v, tid, s)
        grup_panel.set_visibility(bool(gruplar))
        turnuva_logo.content = f'<span class="turnuva-logo kucuk" style="background-image:url({lig_logo_url(tid)})"></span>'
        grup_baslik.content = (f'<div class="turnuva-baslik"><span class="turnuva-logo" style="background-image:url('
                               f'{lig_logo_url(tid)})"></span><h3>Gruplar</h3>'
                               f'<span class="cap">{e(milli.TURNUVA[tid][1])} · {e(s)}</span></div>')
        grup_izgara.clear()
        with grup_izgara:
            for ad, satirlar, lejant in gruplar:
                with ui.column().classes('gap-1'):
                    ui.label(milli.grup_adi(tid, ad) or ad).classes('disp').style('font-weight:700;font-size:1.1rem')
                    _tablo(['#', 'Takım', 'O', 'G', 'B', 'M', 'Gol', 'P'],
                           [(r['id'], [(str(k + 1), '', f'box-shadow:inset 3px 0 0 {r["renk"] or "transparent"}'),
                                       (e(r['ad']), 'link', ''), (str(r['O']), '', ''), (str(r['G']), '', ''),
                                       (str(r['B']), '', ''), (str(r['M']), '', ''), (e(r['gol']), '', ''),
                                       (str(r['P']), 'pts', '')])
                            for k, r in enumerate(satirlar)], takim_ac)
                    aciklama = list(lejant)
                    if any(not r['renk'] for r in satirlar) and lejant:
                        aciklama.append(('', 'Ligde kalır' if any('lige' in a for _, a in lejant) else 'Elenir'))
                    if aciklama:
                        ui.html('<div class="cap" style="line-height:1.5">' + '<br>'.join(
                            f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;'
                            f'background:{r or "transparent"};border:1px solid {r or "var(--line)"}"></span>{e(a)}'
                            for r, a in aciklama) + '</div>', sanitize=False)
        maclar = milli.sezon_maclari(v, tid, s)
        gelecek = [m for m in maclar if m['skor'] is None]
        oynanan = [m for m in maclar if m['skor'] is not None][::-1]
        mac_kutu.clear()
        with mac_kutu:
            for baslik, liste in (('Sıradaki maçlar', gelecek), ('Oynanan maçlar', oynanan)):
                if not liste:
                    continue
                ui.label(baslik).classes('disp text-lg font-bold').style('margin-top:6px')
                for m in liste:
                    mac_satiri(m, secilebilir=True)
            if not maclar:
                ui.label('Bu sezonun maç verisi yok.').classes('cap')
        if gelecek:
            mac_sec(gelecek[0])

    def sezonlari_doldur():
        secenek = milli.sezonlar(d['v'], d['tid'])
        d['sezon'] = secenek[0] if secenek else None
        sezon.set_options({s: s for s in secenek}, value=d['sezon'])

    def turnuva_degisti(ev_):
        d['tid'] = ev_.value
        app.storage.general['milli'] = {'tid': ev_.value}
        sezonlari_doldur()
        if d['sezon']:
            sezon_ciz()

    def sezon_degisti(ev_):
        if ev_.value and ev_.value != d['sezon']:
            d['sezon'] = ev_.value
            sezon_ciz()

    turnuva.on_value_change(turnuva_degisti)
    sezon.on_value_change(sezon_degisti)

    # ---------------------------------------------------------------- yükleme
    async def yenile():
        klasor = G.depo.veri_klasoru
        v = milli.oku(klasor)
        if v is None:
            durum.text = 'Milli takım verisi henüz yok; arka planda indiriliyor (ilk açılışta bir iki dakika sürer).'
            return
        if d['v'] is v:  # veri değişmedi
            return
        durum.text = 'Milli takım Elo\'su hesaplanıyor…'
        E = await run.io_bound(milli.elo, klasor)
        d['v'], d['E'] = v, E
        durum.text = f'{E.n_mac} milli maç · veri: {v["guncellendi"][:10]}'
        takimlar = {t: E.ad[t] for t in sorted(E.R, key=lambda t: tr_anahtar(E.ad[t]))}
        ev.set_options(takimlar)
        dep.set_options(dict(takimlar))
        sira = E.siralama()
        elo_not.text = (f'2008\'den bu yana {E.n_mac} resmi milli maçtan hesaplanır (World Football Elo yöntemi: maçın önemi, gol '
                        'farkı ve ev sahibi avantajı hesaba katılır). Son 4 yılda en az 8 maç yapmış takımlar listelenir; takımın '
                        'kartı için adına tıkla. Not: FotMob 2026 öncesi hazırlık maçlarını vermediği için konfederasyonlar '
                        'birbiriyle çoğunlukla yalnızca Dünya Kupası\'nda karşılaşır; kıtalar arası karşılaştırma bu yüzden kaba kalır.')
        siralama.clear()
        with siralama:
            _tablo(['#', 'Takım', 'Elo', 'Maç', 'Son maç'],
                   [(r['id'], [(str(k), '', ''), (e(r['ad']), 'link', ''), (str(round(r['elo'])), 'hi', ''),
                               (str(r['mac']), '', ''), (f'{r["son"][8:10]}.{r["son"][5:7]}.{r["son"][:4]}', '', '')])
                    for k, r in enumerate(sira, 1)], takim_ac)
        sezonlari_doldur()
        if d['sezon']:
            sezon_ciz()

    async def canli_mac_ac(tid, mac_id):
        """Canlı skordan (Maç tahmini düğmesi): sekmede o turnuvanın güncel sezonu seçilir, maçın ayrıntılı tahmini açılır."""
        if d['v'] is None:
            await yenile()
        if d['v'] is None:
            ui.notify('Milli takım verisi henüz hazır değil; birazdan yeniden dene.')
            return
        if d['tid'] != tid and tid in turnuva.options:
            turnuva.set_value(tid)  # turnuva_degisti: en yeni sezon seçilir ve çizilir
        m = next((x for s in milli.sezonlar(d['v'], tid)[:2] for x in milli.sezon_maclari(d['v'], tid, s)
                  if str(x['id']) == str(mac_id)), None)
        if m is None:
            ui.notify('Bu maç turnuvanın fikstüründe bulunamadı; sekmede maçlara bakabilirsin.')
            return
        ayrintili(m)
    G.milli_mac_ac = lambda tid, mac_id: G.arka_plan(canli_mac_ac(tid, mac_id))

    G.dinle('canli', lambda: G.arka_plan(yenile()) if d['v'] is not None else None)  # milli veri yenilendiyse
    return yenile
