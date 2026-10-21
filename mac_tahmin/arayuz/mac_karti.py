"""Maç kartı: canlı skorlar sekmesinde bir maça tıklanınca açılır. Skor ve durum, olaylar, takım istatistikleri ve saha
üzerinde ilk 11'ler (başlamamış maçta FotMob'un tahmini kadrosu). Başlamamış ve canlı maçta maç saatinin hava tahmini.
Canlı maçta kart açıkken 30 saniyede bir yenilenir."""
import logging
import re

from nicegui import run, ui

from .. import hava
from ..logo import logo_html, takim_logo_url
from ..mac_ozeti import ayrinti
from ..ulkeler import turkce
from .ortak import e, hata_metni, hava_html, kisa_gun, tahmin_acilabilir, tahmine_git, takim_tiklama, yerel

logger = logging.getLogger(__name__)

YENILEME_SN = 30


def _sayi(v):
    """'280 (82%)' → 280, '0.32' → 0.32; sayı yoksa None."""
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r'-?\d+(?:\.\d+)?', str(v or ''))
    return float(m.group()) if m else None


def _yaz(v):
    return str(v).replace('.', ',') if v is not None else '–'


def _istatistik_html(gruplar, ev_ad='', dep_ad=''):
    if not gruplar:
        return '<p class="cap">Bu maç için istatistik yok (maç başlamadı ya da kaynak vermiyor).</p>'
    parca = [f'<div class="ist-lejant"><span class="ev"><i style="background:var(--mk-ev);margin-left:0"></i>{e(ev_ad)}</span>'
             f'<span class="dep">{e(dep_ad)}<i style="background:var(--mk-dep);margin-right:0"></i></span></div>']
    for i, (grup, satirlar) in enumerate(gruplar):
        parca.append(f'<div class="ist-grup">{e(grup)}</div>' if i else '')
        for ad, ev, dep in satirlar:
            a, b = _sayi(ev), _sayi(dep)
            toplam = (a or 0) + (b or 0)
            pa = 50 if not toplam else (a or 0) / toplam * 100
            ust_ev, ust_dep = (a or 0) > (b or 0), (b or 0) > (a or 0)
            parca.append(
                f'<div class="ist"><span class="d ev{" onde" if ust_ev else ""}">{e(_yaz(ev))}</span><span class="ad">{e(ad)}</span>'
                f'<span class="d dep{" onde" if ust_dep else ""}">{e(_yaz(dep))}</span>'
                f'<div class="ist-cubuk{" bos" if not toplam else ""}"><i class="e" style="width:{pa:.1f}%"></i>'
                f'<i class="a" style="width:{100 - pa:.1f}%"></i></div></div>')
    return ''.join(parca)


def _olay_html(olaylar, durum):
    if not olaylar:
        return ('<p class="cap">Henüz olay yok.</p>' if durum in ('canli', 'baslamadi')
                else '<p class="cap">Kaynak bu maç için olay akışı (gol, kart, değişiklik) vermiyor.</p>')
    simge = {'gol': '⚽', 'sari': '<span class="kart sari"></span>', 'kirmizi': '<span class="kart kirmizi"></span>',
             'degisiklik': '<span class="degis">⇄</span>'}
    satirlar = []
    for o in olaylar:
        if o['tur'] == 'devre':
            satirlar.append(f'<div class="olay-ayrac">Devre arası · {o["skor"][0]} – {o["skor"][1]}</div>')
            continue
        if o['tur'] == 'gol':
            metin = f'<b>{e(o["oyuncu"])}</b>' + (f' <span class="cap">({e(o["aciklama"])})</span>' if o.get('aciklama') else '') \
                    + (f'<br><span class="cap">asist: {e(o["asist"])}</span>' if o.get('asist') else '')
            if o.get('skor'):
                metin += f' <span class="olay-skor">{o["skor"][0]} – {o["skor"][1]}</span>'
        elif o['tur'] == 'degisiklik':
            metin = f'<span class="giren">▲ {e(o["giren"])}</span><br><span class="cikan">▼ {e(o["cikan"])}</span>'
        else:
            metin = e(o.get('oyuncu', '')) + (f' <span class="cap">({e(o["aciklama"])})</span>' if o.get('aciklama') else '')
        icerik = f'<span class="olay-simge">{simge[o["tur"]]}</span><span class="olay-metin">{metin}</span>'
        satirlar.append(f'<div class="olay {o["taraf"]}"><span class="olay-dk">{e(o["dk"])}</span>{icerik}</div>')
    return ''.join(satirlar)


