"""Avrupa kupaları sekmesi: Şampiyonlar Ligi, Avrupa Ligi ve Konferans Ligi. Lig aşaması puan durumu (eski sezonlarda
gruplar), tur tur maçlar (oynanmamışlarda kulüp Elo'suna göre olasılıklar), gerçek eleme ağacı ve sezon sonu
simülasyonu: tur tur ilerleme ve şampiyonluk olasılıkları, olası finaller, seçilen takımın yolu (tur tur olası
rakipleri) ve örnek bir senaryonun eleme ağacı. Hesaplar avrupa.py'de."""
from nicegui import app, run, ui

from .. import avrupa
from ..logo import lig_logo_url, logo_html, takim_logo_url
from . import mac_tahmini
from .ortak import e, fmt, kisa_gun, takim_link, takim_tiklama, yerel, yuzde

ID, AD = 'avrupa', 'Kupalar'
TEMBEL = True  # kulüp Elo'su bütün lig ve kupa maçlarından hesaplanır: yalnızca sekme açıkken
VARSAYILAN = 42
SIM_N = 10000
TUR_KISA = ['Son 16', 'Çeyrek', 'Yarı', 'Final', 'Şampiyon']


def _logo(tid, sinif='logo'):
    return logo_html(takim_logo_url(tid) if tid else '', sinif)


def _olas(p):
    """Olasılık hücresi: değer ve olasılığa göre koyulaşan arka plan."""
    if p < 0.0005:
        return '<td class="sag cap">–</td>'
    metin = '<%1' if p < 0.01 else yuzde(p)
    return f'<td class="sag" style="background:rgba(47,122,87,{min(0.65, p * 0.75):.2f})">{metin}</td>'


def _tur_sirasi(t):
    return (0, int(t)) if str(t).isdigit() else (1, avrupa.GOSTERIM_TURLARI.index(t) if t in avrupa.GOSTERIM_TURLARI else 9)


def _agac_html(turlar, ad):
    """Eleme ağacı. turlar: {tur: [(ev, dep, ev toplam, dep toplam, kazanan, not)]} (kura sırasıyla)."""
    sutunlar = []
    for tur in avrupa.GOSTERIM_TURLARI:
        if tur not in turlar or len(turlar[tur]) > 16:  # ağaçta son 32'den sonrası (FA Cup gibi kupaların ilk turları çok kalabalık)
            continue
        kutular = []
        for ev, dep, ge, gd, kaz, not_ in turlar[tur]:
            satir = []
            for t, g in ((ev, ge), (dep, gd)):
                sinif = '' if kaz is None else (' kaz' if kaz == t else ' kay')
                satir.append(f'<div class="t{sinif}"><span class="ad">{_logo(t)}{takim_link(ad(t), t) if t else "Belli değil"}</span>'
                             f'<b>{"" if g is None else g}</b></div>')
            kutular.append('<div class="agac-mac">' + ''.join(satir) + (f'<div class="not">{e(not_)}</div>' if not_ else '') + '</div>')
        sutunlar.append(f'<div class="agac-tur"><div class="agac-baslik">{avrupa.TUR_ADI[tur]}</div>'
                        f'<div class="agac-kutular">{"".join(kutular)}</div></div>')
    return '<div class="agac">' + ''.join(sutunlar) + '</div>' if sutunlar else ''


