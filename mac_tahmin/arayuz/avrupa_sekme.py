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


# ---------------------------------------------------------------- saf HTML üreticiler (arayüz öğesine dokunmaz)
def _tablo_govdesi(satirlar, lig, E, ad, renk):
    return ''.join(
        f'<tr><td style="box-shadow:inset 3px 0 0 {renk(k)}">{k + 1}</td><td>{_logo(r[0])} {takim_link(ad(r[0]) if E else r[1], r[0])}</td>'
        f'<td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td><td>{e(r[6])}</td><td>{"+" if r[7] > 0 else ""}{r[7]}</td>'
        f'<td class="pts">{r[8]}</td>' + (f'<td class="cap">{round(E.puan(r[0])) if E else ""}</td>' if lig else '') + '</tr>'
        for k, r in enumerate(satirlar))


def _puan_durumu_html(S, E, kid, ad):
    """(puan durumu HTML'i, altındaki not): lig aşaması tek tablo, eski biçimde ve yerel kupalarda gruplar."""
    lig = avrupa.lig_asamasi(S)
    parca = []
    for grup, satirlar in S['tablo']:
        renk = (lambda k: 'var(--pitch-2)' if k < 8 else 'var(--away)' if k < 24 else 'transparent') if lig else \
               (lambda k: 'var(--pitch-2)' if k < 2 else 'var(--lamp)' if k == 2 else 'transparent')
        govde = _tablo_govdesi(satirlar, lig, E, ad, renk)
        parca.append((f'<div><div class="disp" style="font-weight:700;font-size:1.05rem">{e(grup)} Grubu</div>' if grup else '<div>')
                     + '<table class="tb avrupa-tablo"><thead><tr><th>#</th><th>Takım</th><th>O</th><th>G</th><th>B</th><th>M</th>'
                       '<th>Gol</th><th>Av</th><th>P</th>' + ('<th>Elo</th>' if lig else '') + '</tr></thead><tbody>'
                     + govde + '</tbody></table></div>')
    if lig:
        return parca[0], ('Yeşil: son 16\'ya doğrudan kalır (1-8). Mavi: play-off turu oynar (9-24). Renksiz: elenir. '
                          'Elo: takımın kulüp Elo puanı (güç ölçüsü).')
    return ('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px">' + ''.join(parca) + '</div>',
            'Grup aşaması. Renkler: kaynakta gruptan çıkan sıralar.' if kid in avrupa.YEREL else
            'Eski biçim (2024/25 öncesi): 4\'er takımlı gruplar. Yeşil: üst tura çıkar; sarı: alt kupaya geçer.')


def _mac_satiri_html(r, E, ad):
    """Bir maç satırı. r: sezon['maclar'] satırı (id, zaman, ev, dep, …, ev golü, dep golü, tur, canlı, penaltı)."""
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
    return (f'<div class="mm secilebilir{" done" if r[6] is not None else ""}" data-mac="{e(r[0])}" '
            f'title="Ayrıntılı tahmin"><div class="st">{ust}</div>'
            f'<div class="h">{takim_link(ad(r[2]), r[2])} {_logo(r[2])}</div><div class="orta">{orta}</div>'
            f'<div class="a">{_logo(r[3])} {takim_link(ad(r[3]), r[3])}</div></div>')


def _agac_turlari(S):
    """Gerçek eleme ağacının turları: {tur: [(ev, dep, ev toplam, dep toplam, kazanan, not)]}."""
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
    return turlar


def _sim_notu(sim):
    return (f'Kalan {sim["kalan_mac"]} lig aşaması maçı ve bütün eleme turları {sim["N"]:,} kez oynatıldı'.replace(',', '.')
            + ' (kulüp Elo\'su ve Poisson gol modeli; eleme turları iki maçlı, eşitlikte uzatma ve penaltı, final '
              'tarafsız sahada). Kura UEFA\'nın sabit ağacına göre çekilir; gerçekleşen kura ve maçlar olduğu gibi '
              'kullanılır. Sütunlar, takımın o tura kalma olasılığıdır.')