def _isaretler(olaylar):
    """Oyuncunun maçtaki olayları simge olarak: ⚽ her gol (kendi kalesine kırmızı), 👟 her asist, sarı / kırmızı kart."""
    o = olaylar or {}
    parca = (['<i class="is-gol" title="Gol">⚽</i>'] * o.get('gol', 0)
             + ['<i class="is-gol kk" title="Kendi kalesine">⚽</i>'] * o.get('kk', 0)
             + ['<i class="is-asist" title="Asist">👟</i>'] * o.get('asist', 0)
             + (['<i class="is-kart sari" title="Sarı kart"></i>'] if o.get('sari') and not o.get('kirmizi') else [])
             + (['<i class="is-kart kirmizi" title="Kırmızı kart"></i>'] if o.get('kirmizi') else []))
    return f'<span class="isaretler">{"".join(parca)}</span>' if parca else ''


def _saha_html(kadro):
    """İki takımın ilk 11'i dikey bir sahada: ev sahibi alt yarıda, deplasman üst yarıda."""
    def oyuncu(p, ev):
        if p['x'] is None or p['y'] is None:
            return ''
        # FotMob'da x takımın sağından ölçülür (0,125 sağ bek, 0,875 sol bek). Yukarı hücum eden ev sahibinin sağı ekranın
        # sağında, aşağı hücum eden deplasmanın sağı ekranın solunda kalır.
        sol = 100 - p['x'] * 100 if ev else p['x'] * 100
        ust = 50 + (1 - p['y']) * 46 if ev else 50 - (1 - p['y']) * 46
        puan = (f'<span class="puan {"iyi" if p["puan"] >= 7 else "kotu" if p["puan"] < 6 else ""}">{_yaz(round(p["puan"], 1))}</span>'
                if p.get('puan') else '')
        ad = p['ad'].split(' ')[-1] if len(p['ad']) > 14 else p['ad']
        tik = f' tiklanir" data-oyuncu="{e(p["id"])}' if p.get('id') else ''  # tıklanınca maçtaki performansı
        return (f'<div class="oy {"ev" if ev else "dep"}{tik}" style="left:{sol:.1f}%;top:{ust:.1f}%">'
                f'<span class="forma">{e(p["no"])}{puan}{_isaretler(p.get("olaylar"))}</span>'
                f'<span class="isim">{e(ad)}{" (K)" if p.get("kaptan") else ""}</span></div>')
    oyuncular = ''.join(oyuncu(p, True) for p in kadro['ev']['ilk11']) + ''.join(oyuncu(p, False) for p in kadro['dep']['ilk11'])
    return ('<div class="saha"><div class="saha-cizgi orta"></div><div class="saha-cizgi yuvarlak"></div>'
            '<div class="saha-cizgi ceza ceza-ust"></div><div class="saha-cizgi ceza ceza-alt"></div>' + oyuncular + '</div>')


def _yedek_html(takim, baslik):
    def ad(p):  # oyuna giren yedek tıklanınca maçtaki performansı (girmeyenin istatistiği yok)
        return (f'<span class="link" data-oyuncu="{e(p["id"])}">{e(p["ad"])}</span>' if p.get('id') and p.get('puan')
                else e(p['ad']))
    yedek = ', '.join(ad(p) + (f' ({e(p["no"])})' if p.get('no') else '') + _isaretler(p.get('olaylar'))
                      for p in takim['yedek']) or '–'
    return (f'<div class="kadro-bilgi"><b>{e(baslik)}</b> · {e(takim["dizilis"])}'
            + (f' · Teknik direktör: {e(takim["teknik"])}' if takim.get('teknik') else '')
            + f'<div class="cap">Yedekler: {yedek}</div></div>')


def _logo(tid):
    return logo_html(takim_logo_url(tid, 'small'), 'mk-logo')


def _uygulamadaki_kayit(depo, fm_id):
    """Oyuncunun uygulamadaki en yeni lig-sezon kaydı (FotMob id'siyle): (lig, yıl, id) ya da None."""
    try:
        from ..sezon import _kariyer_dizini
        satirlar = _kariyer_dizini(depo.veri_klasoru)['fm'].get(int(fm_id)) or []
    except Exception:
        logger.debug('oyuncunun uygulamadaki kaydı bulunamadı: %s', fm_id, exc_info=True)
        return None
    r = max(satirlar, key=lambda r: r['yil'], default=None)
    return (r['anahtar'], r['yil'], r['id']) if r else None