def kur(G):
    hafiza = app.storage.general.get('avrupa', {})
    d = {'kid': hafiza.get('kid', VARSAYILAN), 'sezon': None, 'tur': None, 'v': None, 'E': None, 'sim': None}
    kupa_sec = {**{k: f'{ad} (Avrupa)' for k, ad in avrupa.KUPALAR}, **dict(avrupa.YEREL_KUPALAR)}

    with ui.row().classes('w-full items-end gap-3'):
        kupa = ui.select(kupa_sec, value=d['kid'] if d['kid'] in kupa_sec else VARSAYILAN, label='Kupa').props(
            'outlined dense options-dense').style('min-width:260px')
        with kupa.add_slot('prepend'):
            kupa_logo = ui.html('', sanitize=False)
        sezon = ui.select({}, label='Sezon').props('outlined dense options-dense').style('min-width:140px')
        durum = ui.label().classes('cap')

    with ui.column().classes('panel') as tablo_panel:
        tablo_baslik = ui.html('', sanitize=False)
        tablo_not = ui.label().classes('cap')
        tablo_kutu = ui.html('', sanitize=False).classes('w-full kaydir')

    with ui.column().classes('panel'):
        with ui.row().classes('w-full items-center'):
            ui.html('<h3>Maçlar</h3>', sanitize=False)
            ui.space()
            tur_sec = ui.select({}, label='Tur').props('outlined dense options-dense').style('min-width:220px')
        ui.label('Oynanmamış maçlarda olasılıklar (ev · beraberlik · deplasman) kulüp Elo\'suna göredir. Maça tıklayınca '
                 'ayrıntılı tahmin açılır (skor olasılıkları, goller, turu kim geçer, son maçlar, kim gol atar).').classes('cap')
        mac_kutu = ui.html('', sanitize=False).classes('w-full')

    with ui.column().classes('panel') as agac_panel:
        ui.html('<h3>Eleme ağacı</h3>', sanitize=False)
        ui.label('İki maçlı turlarda toplam skor (uzatma dahil); kalın yazılan turu geçen takım.').classes('cap')
        agac = ui.html('', sanitize=False).classes('w-full kaydir')

    with ui.column().classes('panel') as sim_panel:
        ui.html('<h3>Sezon sonu simülasyonu</h3>', sanitize=False)
        sim_not = ui.label().classes('lead')
        sim_tablo = ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:640px;overflow-y:auto')
        with ui.row().classes('w-full gap-4 items-start'):
            with ui.column().classes('gap-1').style('flex:1 1 300px'):
                ui.label('En olası finaller').classes('disp text-lg font-bold')
                finaller = ui.html('', sanitize=False).classes('w-full')
            with ui.column().classes('gap-1').style('flex:2 1 420px'):
                with ui.row().classes('w-full items-center'):
                    ui.label('Takımın yolu').classes('disp text-lg font-bold')
                    ui.space()
                    yol_sec = ui.select({}, label='Takım', with_input=True).props('outlined dense options-dense').style('min-width:240px')
                yol = ui.html('', sanitize=False).classes('w-full')
        with ui.row().classes('w-full items-center'):
            ui.label('Örnek senaryo').classes('disp text-lg font-bold')
            ui.space()
            ui.button('Başka bir senaryo', icon='casino', on_click=lambda: G.arka_plan(ornek_yenile())).props('flat dense no-caps')
        ui.label('Simülasyonlardan biri baştan sona: lig aşamasının sonucu ve eleme turlarında kimin kimle eşleşip kimin '
                 'kazandığı. Her tıklamada yeni bir senaryo.').classes('cap')
        ornek_lig = ui.html('', sanitize=False).classes('w-full')
        ornek_agac = ui.html('', sanitize=False).classes('w-full kaydir')

    for oge in (tablo_kutu, mac_kutu, agac, sim_tablo, finaller, yol, ornek_agac):
        takim_tiklama(oge, G)  # takım adına tıklanınca takım sayfası

    def ad(t):
        E = d['E']
        return (E.ad.get(t) if E else None) or str(t)

    # ---------------------------------------------------------------- puan durumu
    def tablo_ciz(S):
        E = d['E']
        kid, s = d['kid'], d['sezon']
        tablo_baslik.content = (f'<div class="turnuva-baslik"><span class="turnuva-logo" style="background-image:url('
                                f'{lig_logo_url(kid)})"></span><h3>Puan durumu</h3><span class="cap">{e(kupa_sec[kid])} · {e(s)}</span></div>')
        lig = avrupa.lig_asamasi(S)
        parca = []
        for grup, satirlar in S['tablo']:
            renk = (lambda k: 'var(--pitch-2)' if k < 8 else 'var(--away)' if k < 24 else 'transparent') if lig else \
                   (lambda k: 'var(--pitch-2)' if k < 2 else 'var(--lamp)' if k == 2 else 'transparent')
            govde = ''.join(
                f'<tr><td style="box-shadow:inset 3px 0 0 {renk(k)}">{k + 1}</td><td>{_logo(r[0])} {takim_link(ad(r[0]) if E else r[1], r[0])}</td>'
                f'<td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td><td>{e(r[6])}</td><td>{"+" if r[7] > 0 else ""}{r[7]}</td>'
                f'<td class="pts">{r[8]}</td>' + (f'<td class="cap">{round(E.puan(r[0])) if E else ""}</td>' if lig else '') + '</tr>'
                for k, r in enumerate(satirlar))
            parca.append((f'<div><div class="disp" style="font-weight:700;font-size:1.05rem">{e(grup)} Grubu</div>' if grup else '<div>')
                         + '<table class="tb avrupa-tablo"><thead><tr><th>#</th><th>Takım</th><th>O</th><th>G</th><th>B</th><th>M</th>'
                           '<th>Gol</th><th>Av</th><th>P</th>' + ('<th>Elo</th>' if lig else '') + '</tr></thead><tbody>'
                         + govde + '</tbody></table></div>')
        if lig:
            tablo_kutu.content = parca[0]
            tablo_not.text = ('Yeşil: son 16\'ya doğrudan kalır (1-8). Mavi: play-off turu oynar (9-24). Renksiz: elenir. '
                              'Elo: takımın kulüp Elo puanı (güç ölçüsü).')
        else:
            tablo_kutu.content = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px">' + ''.join(parca) + '</div>'
            tablo_not.text = ('Grup aşaması. Renkler: kaynakta gruptan çıkan sıralar.' if kid in avrupa.YEREL else
                              'Eski biçim (2024/25 öncesi): 4\'er takımlı gruplar. Yeşil: üst tura çıkar; sarı: alt kupaya geçer.')
        tablo_panel.set_visibility(bool(S['tablo']))

    # ---------------------------------------------------------------- maçlar
    def maclari_ciz(_=None):
        S, E = avrupa.sezon(d['v'], d['kid'], d['sezon']), d['E']
        tur = tur_sec.value
        satirlar = []
        for r in S['maclar']:
            if r[8] != tur:
                continue
            z = yerel(r[1])
            ust = f'{kisa_gun(z.date())} {z:%H:%M}' if z else ''
            if r[6] is not None:
                orta = f'<b class="disp" style="font-size:1.2rem">{r[6]} – {r[7]}</b>' + (' <span class="cap">(pen.)</span>' if r[10] else '')
            elif E:
                p = E.tahmin(r[2], r[3], tarafsiz=r[8] == 'final')['p']
                ev_s, dep_s = ('kaz', 'kay') if p[0] >= p[2] else ('kay', 'kaz')
                orta = (f'<div class="olas"><span class="{ev_s}" title="{e(ad(r[2]))} kazanır">{yuzde(p[0])}</span>'
                        f'<span class="ber" title="Beraberlik">{yuzde(p[1])}</span>'
                        f'<span class="{dep_s}" title="{e(ad(r[3]))} kazanır">{yuzde(p[2])}</span></div>')
            else:
                orta = '<span class="cap">–</span>'
            if r[9]:
                ust = '<span class="durum canli"><i class="nabiz"></i>Canlı</span> ' + ust
            uyari = [x for x in (E.belirsizlik(r[2], ad(r[2])), E.belirsizlik(r[3], ad(r[3]))) if x] if E and r[6] is None else []
            if uyari:  # model takımlardan birini az tanıyor: olasılıklar daha belirsiz
                ust += f' <span class="belirsiz" title="{e(" ".join(uyari))}">⚠ belirsiz</span>'
            satirlar.append(f'<div class="mm secilebilir{" done" if r[6] is not None else ""}" data-mac="{e(r[0])}" '
                            f'title="Ayrıntılı tahmin"><div class="st">{ust}</div>'
                            f'<div class="h">{takim_link(ad(r[2]), r[2])} {_logo(r[2])}</div><div class="orta">{orta}</div>'
                            f'<div class="a">{_logo(r[3])} {takim_link(ad(r[3]), r[3])}</div></div>')
        mac_kutu.content = ''.join(satirlar) or '<p class="cap">Bu turda maç yok.</p>'

    tur_sec.on_value_change(maclari_ciz)

    def mac_tiklandi(ev_):
        """Maç satırına tıklanınca ayrıntılı tahmin penceresi (takım adına tıklama takım sayfasını açar)."""
        ayrinti_ac(ev_.args)

    async def canli_mac_ac(kid, mac_id):
        """Canlı skordan (Maç tahmini düğmesi): sekmede o kupanın güncel sezonu seçilir, maçın ayrıntılı tahmini açılır."""
        if d['v'] is None:
            await yenile()
        if d['v'] is None:
            ui.notify('Kupa verisi henüz hazır değil; birazdan yeniden dene.')
            return
        if d['kid'] != kid and kid in kupa.options:
            kupa.set_value(kid)  # kupa_degisti: en yeni sezon seçilir ve çizilir
        elif d['sezon'] != (avrupa.sezonlar(d['v'], kid) or [None])[0]:
            sezonlari_doldur()
            sezon_ciz()
        if not ayrinti_ac(mac_id):
            ui.notify('Bu maç kupanın fikstüründe bulunamadı (eleme turu olabilir); sekmede maçlara bakabilirsin.')
    G.avrupa_mac_ac = lambda kid, mac_id: G.arka_plan(canli_mac_ac(kid, mac_id))

    def ayrinti_ac(mac_id):
        S, E = avrupa.sezon(d['v'], d['kid'], d['sezon']), d['E']
        r = next((x for x in S['maclar'] if str(x[0]) == str(mac_id)), None) if S and E else None
        if r is None:
            return False
        # yerel kupalarda her tur eleme; Avrupa kupalarında sayıyla adlanan turlar lig / grup aşaması
        eleme = d['kid'] in avrupa.YEREL or not r[8].isdigit()
        ayni_tur = [(x[1], x[2], x[3], (x[6], x[7]) if x[6] is not None else None) for x in S['maclar'] if x[8] == r[8]]
        G.ayrintili_tahmin({
            'E': E, 'ev': r[2], 'dep': r[3], 'ev_ad': ad(r[2]), 'dep_ad': ad(r[3]), 'tarafsiz': r[8] == 'final',
            'baslik': f'{avrupa.KUPA[d["kid"]]} · {avrupa.tur_adi(r[8], d["kid"] in avrupa.YEREL)}', 'zaman': r[1],
            'turnuva_logo': lig_logo_url(d['kid']), 'skor': (r[6], r[7]) if r[6] is not None else None,
            'eleme': mac_tahmini.eslesme_turu(ayni_tur, r[2], r[3], r[1], eleme),
            # kim gol atar: güncel kadrolardan hesaplandığı için yalnızca kupanın en son sezonunda
            'kulup': True, 'golcu': d['sezon'] == avrupa.sezonlar(d['v'], d['kid'])[0]})
        return True

    mac_kutu.on('click', mac_tiklandi, js_handler='(e) => { if (e.target.closest("[data-takim]")) return; '
                'const t = e.target.closest("[data-mac]"); if (t) emit(t.dataset.mac); }')

    # ---------------------------------------------------------------- gerçek eleme ağacı
    def agac_ciz(S):
        turlar = {}
        for tur, _, ev, dep, kaz, ayaklar in sorted(S['eleme'], key=lambda x: (x[0], x[1])):
            ge = gd = None
            for _, h, a, hg, ag in ayaklar:
                if hg is None:
                    continue
                ge = (ge or 0) + (hg if h == ev else ag)
                gd = (gd or 0) + (ag if h == ev else hg)
            # toplam skor eşitken turu geçen belliyse penaltılarla geçmiştir (FotMob skoru uzatmayı içerir)
            turlar.setdefault(tur, []).append((ev, dep, ge, gd, kaz, 'pen.' if kaz and ge is not None and ge == gd else ''))
        agac.content = _agac_html(turlar, ad)
        # kura çekilmeden (hiçbir eşleşmenin takımı belli değilken) ağaç gösterilmez: yalnızca "Belli değil" satırları olurdu
        agac_panel.set_visibility(any(ev is not None or dep is not None for ms in turlar.values() for ev, dep, *_ in ms))

    # ---------------------------------------------------------------- simülasyon
    def sim_ciz():
        sim = d['sim']
        T = sim['takimlar']
        sira = sorted(T, key=lambda r: (-r['turlar'][4], -r['turlar'][3], -r['ilk8'], r['sira']))
        sim_not.text = (f'Kalan {sim["kalan_mac"]} lig aşaması maçı ve bütün eleme turları {sim["N"]:,} kez oynatıldı'.replace(',', '.')
                        + ' (kulüp Elo\'su ve Poisson gol modeli; eleme turları iki maçlı, eşitlikte uzatma ve penaltı, final '
                          'tarafsız sahada). Kura UEFA\'nın sabit ağacına göre çekilir; gerçekleşen kura ve maçlar olduğu gibi '
                          'kullanılır. Sütunlar, takımın o tura kalma olasılığıdır.')
        govde = ''.join(
            f'<tr><td>{_logo(r["id"])} {takim_link(r["ad"], r["id"])}</td><td class="sag cap">{round(r["elo"])}</td>'
            f'<td class="sag">{fmt(r["puan"], 1)}</td><td class="sag">{fmt(r["sira"], 1)}</td>'
            + _olas(r['ilk8']) + _olas(r['playoff']) + _olas(r['elendi']) + ''.join(_olas(p) for p in r['turlar']) + '</tr>'
            for r in sira)
        sim_tablo.content = ('<table class="tb kiyas-tablo"><thead><tr><th>Takım</th><th class="sag">Elo</th><th class="sag">Ort. puan</th>'
                             '<th class="sag">Ort. sıra</th><th class="sag">İlk 8</th><th class="sag">Play-off</th><th class="sag">Elenir</th>'
                             + ''.join(f'<th class="sag">{x}</th>' for x in TUR_KISA) + '</tr></thead><tbody>' + govde + '</tbody></table>')
        finaller.content = '<div class="liste">' + ''.join(
            f'<div class="satir"><span>{_logo(a)} {takim_link(ad(a), a)} – {_logo(b)} {takim_link(ad(b), b)}</span>'
            f'<div class="track"><i style="width:{p / sim["finaller"][0][1] * 100:.0f}%"></i></div><span class="pv">{yuzde(p)}</span></div>'
            for (a, b), p in sim['finaller'][:6]) + '</div>'
        secenek = {r['id']: r['ad'] for r in sira}
        deger = yol_sec.value if yol_sec.value in secenek else sira[0]['id']
        yol_sec.set_options(secenek, value=deger)
        yol_ciz()
        ornek_ciz(sim)

    def yol_ciz(_=None):
        sim, t = d['sim'], yol_sec.value
        if not sim or t not in sim['sira_ix']:
            return
        i = sim['sira_ix'][t]
        r = sim['takimlar'][i]
        ulasma = {'playoff': r['playoff'], '1/8': r['turlar'][0], '1/4': r['turlar'][1], '1/2': r['turlar'][2], 'final': r['turlar'][3]}
        satirlar = [f'<div class="lead">Lig aşaması: ortalama {fmt(r["puan"], 1)} puan, {fmt(r["sira"], 1)}. sıra · ilk 8 {yuzde(r["ilk8"])}'
                    f' · play-off {yuzde(r["playoff"])} · elenme {yuzde(r["elendi"])}</div>']
        for tur in avrupa.ELEME_TURLARI:
            p = ulasma[tur]
            if p < 0.001:
                continue
            ihtimal = sim['rakip'][tur][i]
            en = sorted(((u, ihtimal[u] / p) for u in range(len(ihtimal)) if ihtimal[u] > 0), key=lambda x: -x[1])[:4]
            rakipler = ', '.join(f'{_logo(sim["takimlar"][u]["id"])} {e(sim["takimlar"][u]["ad"])} <span class="cap">{yuzde(q)}</span>'
                                 for u, q in en)
            satirlar.append(f'<div class="yol-tur"><b>{avrupa.TUR_ADI[tur]}</b> <span class="cap">(oynama olasılığı {yuzde(p)})</span>'
                            f'<div>Olası rakipler: {rakipler}</div></div>')
        satirlar.append(f'<div class="yol-tur"><b>Şampiyonluk</b>: {yuzde(r["turlar"][4])}</div>')
        yol.content = ''.join(satirlar) + ('<p class="cap">Rakip yüzdeleri, takım o tura kaldığında karşısına o takımın çıkma '
                                           'olasılığıdır.</p>')

    yol_sec.on_value_change(yol_ciz)

    def ornek_ciz(sim):
        s = sim['ornek_sira']
        ornek_lig.content = (f'<div class="lead"><b>Lig aşaması</b> · ilk 8: {", ".join(e(ad(t)) for t in s[:8])}<br>'
                             f'<span class="cap">Play-off (9-24): {", ".join(e(ad(t)) for t in s[8:24])}</span></div>')
        turlar = {}
        for tur, a, b, ga, gb, k, not_ in sim['ornek']:
            turlar.setdefault(tur, []).append((a, b, ga, gb, k, not_))
        sampiyon = sim['ornek'][-1][5]
        ornek_agac.content = _agac_html(turlar, ad) + f'<div class="lead" style="margin-top:6px">Şampiyon: <b>{_logo(sampiyon)} {e(ad(sampiyon))}</b></div>'

    async def ornek_yenile():
        if not d['E']:
            return
        sim = await run.io_bound(avrupa.simulasyon, d['v'], d['E'], d['kid'], d['sezon'], 1)
        if sim:
            ornek_ciz(sim)

    async def sim_calistir():
        kid, s = d['kid'], d['sezon']
        sim_panel.set_visibility(False)
        if s != avrupa.sezonlar(d['v'], kid)[0] or not avrupa.lig_asamasi(avrupa.sezon(d['v'], kid, s)):
            return  # simülasyon yalnızca süren (yeni biçimli) sezon için
        sim = await run.io_bound(avrupa.simulasyon, d['v'], d['E'], kid, s, SIM_N)
        if (kid, s) != (d['kid'], d['sezon']) or not sim:
            return
        d['sim'] = sim
        sim_panel.set_visibility(True)
        sim_ciz()

    # ---------------------------------------------------------------- seçim
    def sezon_ciz():
        S = avrupa.sezon(d['v'], d['kid'], d['sezon'])
        kupa_logo.content = f'<span class="turnuva-logo kucuk" style="background-image:url({lig_logo_url(d["kid"])})"></span>'
        tablo_ciz(S)
        turlar = sorted({r[8] for r in S['maclar']}, key=_tur_sirasi)
        secenek = {t: avrupa.tur_adi(t, d['kid'] in avrupa.YEREL) for t in turlar}
        siradaki = next((r[8] for r in S['maclar'] if r[6] is None), turlar[-1] if turlar else None)
        tur_sec.set_options(secenek, value=siradaki)
        maclari_ciz()
        agac_ciz(S)
        G.arka_plan(sim_calistir())

    def sezonlari_doldur():
        secenek = avrupa.sezonlar(d['v'], d['kid'])
        d['sezon'] = secenek[0] if secenek else None
        sezon.set_options({s: s for s in secenek}, value=d['sezon'])

    def kupa_degisti(ev_):
        d['kid'] = ev_.value
        app.storage.general['avrupa'] = {'kid': ev_.value}
        sezonlari_doldur()
        if d['sezon']:
            sezon_ciz()

    def sezon_degisti(ev_):
        if ev_.value and ev_.value != d['sezon']:
            d['sezon'] = ev_.value
            sezon_ciz()

    kupa.on_value_change(kupa_degisti)
    sezon.on_value_change(sezon_degisti)

    async def yenile():
        klasor = G.depo.veri_klasoru
        v = avrupa.oku(klasor)
        if v is None:
            durum.text = 'Avrupa kupaları verisi henüz yok; arka planda indiriliyor (ilk açılışta bir iki dakika sürer).'
            return
        if d['v'] is v:
            return
        durum.text = 'Kulüp Elo\'su hesaplanıyor…'
        E = await run.io_bound(avrupa.elo, klasor)
        d['v'], d['E'] = v, E
        durum.text = f'{E.n_mac:,} maçtan kulüp Elo\'su · veri: {v["guncellendi"][:10]}'.replace(',', '.')
        sezonlari_doldur()
        if d['sezon']:
            sezon_ciz()

    G.dinle('canli', lambda: G.arka_plan(yenile()) if d['v'] is not None else None)  # kupa verisi yenilendiyse
    return yenile