def _sim_tablo_html(sira):
    govde = ''.join(
        f'<tr><td>{_logo(r["id"])} {takim_link(r["ad"], r["id"])}</td><td class="sag cap">{round(r["elo"])}</td>'
        f'<td class="sag">{fmt(r["puan"], 1)}</td><td class="sag">{fmt(r["sira"], 1)}</td>'
        + _olas(r['ilk8']) + _olas(r['playoff']) + _olas(r['elendi']) + ''.join(_olas(p) for p in r['turlar']) + '</tr>'
        for r in sira)
    return ('<table class="tb kiyas-tablo"><thead><tr><th>Takım</th><th class="sag">Elo</th><th class="sag">Ort. puan</th>'
            '<th class="sag">Ort. sıra</th><th class="sag">İlk 8</th><th class="sag">Play-off</th><th class="sag">Elenir</th>'
            + ''.join(f'<th class="sag">{x}</th>' for x in TUR_KISA) + '</tr></thead><tbody>' + govde + '</tbody></table>')


def _finaller_html(sim, ad):
    return '<div class="liste">' + ''.join(
        f'<div class="satir"><span>{_logo(a)} {takim_link(ad(a), a)} – {_logo(b)} {takim_link(ad(b), b)}</span>'
        f'<div class="track"><i style="width:{p / sim["finaller"][0][1] * 100:.0f}%"></i></div><span class="pv">{yuzde(p)}</span></div>'
        for (a, b), p in sim['finaller'][:6]) + '</div>'


def _yol_html(sim, t):
    """Seçilen takımın yolu: tur tur olası rakipleri."""
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
    return ''.join(satirlar) + ('<p class="cap">Rakip yüzdeleri, takım o tura kaldığında karşısına o takımın çıkma '
                                'olasılığıdır.</p>')