def _perf_ust_html(a, o, pid):
    puan = o.get('puan')
    renk = '' if not puan else 'iyi' if puan >= 7 else 'kotu' if puan < 6 else ''
    isaret = next((_isaretler(p.get('olaylar')) for t in ('ev', 'dep') for p in (a.get('kadro') or {}).get(t, {}).get('ilk11', [])
                   + (a.get('kadro') or {}).get(t, {}).get('yedek', []) if str(p.get('id')) == pid), '')
    return (
        f'<div class="tk-baslik">{_logo(o["takim_id"])}<div>'
        f'<div class="disp" style="font-size:1.7rem;font-weight:700;line-height:1.1">{e(o["ad"])}{isaret}</div>'
        f'<div class="cap">{e(turkce(o["takim"]))}' +(f' · {e(o["no"])} numara' if o['no'] else '') + (' · kaleci' if o['kaleci'] else '')
        + (f' · {o["dk"]} dakika' if o.get('dk') is not None else '')
        + f' · {e(a["ev"]["ad"])} {a["ev"]["skor"] if a["ev"]["skor"] is not None else ""} – '
          f'{a["dep"]["skor"] if a["dep"]["skor"] is not None else ""} {e(a["dep"]["ad"])}</div></div>'
        + (f'<span class="perf-puan {renk}">{_yaz(round(puan, 1))}</span>' if puan else '') + '</div>')


def _perf_govde_html(o):
    tur = {'RightFoot': 'sağ ayak', 'LeftFoot': 'sol ayak', 'Header': 'kafa', 'OtherBodyParts': 'diğer'}
    sonuc = {'Goal': 'Gol', 'AttemptSaved': 'Kurtarıldı', 'Miss': 'Dışarı', 'Post': 'Direk', 'Blocked': 'Engellendi'}
    sutlar = ''
    if o['sutlar']:
        sutlar = ('<div class="perf-grup"><div class="perf-baslik">Şutlar</div>' + ''.join(
            f'<div class="perf-satir"><span>{s["dk"]}\' · {sonuc.get(s["sonuc"], s["sonuc"] or "")}'
            f'{" (" + tur[s["tur"]] + ")" if s.get("tur") in tur else ""}</span>'
            f'<b>xG {_yaz(round(s["xg"], 2)) if s.get("xg") is not None else "–"}</b></div>' for s in o['sutlar']) + '</div>')
    return '<div class="perf-izgara">' + ''.join(
        f'<div class="perf-grup"><div class="perf-baslik">{e(g)}</div>'
        + ''.join(f'<div class="perf-satir"><span>{e(ad)}</span><b>{e(v)}</b></div>' for ad, v in satirlar) + '</div>'
        for g, satirlar in o['gruplar']) + sutlar + '</div>'


def _ust_html(a, durum, skor):
    """Maç kartının üstü: takımlar (tıklanınca takım sayfası), skor ya da saat ve durum."""
    return (  # takıma tıklanınca takım sayfası (milli takımlarda FotMob'un takım sayfası da var)
        f'<div class="mk-ust"><div class="mk-takim" data-takim="{e(a["ev"]["id"])}" title="Takım sayfası">{_logo(a["ev"]["id"])}'
        f'<b>{e(a["ev"]["ad"])}</b></div>'
        f'<div class="mk-orta"><div class="mk-skor{" canli" if a["durum"] == "canli" else ""}">{skor}</div>{durum}</div>'
        f'<div class="mk-takim" data-takim="{e(a["dep"]["id"])}" title="Takım sayfası">{_logo(a["dep"]["id"])}'
        f'<b>{e(a["dep"]["ad"])}</b></div></div>')