class _Avrupa:
    """Avrupa kupaları sekmesi: öğeler özniteliklerde; yenile() sekme yenilenince ve kupa verisi değişince çağrılır."""

    def __init__(self, G):
        self.G = G
        hafiza = app.storage.general.get('avrupa', {})
        self.d = {'kid': hafiza.get('kid', VARSAYILAN), 'sezon': None, 'tur': None, 'v': None, 'E': None, 'sim': None}
        self.kupa_sec = {**{k: f'{ad} (Avrupa)' for k, ad in avrupa.KUPALAR}, **dict(avrupa.YEREL_KUPALAR)}
        self._iskelet_ust()
        self._iskelet_sim()
        for oge in (self.tablo_kutu, self.mac_kutu, self.agac, self.sim_tablo, self.finaller, self.yol, self.ornek_agac):
            takim_tiklama(oge, G)  # takım adına tıklanınca takım sayfası
        self.tur_sec.on_value_change(self.maclari_ciz)
        self.mac_kutu.on('click', self.mac_tiklandi, js_handler='(e) => { if (e.target.closest("[data-takim]")) return; '
                         'const t = e.target.closest("[data-mac]"); if (t) emit(t.dataset.mac); }')
        G.avrupa_mac_ac = lambda kid, mac_id: G.arka_plan(self.canli_mac_ac(kid, mac_id))
        self.yol_sec.on_value_change(self.yol_ciz)
        self.kupa.on_value_change(self.kupa_degisti)
        self.sezon.on_value_change(self.sezon_degisti)
        G.dinle('canli', lambda: G.arka_plan(self.yenile()) if self.d['v'] is not None else None)  # kupa verisi yenilendiyse

    # ---------------------------------------------------------------- arayüz iskeleti
    def _iskelet_ust(self):
        d = self.d
        with ui.row().classes('w-full items-end gap-3'):
            self.kupa = ui.select(self.kupa_sec, value=d['kid'] if d['kid'] in self.kupa_sec else VARSAYILAN, label='Kupa').props(
                'outlined dense options-dense').style('min-width:260px')
            with self.kupa.add_slot('prepend'):
                self.kupa_logo = ui.html('', sanitize=False)
            self.sezon = ui.select({}, label='Sezon').props('outlined dense options-dense').style('min-width:140px')
            self.durum = ui.label().classes('cap')

        with ui.column().classes('panel') as self.tablo_panel:
            self.tablo_baslik = ui.html('', sanitize=False)
            self.tablo_not = ui.label().classes('cap')
            self.tablo_kutu = ui.html('', sanitize=False).classes('w-full kaydir')

        with ui.column().classes('panel'):
            with ui.row().classes('w-full items-center'):
                ui.html('<h3>Maçlar</h3>', sanitize=False)
                ui.space()
                self.tur_sec = ui.select({}, label='Tur').props('outlined dense options-dense').style('min-width:220px')
            ui.label('Oynanmamış maçlarda olasılıklar (ev · beraberlik · deplasman) kulüp Elo\'suna göredir. Maça tıklayınca '
                     'ayrıntılı tahmin açılır (skor olasılıkları, goller, turu kim geçer, son maçlar, kim gol atar).').classes('cap')
            self.mac_kutu = ui.html('', sanitize=False).classes('w-full')

        with ui.column().classes('panel') as self.agac_panel:
            ui.html('<h3>Eleme ağacı</h3>', sanitize=False)
            ui.label('İki maçlı turlarda toplam skor (uzatma dahil); kalın yazılan turu geçen takım.').classes('cap')
            self.agac = ui.html('', sanitize=False).classes('w-full kaydir')

    def _iskelet_sim(self):
        with ui.column().classes('panel') as self.sim_panel:
            ui.html('<h3>Sezon sonu simülasyonu</h3>', sanitize=False)
            self.sim_not = ui.label().classes('lead')
            self.sim_tablo = ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:640px;overflow-y:auto')
            with ui.row().classes('w-full gap-4 items-start'):
                with ui.column().classes('gap-1').style('flex:1 1 300px'):
                    ui.label('En olası finaller').classes('disp text-lg font-bold')
                    self.finaller = ui.html('', sanitize=False).classes('w-full')
                with ui.column().classes('gap-1').style('flex:2 1 420px'):
                    with ui.row().classes('w-full items-center'):
                        ui.label('Takımın yolu').classes('disp text-lg font-bold')
                        ui.space()
                        self.yol_sec = ui.select({}, label='Takım', with_input=True).props('outlined dense options-dense').style(
                            'min-width:240px')
                    self.yol = ui.html('', sanitize=False).classes('w-full')
            with ui.row().classes('w-full items-center'):
                ui.label('Örnek senaryo').classes('disp text-lg font-bold')
                ui.space()
                ui.button('Başka bir senaryo', icon='casino', on_click=lambda: self.G.arka_plan(self.ornek_yenile())).props(
                    'flat dense no-caps')
            ui.label('Simülasyonlardan biri baştan sona: lig aşamasının sonucu ve eleme turlarında kimin kimle eşleşip kimin '
                     'kazandığı. Her tıklamada yeni bir senaryo.').classes('cap')
            self.ornek_lig = ui.html('', sanitize=False).classes('w-full')
            self.ornek_agac = ui.html('', sanitize=False).classes('w-full kaydir')

    def ad(self, t):
        E = self.d['E']
        return (E.ad.get(t) if E else None) or str(t)

    # ---------------------------------------------------------------- puan durumu, maçlar, ağaç
    def tablo_ciz(self, S):
        E, d = self.d['E'], self.d
        kid, s = d['kid'], d['sezon']
        self.tablo_baslik.content = (f'<div class="turnuva-baslik"><span class="turnuva-logo" style="background-image:url('
                                     f'{lig_logo_url(kid)})"></span><h3>Puan durumu</h3><span class="cap">{e(self.kupa_sec[kid])} · {e(s)}</span></div>')
        self.tablo_kutu.content, self.tablo_not.text = _puan_durumu_html(S, E, kid, self.ad)
        self.tablo_panel.set_visibility(bool(S['tablo']))

    def maclari_ciz(self, _=None):
        d = self.d
        S, E = avrupa.sezon(d['v'], d['kid'], d['sezon']), d['E']
        tur = self.tur_sec.value
        satirlar = [_mac_satiri_html(r, E, self.ad) for r in S['maclar'] if r[8] == tur]
        self.mac_kutu.content = ''.join(satirlar) or '<p class="cap">Bu turda maç yok.</p>'

    def mac_tiklandi(self, ev_):
        """Maç satırına tıklanınca ayrıntılı tahmin penceresi (takım adına tıklama takım sayfasını açar)."""
        self.ayrinti_ac(ev_.args)

    async def canli_mac_ac(self, kid, mac_id):
        """Canlı skordan (Maç tahmini düğmesi): sekmede o kupanın güncel sezonu seçilir, maçın ayrıntılı tahmini açılır."""
        d = self.d
        if d['v'] is None:
            await self.yenile()
        if d['v'] is None:
            ui.notify('Kupa verisi henüz hazır değil; birazdan yeniden dene.')
            return
        if d['kid'] != kid and kid in self.kupa.options:
            self.kupa.set_value(kid)  # kupa_degisti: en yeni sezon seçilir ve çizilir
        elif d['sezon'] != (avrupa.sezonlar(d['v'], kid) or [None])[0]:
            self.sezonlari_doldur()
            self.sezon_ciz()
        if not self.ayrinti_ac(mac_id):
            ui.notify('Bu maç kupanın fikstüründe bulunamadı (eleme turu olabilir); sekmede maçlara bakabilirsin.')

    def ayrinti_ac(self, mac_id):
        d, ad = self.d, self.ad
        S, E = avrupa.sezon(d['v'], d['kid'], d['sezon']), d['E']
        r = next((x for x in S['maclar'] if str(x[0]) == str(mac_id)), None) if S and E else None
        if r is None:
            return False
        # yerel kupalarda her tur eleme; Avrupa kupalarında sayıyla adlanan turlar lig / grup aşaması
        eleme = d['kid'] in avrupa.YEREL or not r[8].isdigit()
        ayni_tur = [(x[1], x[2], x[3], (x[6], x[7]) if x[6] is not None else None) for x in S['maclar'] if x[8] == r[8]]
        self.G.ayrintili_tahmin({
            'E': E, 'ev': r[2], 'dep': r[3], 'ev_ad': ad(r[2]), 'dep_ad': ad(r[3]), 'tarafsiz': r[8] == 'final',
            'baslik': f'{avrupa.KUPA[d["kid"]]} · {avrupa.tur_adi(r[8], d["kid"] in avrupa.YEREL)}', 'zaman': r[1],
            'turnuva_logo': lig_logo_url(d['kid']), 'skor': (r[6], r[7]) if r[6] is not None else None,
            'eleme': mac_tahmini.eslesme_turu(ayni_tur, r[2], r[3], r[1], eleme),
            # kim gol atar: güncel kadrolardan hesaplandığı için yalnızca kupanın en son sezonunda
            'kulup': True, 'golcu': d['sezon'] == avrupa.sezonlar(d['v'], d['kid'])[0]})
        return True

    def agac_ciz(self, S):
        turlar = _agac_turlari(S)
        self.agac.content = _agac_html(turlar, self.ad)
        # kura çekilmeden (hiçbir eşleşmenin takımı belli değilken) ağaç gösterilmez: yalnızca "Belli değil" satırları olurdu
        self.agac_panel.set_visibility(any(ev is not None or dep is not None for ms in turlar.values() for ev, dep, *_ in ms))

    # ---------------------------------------------------------------- simülasyon
    def sim_ciz(self):
        sim = self.d['sim']
        T = sim['takimlar']
        sira = sorted(T, key=lambda r: (-r['turlar'][4], -r['turlar'][3], -r['ilk8'], r['sira']))
        self.sim_not.text = _sim_notu(sim)
        self.sim_tablo.content = _sim_tablo_html(sira)
        self.finaller.content = _finaller_html(sim, self.ad)
        secenek = {r['id']: r['ad'] for r in sira}
        deger = self.yol_sec.value if self.yol_sec.value in secenek else sira[0]['id']
        self.yol_sec.set_options(secenek, value=deger)
        self.yol_ciz()
        self.ornek_ciz(sim)

    def yol_ciz(self, _=None):
        sim, t = self.d['sim'], self.yol_sec.value
        if not sim or t not in sim['sira_ix']:
            return
        self.yol.content = _yol_html(sim, t)

    def ornek_ciz(self, sim):
        ad = self.ad
        s = sim['ornek_sira']
        self.ornek_lig.content = (f'<div class="lead"><b>Lig aşaması</b> · ilk 8: {", ".join(e(ad(t)) for t in s[:8])}<br>'
                                  f'<span class="cap">Play-off (9-24): {", ".join(e(ad(t)) for t in s[8:24])}</span></div>')
        turlar = {}
        for tur, a, b, ga, gb, k, not_ in sim['ornek']:
            turlar.setdefault(tur, []).append((a, b, ga, gb, k, not_))
        sampiyon = sim['ornek'][-1][5]
        self.ornek_agac.content = (_agac_html(turlar, ad)
                                   + f'<div class="lead" style="margin-top:6px">Şampiyon: <b>{_logo(sampiyon)} {e(ad(sampiyon))}</b></div>')

    async def ornek_yenile(self):
        d = self.d
        if not d['E']:
            return
        sim = await run.io_bound(avrupa.simulasyon, d['v'], d['E'], d['kid'], d['sezon'], 1)
        if sim:
            self.ornek_ciz(sim)

    async def sim_calistir(self):
        d = self.d
        kid, s = d['kid'], d['sezon']
        self.sim_panel.set_visibility(False)
        if s != avrupa.sezonlar(d['v'], kid)[0] or not avrupa.lig_asamasi(avrupa.sezon(d['v'], kid, s)):
            return  # simülasyon yalnızca süren (yeni biçimli) sezon için
        sim = await run.io_bound(avrupa.simulasyon, d['v'], d['E'], kid, s, SIM_N)
        if (kid, s) != (d['kid'], d['sezon']) or not sim:
            return
        d['sim'] = sim
        self.sim_panel.set_visibility(True)
        self.sim_ciz()

    # ---------------------------------------------------------------- seçim
    def sezon_ciz(self):
        d = self.d
        S = avrupa.sezon(d['v'], d['kid'], d['sezon'])
        self.kupa_logo.content = f'<span class="turnuva-logo kucuk" style="background-image:url({lig_logo_url(d["kid"])})"></span>'
        self.tablo_ciz(S)
        turlar = sorted({r[8] for r in S['maclar']}, key=_tur_sirasi)
        secenek = {t: avrupa.tur_adi(t, d['kid'] in avrupa.YEREL) for t in turlar}
        siradaki = next((r[8] for r in S['maclar'] if r[6] is None), turlar[-1] if turlar else None)
        self.tur_sec.set_options(secenek, value=siradaki)
        self.maclari_ciz()
        self.agac_ciz(S)
        self.G.arka_plan(self.sim_calistir())

    def sezonlari_doldur(self):
        d = self.d
        secenek = avrupa.sezonlar(d['v'], d['kid'])
        d['sezon'] = secenek[0] if secenek else None
        self.sezon.set_options({s: s for s in secenek}, value=d['sezon'])

    def kupa_degisti(self, ev_):
        self.d['kid'] = ev_.value
        app.storage.general['avrupa'] = {'kid': ev_.value}
        self.sezonlari_doldur()
        if self.d['sezon']:
            self.sezon_ciz()

    def sezon_degisti(self, ev_):
        if ev_.value and ev_.value != self.d['sezon']:
            self.d['sezon'] = ev_.value
            self.sezon_ciz()

    async def yenile(self):
        d = self.d
        klasor = self.G.depo.veri_klasoru
        v = avrupa.oku(klasor)
        if v is None:
            self.durum.text = 'Avrupa kupaları verisi henüz yok; arka planda indiriliyor (ilk açılışta bir iki dakika sürer).'
            return
        if d['v'] is v:
            return
        self.durum.text = 'Kulüp Elo\'su hesaplanıyor…'
        E = await run.io_bound(avrupa.elo, klasor)
        d['v'], d['E'] = v, E
        self.durum.text = f'{E.n_mac:,} maçtan kulüp Elo\'su · veri: {v["guncellendi"][:10]}'.replace(',', '.')
        self.sezonlari_doldur()
        if d['sezon']:
            self.sezon_ciz()


def kur(G):
    return _Avrupa(G).yenile