class _MacKarti:
    """Maç kartı penceresi (olaylar, istatistikler, kadrolar) ve oyuncunun maçtaki performansı penceresi. d['istek']: eski
    maçın geç gelen verisi yenisinin üstüne yazılmasın."""

    def __init__(self, G):
        self.G = G
        self.d = {'mac': None, 'istek': 0, 'veri': None}
        self._iskelet_kart()
        self._iskelet_perf()
        self.kadro.on('click', self.oyuncu_tiklandi,
                      js_handler='(e) => { const t = e.target.closest("[data-oyuncu]"); if (t) emit(t.dataset.oyuncu); }')
        ui.timer(YENILEME_SN, self.tazele)
        self.kart.on('hide', lambda: self.d.update(mac=None, veri=None))

    # ---------------------------------------------------------------- arayüz iskeleti
    def _iskelet_kart(self):
        with ui.dialog() as self.kart, ui.card().classes('w-full gap-3 mac-kart').style(
                'max-width:820px;background:var(--panel);color:var(--ink)'):
            with ui.row().classes('w-full items-center no-wrap'):
                self.baslik = ui.label().classes('cap grow')
                self.tahmin_dugme = ui.button('Maç tahmini', icon='insights', on_click=lambda: self.tahmine()).props(
                    'flat dense no-caps color=primary').tooltip(
                    'Bu maçın tahminini aç (lig maçında Maç tahmini sekmesi; kupa ve milli maçta ilgili sekme)')
                ui.button(icon='close', on_click=self.kart.close).props('flat round dense')
            self.ust = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), self.G)
            self.hava_yer = ui.html('', sanitize=False).classes('w-full').style('text-align:center;font-size:.85rem')
            with ui.tabs().props('dense no-caps active-color=primary indicator-color=primary align=justify').classes(
                    'w-full') as self.sekme:
                ui.tab('olay', 'Olaylar')
                ui.tab('ist', 'İstatistikler')
                ui.tab('kadro', 'Kadrolar')
            with ui.tab_panels(self.sekme, value='olay').props('animated=false').classes('w-full').style(
                    'background:transparent'):
                with ui.tab_panel('olay'):
                    self.olay = ui.html('', sanitize=False).classes('w-full')
                with ui.tab_panel('ist'):
                    self.ist = ui.html('', sanitize=False).classes('w-full')
                with ui.tab_panel('kadro'):
                    self.kadro_not = ui.label().classes('cap')
                    self.kadro = ui.html('', sanitize=False).classes('w-full')
            self.alt = ui.label().classes('cap')

    def _iskelet_perf(self):
        # oyuncunun maçtaki performansı
        with ui.dialog() as self.perf, ui.card().classes('w-full gap-2').style(
                'max-width:720px;background:var(--panel);color:var(--ink)'):
            with ui.row().classes('w-full items-start no-wrap'):
                self.perf_ust = ui.html('', sanitize=False).classes('grow')
                self.perf_kart = ui.button('Oyuncu kartı', icon='badge', on_click=lambda: self.oyuncu_karti_ac()).props(
                    'flat dense no-caps color=primary').tooltip('Oyuncunun sezon kartı (uygulamadaki liginde)')
                ui.button(icon='close', on_click=self.perf.close).props('flat round dense')
            self.perf_govde = ui.html('', sanitize=False).classes('w-full')
            ui.label('Kaynak: FotMob. Canlı maçta kart açıkken 30 saniyede bir güncellenir.').classes('cap')

    # ---------------------------------------------------------------- oyuncunun maçtaki performansı
    def oyuncu_tiklandi(self, ev):
        pid = str(ev.args or '')
        if self.d['veri'] and pid in (self.d['veri'].get('oyuncular') or {}):
            self.d['perf'] = pid
            self.perf_ciz()
            self.perf.open()
        else:
            ui.notify('Bu oyuncu için maç istatistiği yok (oyuna girmemiş ya da kaynak vermiyor).')

    def perf_ciz(self):
        a, pid = self.d['veri'], self.d.get('perf')
        o = (a or {}).get('oyuncular', {}).get(pid)
        if not o:
            return
        self.perf_ust.content = _perf_ust_html(a, o, pid)
        self.perf_govde.content = _perf_govde_html(o)
        self.perf_kart.set_visibility(bool(_uygulamadaki_kayit(self.G.depo, pid)))

    def oyuncu_karti_ac(self):
        k = _uygulamadaki_kayit(self.G.depo, self.d.get('perf'))
        if k:
            self.perf.close()
            self.kart.close()
            self.G.git(*k)

    # ---------------------------------------------------------------- maç kartı
    def ciz(self, a, m):
        z = yerel(a.get('baslangic') or m.get('baslangic'))
        if a['durum'] == 'canli':
            durum = f'<span class="durum canli"><i class="nabiz"></i>{e(a.get("dakika") or "Canlı")}</span>'
        elif a['durum'] == 'bitti':
            durum = '<span class="durum">Maç sonu</span>'
        else:
            durum = f'<span class="durum">{kisa_gun(z.date()) + " · " + f"{z:%H:%M}" if z else ""}</span>'
        skor = (f'{a["ev"]["skor"]} – {a["dep"]["skor"]}' if a['durum'] in ('canli', 'bitti') else (f'{z:%H:%M}' if z else '–'))
        self.ust.content = _ust_html(a, durum, skor)
        self.olay.content = _olay_html(a['olaylar'], a['durum'])
        self.ist.content = _istatistik_html(a['istatistik'], a['ev']['ad'], a['dep']['ad'])
        k = a.get('kadro')
        if k and k['ev']['ilk11']:
            self.kadro_not.text = ('Tahmini ilk 11 (FotMob); maç saatine yakın açıklanan kadroyla değişebilir.' if k.get('tur') == 'predicted'
                                   else 'İlk 11\'ler. Formanın köşesindeki sayı oyuncunun maç puanı (FotMob). Oyuncuya tıklayınca '
                                        'bu maçtaki istatistikleri (pas, orta, şut, ikili mücadele…) açılır.')
            self.kadro.content = (_saha_html(k) + '<div class="kadro-alt">' + _yedek_html(k['dep'], a['dep']['ad'])
                                  + _yedek_html(k['ev'], a['ev']['ad']) + '</div>')
        else:
            self.kadro_not.text = 'Kadro henüz açıklanmadı; FotMob bu maç için tahmini kadro da yayınlamamış.'
            self.kadro.content = ''
        self.alt.text = ('Canlı: 30 saniyede bir yenilenir. ' if a['durum'] == 'canli' else '') + 'Kaynak: FotMob.'
        if self.perf.value:  # açık oyuncu performansı da güncellenir
            self.perf_ciz()

    async def yukle(self, m, ilk=False):
        G, d = self.G, self.d
        d['istek'] += 1
        istek = d['istek']
        if ilk:
            self.ust.content = '<div class="cap">Maç ayrıntısı alınıyor…</div>'
            self.olay.content = self.ist.content = self.kadro.content = self.hava_yer.content = ''
            self.kadro_not.text = self.alt.text = ''
        try:
            a = await run.io_bound(ayrinti, m['id'], G.depo.g.ham)
        except Exception as ex:
            if istek == d['istek'] and ilk:
                self.ust.content = f'<div class="cap">Maç ayrıntısı alınamadı: {e(hata_metni(ex, "maç ayrıntısı"))}</div>'
            return
        if istek != d['istek'] or d['mac'] is not m:
            return
        d['veri'] = a
        self.ciz(a, m)
        if a['durum'] in ('baslamadi', 'canli'):  # maç saatindeki hava tahmini (yalnızca bilgi)
            try:
                hv = await run.io_bound(hava.mac_havasi, G.depo.mac_konumu(m, a['ev'].get('id')),
                                        a.get('baslangic') or m.get('baslangic'), G.depo.g.ham)
            except Exception:
                logger.debug('maç havası alınamadı', exc_info=True)
                hv = None
            if istek == d['istek'] and d['mac'] is m:
                self.hava_yer.content = hava_html(hv)
        else:
            self.hava_yer.content = ''

    def tahmine(self):
        m = self.d['mac']
        if m and tahmine_git(self.G, m):
            self.kart.close()

    async def ac(self, m):
        if not m.get('id'):
            return
        self.d['mac'] = m
        b, grup = m.get('baslik') or '', m.get('grup') or ''
        lig = re.match(r'([A-D]) Ligi · (.+)', grup)
        if lig and b.endswith(' ' + lig.group(1)):  # "Uluslar Ligi A · A Ligi · 1. Grup" → "Uluslar Ligi A · 1. Grup"
            grup = lig.group(2)
        self.baslik.text = ' · '.join(x for x in (b, grup) if x)
        self.sekme.set_value('olay' if m['durum'] in ('canli', 'bitti') else 'kadro')
        self.tahmin_dugme.set_visibility(tahmin_acilabilir(m))  # canlı lig maçında tahmine geçilmez
        self.kart.open()
        await self.yukle(m, ilk=True)

    async def tazele(self):
        d = self.d
        if self.kart.value and d['mac'] and d['veri'] and d['veri']['durum'] == 'canli':
            await self.yukle(d['mac'])


def kur(G):
    return _MacKarti(G).ac
