"""Takım sayfası: takımın adına tıklanınca açılır. Son 5 maç (bütün kulvarlar) ve form, sıradaki maçlar, kulvar kulvar
bütün maçlar (lig, Avrupa, kupa, hazırlık), en çok oynayan 11 (uygulamanın lig verisinden, takımın dizilişine göre) ve
son maçın ilk 11'i, sakatlar ve güncel kadro. Veri FotMob takım sayfasından (takim.py); maça tıklanınca maç kartı açılır."""
import logging
import re

from nicegui import run, ui

from .. import avrupa, lig_maclari, takim
from ..logo import logo_html, takim_logo_url
from . import bildirim
from ..sezon import SANS_ESIK, SON_SEZON, hak_edilen_puan
from .ortak import FORM, e, fmt, hata_metni, kisa_gun, yerel, yuzde

logger = logging.getLogger(__name__)

GRUP_ADI = {'keepers': 'Kaleciler', 'defenders': 'Defans', 'midfielders': 'Orta saha', 'attackers': 'Forvet'}
# yaş haritasında mevki grupları ve renkleri (FotMob kadro grubu → seri adı)
YAS_GRUPLARI_RENK = [('Kaleci', '#8a9088'), ('Defans', '#35598a'), ('Orta saha', '#c9960f'), ('Forvet', '#b0413e')]
YAS_GRUBU = {'keepers': 'Kaleci', 'defenders': 'Defans', 'midfielders': 'Orta saha', 'attackers': 'Forvet'}


def _logo(tid, kucuk=True):
    return logo_html(takim_logo_url(tid, 'xsmall' if kucuk else 'small') if tid else '')


def _rozet(s):
    return f'<i class="{s}" title="{FORM[s][1]}">{FORM[s][0]}</i>' if s else ''


def _saha(oyuncular, not_=''):
    """Tek takımın 11'i dikey sahada (takım yukarı hücum eder). x: takımın sağından (FotMob gibi), y: kendi kalesinden."""
    parca = []
    for p in oyuncular:
        if p.get('x') is None or p.get('y') is None:
            continue
        sol, ust = 100 - p['x'] * 100, 4 + (1 - p['y']) * 90
        ad = p['ad'].split(' ')[-1] if len(p['ad']) > 14 else p['ad']
        ek = ' <span class="sakat-isaret" title="Sakat">✚</span>' if p.get('sakat') else ''
        # tıklanınca oyuncu kartı: uygulamadaki oyuncu sırası (idx) ya da FotMob id'si
        anahtar = f'idx:{p["idx"]}' if p.get('idx') is not None else f'fm:{p["id"]}' if p.get('id') else ''
        veri = f' data-oyuncu="{e(anahtar)}"' if anahtar else ''
        parca.append(f'<div class="oy ev tiklanir" style="left:{sol:.1f}%;top:{ust:.1f}%"{veri}><span class="forma">'
                     f'{e(p.get("no") or "")}</span><span class="isim">{e(ad)}{ek}</span></div>')
    return ('<div class="saha tek"><div class="saha-cizgi orta"></div><div class="saha-cizgi yuvarlak"></div>'
            '<div class="saha-cizgi ceza ceza-ust"></div><div class="saha-cizgi ceza ceza-alt"></div>' + ''.join(parca) + '</div>'
            + (f'<p class="cap">{e(not_)}</p>' if not_ else ''))


def avrupa_siralari(veri_klasoru, tid):
    """Takımın Avrupa kupalarındaki güncel durumu (her kupanın en yeni sezonu): lig / grup aşamasındaki sırası ya da
    eleme turundaysa o tur. Ör. ['Şampiyonlar Ligi: lig aşamasında 12. (9 puan, 4 maç)']."""
    v = avrupa.oku(veri_klasoru)
    if v is None:
        return []
    out = []
    for kid, ad in avrupa.KUPALAR:
        sezonlar = avrupa.sezonlar(v, kid)
        # yalnızca süren sezon (kupanın yeni sezonu henüz başlamadıysa geçen sezonun sırası gösterilmez)
        S = avrupa.sezon(v, kid, sezonlar[0]) if sezonlar and avrupa._yil(sezonlar[0]) >= SON_SEZON else None
        if not S:
            continue
        tablo = S.get('tablo') or []
        yer = next(((grup, k + 1, r) for grup, satirlar in tablo for k, r in enumerate(satirlar) if str(r[0]) == str(tid)), None)
        if yer:
            grup, sira, r = yer
            asama = 'lig aşamasında' if len(tablo) == 1 else f'{grup} grubunda'
            out.append(f'{ad}: {asama} {sira}. ({r[8]} puan, {r[2]} maç)')
            continue
        turlar = [x[0] for x in S.get('eleme') or [] if str(tid) in (str(x[2]), str(x[3]))]
        if turlar:
            out.append(f'{ad}: {avrupa.tur_adi(turlar[-1])}')
    return out


def kur(G):
    d = {'t': None, 'istek': 0, 'veri': None, 'ilk11': {}}
    with ui.dialog() as dlg, ui.card().classes('w-full gap-3 takim-kart').style('max-width:940px;background:var(--panel);color:var(--ink)'):
        with ui.row().classes('w-full items-start no-wrap'):
            ust = ui.html('', sanitize=False).classes('grow')
            yildiz = ui.button('Takımlarıma ekle', icon='star_border', on_click=lambda: favori()).props(
                'flat dense no-caps color=accent')
            ui.button(icon='close', on_click=dlg.close).props('flat round dense')
        with ui.row().classes('w-full gap-4 items-start'):
            with ui.column().classes('gap-1').style('flex:1 1 380px'):
                ui.label('Son 5 maç').classes('disp text-lg font-bold')
                son5 = ui.html('', sanitize=False).classes('w-full')
            with ui.column().classes('gap-1').style('flex:1 1 380px'):
                ui.label('Sıradaki maçlar').classes('disp text-lg font-bold')
                siradaki = ui.html('', sanitize=False).classes('w-full')
        ui.label('Takımın en iyileri (bu sezon, lig)').classes('disp text-lg font-bold')
        liderler = ui.html('', sanitize=False).classes('w-full')
        with ui.column().classes('w-full gap-1') as xg_bolum:
            ui.label('xG gelişimi (bu sezon, lig)').classes('disp text-lg font-bold')
            xg_not = ui.label().classes('cap')
            xg_grafik = ui.echart({
                'animation': False, 'tooltip': {'trigger': 'axis'}, 'legend': {'bottom': 0},
                'grid': {'left': 40, 'right': 16, 'top': 14, 'bottom': 56},
                'xAxis': {'type': 'category', 'data': [], 'axisLabel': {'fontSize': 10}},
                'yAxis': {'type': 'value', 'name': 'xG', 'min': 0},
                'series': [
                    {'name': 'Ürettiği xG', 'type': 'bar', 'itemStyle': {'color': 'rgba(47,122,87,.45)'}, 'data': []},
                    {'name': 'Verdiği xG', 'type': 'bar', 'itemStyle': {'color': 'rgba(176,65,62,.35)'}, 'data': []},
                    {'name': 'Ürettiği (5 maç ort.)', 'type': 'line', 'smooth': True, 'showSymbol': False,
                     'lineStyle': {'width': 3}, 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                    {'name': 'Verdiği (5 maç ort.)', 'type': 'line', 'smooth': True, 'showSymbol': False,
                     'lineStyle': {'width': 3}, 'itemStyle': {'color': '#b0413e'}, 'data': []}],
            }).classes('w-full').style('height:260px')
        xg_bolum.set_visibility(False)
        with ui.column().classes('w-full gap-1') as yari_bolum:
            ui.label('İlk yarı ve ikinci yarı (bu sezon, lig)').classes('disp text-lg font-bold')
            yari_kutu = ui.html('', sanitize=False).classes('w-full')
        yari_bolum.set_visibility(False)
        with ui.column().classes('w-full gap-1') as yas_bolum:
            ui.label('Kadro yaş haritası (bu sezon, lig)').classes('disp text-lg font-bold')
            yas_not = ui.label().classes('cap')
            yas_grafik = ui.echart({
                'animation': False, 'tooltip': {'trigger': 'item', 'formatter': '{b}'}, 'legend': {'bottom': 0},
                'grid': {'left': 46, 'right': 16, 'top': 14, 'bottom': 56},
                'xAxis': {'type': 'value', 'name': 'Yaş', 'nameLocation': 'middle', 'nameGap': 24, 'min': 16, 'max': 40},
                'yAxis': {'type': 'value', 'name': 'Süre payı %', 'min': 0, 'max': 100},
                'series': [{'name': ad, 'type': 'scatter', 'symbolSize': 11, 'itemStyle': {'color': renk}, 'data': [],
                            **({'markArea': {'silent': True, 'itemStyle': {'color': 'rgba(47,122,87,.07)'},
                                             'label': {'color': '#8a9088', 'fontSize': 10},
                                             'data': [[{'name': 'Gelişim', 'xAxis': 16}, {'xAxis': 23.5}],
                                                      [{'name': 'Zirve', 'xAxis': 23.5, 'itemStyle': {'color': 'rgba(201,150,15,.07)'}},
                                                       {'xAxis': 29.5}],
                                                      [{'name': 'Deneyim', 'xAxis': 29.5, 'itemStyle': {'color': 'rgba(176,65,62,.07)'}},
                                                       {'xAxis': 40}]]}} if k == 0 else {})}
                           for k, (ad, renk) in enumerate(YAS_GRUPLARI_RENK)],
            }).classes('w-full').style('height:300px')
        yas_bolum.set_visibility(False)
        ui.label('Bütün maçlar').classes('disp text-lg font-bold')
        kulvar = ui.toggle({}, on_change=lambda _: liste_ciz()).props('dense no-caps unelevated toggle-color=primary')
        liste = ui.html('', sanitize=False).classes('w-full').style('max-height:360px;overflow-y:auto')
        with ui.row().classes('w-full items-center'):
            ui.label('İlk 11').classes('disp text-lg font-bold')
            ui.space()
            ilk11_sec = ui.toggle({}, on_change=lambda _: ilk11_ciz()).props('dense no-caps unelevated toggle-color=primary')
        with ui.row().classes('w-full gap-4 items-start'):
            saha = ui.html('', sanitize=False).style('flex:1 1 360px;max-width:440px')
            with ui.column().classes('gap-1').style('flex:1 1 300px'):
                ui.label('Sakat ve şüpheliler').classes('disp text-lg font-bold')
                sakatlar = ui.html('', sanitize=False).classes('w-full')
                ui.label('Kadro').classes('disp text-lg font-bold')
                kadro = ui.html('', sanitize=False).classes('w-full').style('max-height:420px;overflow-y:auto')
        alt = ui.label('Kaynak: FotMob (fikstür, kadro, sakatlar) ve uygulamanın lig verisi (oynanan dakikalar).').classes('cap')

    def yildiz_ciz():
        fav = d['veri'] is not None and bildirim.favori_mi(d['veri']['id'])
        yildiz.props(f'icon={"star" if fav else "star_border"}')
        yildiz.text = 'Takımlarımda' if fav else 'Takımlarıma ekle'
        yildiz.set_visibility(d['veri'] is not None)

    def favori():
        v = d['veri']
        if v is None:
            return
        eklendi = bildirim.favori_degistir(v['id'], v['ad'])
        yildiz_ciz()
        ui.notify(f'{v["ad"]} takımlarına eklendi: maçlarında başlama, gol ve maç sonu bildirimi alırsın.' if eklendi
                  else f'{v["ad"]} takımlarından çıkarıldı.')
        G.yay('favoriler')

    def mac_tiklandi(ev):
        m = next((x for x in (d['veri'] or {}).get('maclar', []) if str(x['id']) == str(ev.args)), None)
        if m:
            G.mac_ac({'id': m['id'], 'baslik': m['turnuva'], 'grup': '', 'baslangic': m['zaman'],
                      'durum': 'canli' if m['canli'] else 'bitti' if m['bitti'] else 'baslamadi'})

    js = '(e) => { const t = e.target.closest("[data-mac]"); if (t) emit(t.dataset.mac); }'
    for oge in (son5, siradaki, liste):
        oge.on('click', mac_tiklandi, js_handler=js)

    def oyuncu_tiklandi(ev):
        """Kadrodaki, sakatlar listesindeki ya da sahadaki oyuncu: uygulamadaki kaydının oyuncu kartı."""
        anahtar = str(ev.args or '')
        S, p = d.get('S'), None
        if anahtar.startswith('idx:') and S:
            i = int(anahtar[4:])
            p = S.PLY[i] if 0 <= i < len(S.PLY) else None
        elif anahtar.startswith('fm:'):
            p = d.get('esle', {}).get(anahtar[3:])
        if p is None or S is None:
            ui.notify('Bu oyuncunun bu sezon uygulamadaki ligde kaydı yok (henüz oynamamış ya da lig uygulamada değil).')
            return
        if G.S is S:
            G.oyuncu_ac(p['idx'])
        else:  # başka lig ya da sezon: önce oraya geçilir, kart orada açılır
            G.git(S.lig, S.yil, p['id'])

    js_oyuncu = '(e) => { const t = e.target.closest("[data-oyuncu]"); if (t) { e.stopPropagation(); emit(t.dataset.oyuncu); } }'
    for oge in (saha, sakatlar, kadro, liderler):
        oge.on('click', oyuncu_tiklandi, js_handler=js_oyuncu)

    def liderler_ciz(v):
        """Gol, asist ve FotMob puanında takımın ilk 3'ü. Uygulamanın liginde: lig verisi (xG/xA ile); değilse FotMob."""
        S, oy = d.get('S'), d.get('takimdakiler') or []
        sutunlar = []
        if S and oy:
            mac = next((r['O'] for r in S.tb if r['name'] == d.get('uygulama_adi')), 0)
            esik = max(90, 0.3 * mac * 90)  # puan sıralaması için en az süre (bir maçlık yüksek puan öne geçmesin)

            def ad(p):
                ek = f' <span class="cap">→ {e(p["ayrildi"][0] or "ayrıldı")}</span>' if p.get('ayrildi') else ''
                return f'<span class="link" data-oyuncu="idx:{p["idx"]}">{e(p["n"])}</span>{ek}'
            gol = sorted((p for p in oy if p['g'] > 0), key=lambda p: (-p['g'], -p['xg']))[:3]
            asist = sorted((p for p in oy if p['a'] > 0), key=lambda p: (-p['a'], -p['xa']))[:3]
            puan = sorted((p for p in oy if (p['ex'] or {}).get('rt') and p['min'] >= esik), key=lambda p: -p['ex']['rt'])[:3]
            sutunlar = [('Gol', [(ad(p), str(p['g']), f'{fmt(p["xg"], 1)} xG') for p in gol]),
                        ('Asist', [(ad(p), str(p['a']), f'{fmt(p["xa"], 1)} xA') for p in asist]),
                        ('FotMob puanı', [(ad(p), fmt(p['ex']['rt'], 2), f'{p["mp"]} maç') for p in puan])]
        else:
            ei = v.get('en_iyiler') or {}
            hucre = lambda x: f'<span class="link" data-oyuncu="fm:{x[1]}">{e(x[0])}</span>'
            sutunlar = [('Gol', [(hucre(x), str(x[2]), '') for x in ei.get('gol', [])]),
                        ('Asist', [(hucre(x), str(x[2]), '') for x in ei.get('asist', [])]),
                        ('FotMob puanı', [(hucre(x), fmt(x[2], 2) if isinstance(x[2], (int, float)) else str(x[2]), '')
                                          for x in ei.get('puan', [])])]
        liderler.content = '<div class="lider-izgara">' + ''.join(
            f'<div class="lider-kutu"><div class="cap" style="font-weight:700">{b}</div>' + (''.join(
                f'<div class="lider"><span class="sira">{k + 1}</span><span class="ad">{a}</span><b>{deg}</b>'
                f'<span class="cap">{ek}</span></div>' for k, (a, deg, ek) in enumerate(satirlar)) or '<div class="cap">–</div>')
            + '</div>' for b, satirlar in sutunlar) + '</div>'

    def satir(m, tid, tahminli=False):
        z = yerel(m['zaman'])
        zaman = f'{kisa_gun(z.date())} {z:%H:%M}' if z else ''
        if m['skor']:
            orta = f'<b>{m["skor"][0]} – {m["skor"][1]}</b>' + (' <span class="cap">pen.</span>' if m['pen'] else '')
        elif m['canli']:
            orta = '<span class="durum canli"><i class="nabiz"></i>Canlı</span>'
        elif m['iptal']:
            orta = '<span class="cap">iptal</span>'
        else:
            orta = '<span class="cap">–</span>'
            if tahminli:
                p = olasilik(m)
                if p:
                    # uygulamanın her yerindeki gibi: ev sahibi · beraberlik · deplasman (adların yanındaki sırayla);
                    # favori yeşil, diğer taraf kırmızı
                    ev_s, dep_s = ('kaz', 'kay') if p[0] >= p[2] else ('kay', 'kaz')
                    orta = (f'<div class="olas"><span class="{ev_s}" title="{e(m["ev"])} kazanır">{yuzde(p[0])}</span>'
                            f'<span class="ber" title="Beraberlik">{yuzde(p[1])}</span>'
                            f'<span class="{dep_s}" title="{e(m["dep"])} kazanır">{yuzde(p[2])}</span></div>')
        ev_b, dep_b = ('b' if m['evId'] == tid else ''), ('b' if m['depId'] == tid else '')
        return (f'<div class="tk-mac" data-mac="{e(m["id"])}"><div class="tk-ust">{zaman} · {e(m["turnuva"])}</div>'
                f'<div class="tk-ev {ev_b}">{e(m["ev"])} {_logo(m["evId"])}</div><div class="tk-orta">{orta}</div>'
                f'<div class="tk-dep {dep_b}">{_logo(m["depId"])} {e(m["dep"])}</div>'
                f'<div class="tk-sonuc"><span class="form">{_rozet(m["sonuc"])}</span></div></div>')

    def olasilik(m):
        """Oynanmamış maçın olasılıkları: lig maçında ligin modeli, Avrupa maçında kulüp Elo'su."""
        if m['kategori'] == 'lig' and d.get('S'):
            S = d['S']
            ids = {str(G.depo.takim_kimligi(S.lig, ad)): i for i, ad in enumerate(S.T)}
            h, a = ids.get(str(m['evId'])), ids.get(str(m['depId']))
            if h is not None and a is not None:
                return S.tahmin(h, a)['p']
        if m['kategori'] == 'avrupa' and d.get('E'):
            return d['E'].tahmin(m['evId'], m['depId'])['p']
        return None

    def liste_ciz():
        v = d['veri']
        if not v:
            return
        maclar = [m for m in v['maclar'] if m['kategori'] == kulvar.value]
        gelecek = [m for m in maclar if not m['skor']]
        oynanan = [m for m in maclar if m['skor']][::-1]
        liste.content = ((f'<div class="tk-grup">Sıradaki maçlar ({len(gelecek)})</div>' if gelecek else '')
                         + ''.join(satir(m, v['id'], tahminli=True) for m in gelecek)
                         + (f'<div class="tk-grup">Oynanan maçlar ({len(oynanan)})</div>' if oynanan else '')
                         + ''.join(satir(m, v['id']) for m in oynanan)) or '<p class="cap">Maç yok.</p>'

    def ilk11_ciz():
        sec = d['ilk11'].get(ilk11_sec.value)
        saha.content = _saha(*sec) if sec else '<p class="cap">Bu takım için ilk 11 bilgisi yok.</p>'

    async def ac(anahtar):
        """anahtar: FotMob takım id'si ya da açık ligdeki takım adı."""
        tid = int(anahtar) if re.fullmatch(r'-?[0-9]{1,18}', str(anahtar)) else G.depo.takim_kimligi(G.S.lig, anahtar) if G.S else None
        if tid is None:
            ui.notify('Bu takımın FotMob kaydı bulunamadı.')
            return
        d['istek'] += 1
        istek = d['istek']
        d.update(veri=None, S=None, E=None, ilk11={}, esle={}, takimdakiler=[], uygulama_adi=None)
        liderler.content = ''
        ust.content = '<div class="cap">Takım bilgisi alınıyor…</div>'
        yildiz_ciz()
        for oge in (son5, siradaki, liste, saha, sakatlar, kadro):
            oge.content = ''
        xg_bolum.set_visibility(False)
        yari_bolum.set_visibility(False)
        yas_bolum.set_visibility(False)
        dlg.open()
        try:
            v = await run.io_bound(takim.takim_sayfasi, tid, G.depo.g.ham)
        except Exception as ex:
            ust.content = f'<div class="cap">Takım bilgisi alınamadı: {e(hata_metni(ex, "takım bilgisi"))}</div>'
            return
        if istek != d['istek']:
            return
        d['veri'] = v
        # lig verisi (olasılıklar ve en çok oynayan 11) ve kulüp Elo'su (Avrupa maçları)
        bulunan = G.depo.takim_ligi(tid)
        oyuncular, onceki = [], {}
        if bulunan:
            lig, uygulama_adi = bulunan
            try:
                S = await run.io_bound(G.depo.sezon, lig, SON_SEZON)
                if not S.M:
                    raise ValueError
            except Exception:
                logger.debug('takımın ligi kurulamadı: %s', lig, exc_info=True)
                S = None
            if S is not None:
                d['S'] = S
                takimdakiler = [p for p in S.PLY if uygulama_adi in p['t'].split(' / ')]
                # FotMob kadro kaydı → uygulamadaki oyuncu (FotMob kaynaklı liglerde id aynı, Understat'ta adla eşleşir)
                esle = {}
                for k in v['kadro']:
                    p = next((q for q in takimdakiler if str(q.get('fm_id')) == str(k['id'])), None) \
                        or next((q for q in takimdakiler if takim.kadrodaki(q['n'], [k])), None)
                    if p:
                        esle[str(k['id'])] = p
                d['esle'] = esle
                d['takimdakiler'], d['uygulama_adi'] = takimdakiler, uygulama_adi
                # ilk 11 adayları: yalnızca bu sezon bu takımda oynamış, hâlâ kadroda olan ve sakat olmayanlar
                oyuncular, d['ilk11_sakat'], onceki = takim.ilk11_adaylari(S, uygulama_adi, v['kadro'])
        if any(m['kategori'] == 'avrupa' for m in v['maclar']):
            d['E'] = await run.io_bound(avrupa.elo, G.depo.veri_klasoru)
        d['avrupa_sira'] = await run.io_bound(avrupa_siralari, G.depo.veri_klasoru, tid) or []
        xg_maclar, yari = [], []
        if d.get('S') and d.get('uygulama_adi'):
            xg_maclar, _ = await run.io_bound(G.depo.xg_maclari, d['S'])
            yari = await run.io_bound(lig_maclari.yari_maclari, d['S'].lig, G.depo.g.ham) or []
        if istek != d['istek']:
            return
        ciz(v, oyuncular, onceki)
        xg_ciz(d.get('uygulama_adi'), xg_maclar)
        yari_ciz(tid, yari)
        yas_ciz(v)

    def yas_ciz(v):
        """Güncel kadronun yaşa göre süre payı (bu sezon ligde oynadığı dakika / takımın toplam dakikası): kadronun
        yaşlanıp yaşlanmadığı, gençlerin oynayıp oynamadığı. Oyuncunun dakikası uygulamanın lig verisinden."""
        S, esle = d.get('S'), d.get('esle') or {}
        mac = next((r['O'] for r in S.tb if r['name'] == d.get('uygulama_adi')), 0) if S else 0
        yas_bolum.set_visibility(bool(S and mac))
        if not S or not mac:
            return
        noktalar = {ad: [] for ad, _ in YAS_GRUPLARI_RENK}
        dakika = []
        for k in v['kadro']:
            p = esle.get(str(k['id']))
            dk = p['min'] if p and not p.get('ayrildi') else 0
            if not k.get('yas'):
                continue
            pay = min(100, dk / (mac * 90) * 100)
            grup = YAS_GRUBU.get(k['grup'], YAS_GRUPLARI_RENK[-1][0])
            noktalar[grup].append({'name': f'{k["ad"]} · {k["yas"]} yaş · %{round(pay)} süre', 'value': [k['yas'], round(pay, 1)]})
            dakika.append((k['yas'], dk))
        for s in yas_grafik.options['series']:
            s['data'] = noktalar[s['name']]
        yas_grafik.update()
        toplam = sum(dk for _, dk in dakika) or 1
        ort = sum(y * dk for y, dk in dakika) / toplam
        genc = sum(dk for y, dk in dakika if y <= 23) / toplam
        yasli = sum(dk for y, dk in dakika if y >= 30) / toplam
        kadro_ort = sum(y for y, _ in dakika) / len(dakika) if dakika else 0
        yas_not.text = (f'Kadronun yaş ortalaması {fmt(kadro_ort, 1)}; sahada (dakikaya göre ağırlıklı) {fmt(ort, 1)}. Sürenin '
                        f'%{round(genc * 100)} kadarı 23 yaş ve altına, %{round(yasli * 100)} kadarı 30 yaş ve üstüne gidiyor. '
                        'Her nokta güncel kadrodan bir oyuncu: yatayda yaşı, dikeyde bu sezon ligde takımın toplam süresinden '
                        'aldığı pay.')

    def yari_ciz(tid, maclar):
        """İlk yarı ve ikinci yarı sonuçları ve golleri (indirilmiş maç sayfalarındaki devre skorundan; yalnızca bilgi:
        takıma özgü yarı eğilimi tahmine katılmaz, sezonun bir bölümündeki eğilim öbürünü zayıf öngörüyor)."""
        benim = [m for m in maclar if str(tid) in (str(m['ev_id']), str(m['dep_id']))]
        yari_bolum.set_visibility(len(benim) >= 3)
        if len(benim) < 3:
            yari_kutu.content = ''
            return
        iy, iky = [0, 0, 0], [0, 0, 0]  # önde / berabere / geride; ikinci yarıyı kazandı / berabere / kaybetti
        ag = [0, 0]  # attığı: ilk yarı, ikinci yarı
        yg = [0, 0]
        geri_donus = onu_kacirdi = 0
        for m in benim:
            ben = 0 if str(m['ev_id']) == str(tid) else 1
            i1, i2 = m['iy'][ben], m['iy'][1 - ben]
            s1, s2 = m['ms'][ben], m['ms'][1 - ben]
            iy[0 if i1 > i2 else 1 if i1 == i2 else 2] += 1
            k1, k2 = s1 - i1, s2 - i2
            iky[0 if k1 > k2 else 1 if k1 == k2 else 2] += 1
            ag[0] += i1; ag[1] += k1; yg[0] += i2; yg[1] += k2
            geri_donus += i1 < i2 and s1 >= s2
            onu_kacirdi += i1 > i2 and s1 <= s2
        n = len(benim)

        def yuz(x):
            return f'%{round(x / n * 100)}'
        yari_kutu.content = (
            '<div class="tiles" style="grid-template-columns:repeat(2,1fr)">'
            f'<div class="tile"><span class="num">{iy[0]} / {iy[1]} / {iy[2]}</span><small>İlk yarıyı önde / berabere / geride '
            f'bitirdi ({yuz(iy[0])} önde)</small></div>'
            f'<div class="tile"><span class="num">{iky[0]} / {iky[1]} / {iky[2]}</span><small>İkinci yarıyı kazandı / berabere / '
            f'kaybetti ({yuz(iky[0])} kazandı)</small></div>'
            f'<div class="tile"><span class="num">{ag[0]} – {ag[1]}</span><small>Attığı gol: ilk yarı – ikinci yarı</small></div>'
            f'<div class="tile"><span class="num">{yg[0]} – {yg[1]}</span><small>Yediği gol: ilk yarı – ikinci yarı</small></div>'
            '</div>'
            f'<div class="cap">{n} lig maçının devre skorundan. Geride kapattığı ilk yarıdan sonra kaybetmediği maç: '
            f'{geri_donus}; önde kapattığı ilk yarıdan sonra kazanamadığı maç: {onu_kacirdi}. Yalnızca bilgi: takımların '
            'yarı eğilimleri sezon içinde pek sürmüyor (büyük ölçüde şans), bu yüzden tahmine katılmıyor; maç tahminindeki '
            '"İlk yarı" kutuları modelin beklenen gollerinden.</div>')

    def xg_ciz(ad, maclar):
        """Takımın maç maç ürettiği ve verdiği xG ile 5 maçlık ortalamaları; altında hak edilen puan."""
        benim = [m for m in maclar if ad in (m[1], m[2])] if ad else []
        xg_bolum.set_visibility(len(benim) >= 3)
        if len(benim) < 3:
            return
        uret = [m[5] if m[1] == ad else m[6] for m in benim]
        ver = [m[6] if m[1] == ad else m[5] for m in benim]
        ort = lambda s, i: round(sum(s[max(0, i - 4):i + 1]) / len(s[max(0, i - 4):i + 1]), 2)  # noqa: E731
        xg_grafik.options['xAxis']['data'] = [f'{m[0][8:10]}.{m[0][5:7]} {(m[2] if m[1] == ad else m[1])[:10]}'
                                              + (' (e)' if m[1] == ad else ' (d)') for m in benim]
        xg_grafik.options['series'][0]['data'] = [round(x, 2) for x in uret]
        xg_grafik.options['series'][1]['data'] = [round(x, 2) for x in ver]
        xg_grafik.options['series'][2]['data'] = [ort(uret, i) for i in range(len(uret))]
        xg_grafik.options['series'][3]['data'] = [ort(ver, i) for i in range(len(ver))]
        xg_grafik.update()
        hp = hak_edilen_puan([m[1:] for m in benim]).get(ad, {})
        fark = hp.get('P', 0) - hp.get('xP', 0)
        xg_not.text = (f'{len(benim)} maç: maç başına {fmt(sum(uret) / len(uret), 2)} xG üretip {fmt(sum(ver) / len(ver), 2)} '
                       f'verdi. Hak edilen puan {fmt(hp.get("xP", 0), 1)}, gerçek puan {hp.get("P", 0)} ('
                       + ('şanslı' if fark >= SANS_ESIK else 'şanssız' if fark <= -SANS_ESIK else 'dengeli')
                       + '). Çubuklar maç maç, çizgiler '
                       '5 maçlık ortalama: yeşil çizgi yükseliyor ve kırmızı iniyorsa takım gerçekten iyileşiyor.')

    def ciz(v, oyuncular, onceki):
        tid = v['id']
        yildiz_ciz()
        oynanan = [m for m in v['maclar'] if m['skor'] and not m['iptal']]
        gelecek = [m for m in v['maclar'] if not m['skor'] and not m['iptal']]
        form = ''.join(_rozet(m['sonuc']) for m in oynanan[-5:])
        lig_sira = ''
        S = d.get('S')
        if S:
            bulunan = G.depo.takim_ligi(tid)
            sira = next((k + 1 for k, r in enumerate(S.tablo) if bulunan and r['name'] == bulunan[1]), None)
            if sira:
                r = S.tablo[sira - 1]
                lig_sira = f' · Ligde {sira}. sıra ({r["P"]} puan, {r["O"]} maç)'
        elo = f' · Kulüp Elo\'su {round(d["E"].puan(tid))}' if d.get('E') else ''
        avr = ''.join(f' · {e(x)}' for x in d.get('avrupa_sira') or [])
        ust.content = (f'<div class="tk-baslik">{logo_html(takim_logo_url(tid, "small"), "tk-logo")}'
                       f'<div><div class="disp" style="font-size:2rem;font-weight:700;line-height:1.1">{e(v["ad"])}</div>'
                       f'<div class="cap">{e(takim.LIG_ADI.get(v["lig_id"], v["lig"]))}{lig_sira}{avr}{elo}'
                       + (f' · Teknik direktör: {e(v["teknik"])}' if v['teknik'] else '') + '</div>'
                       f'<div style="margin-top:4px"><span class="cap">Form, son 5 maç (bütün kulvarlar, soldan sağa eskiden yeniye): '
                       f'</span><span class="form">{form}</span></div>'
                       '</div></div>')
        son5.content = ''.join(satir(m, tid) for m in reversed(oynanan[-5:])) or '<p class="cap">Oynanmış maç yok.</p>'
        siradaki.content = ''.join(satir(m, tid, tahminli=True) for m in gelecek[:5]) or '<p class="cap">Planlanmış maç yok.</p>'
        liderler_ciz(v)
        kulvarlar = {k: ad for k, ad in takim.KATEGORI if any(m['kategori'] == k for m in v['maclar'])}
        kulvar.set_options(kulvarlar, value=next(iter(kulvarlar), None))
        liste_ciz()
        # ilk 11'ler
        no = {takim.sadelestir(k['ad']): k['no'] for k in v['kadro']}
        if oyuncular:
            dizilis = (v['son_ilk11'] or {}).get('dizilis') or '4-2-3-1'
            on1 = takim.en_cok_oynayan(oyuncular, dizilis, onceki)  # onceki: takımın bu sezonki maç sayısı
            supheli = {p['n'] for p in oyuncular if p.get('_supheli')}
            for p in on1:
                p['sakat'] = p['ad'] in supheli  # sahada ✚ ile işaretlenir
                p['no'] = no.get(takim.sadelestir(p['ad']), '')
            disarida = d.get('ilk11_sakat') or []
            d['ilk11']['cok'] = (on1, f'Yalnızca bu sezon oynamış oyuncular; her mevkiye, bu sezonki FotMob puanı ve süre '
                                      f'payına göre en iyisi konur (puan × √süre payı), takımın son dizilişinde ({e(dizilis)}). '
                                      + (f'Sakat oldukları için dışarıda: {e(", ".join(disarida))}. ' if disarida else '')
                                      + '✚: şüpheli.')
        if v['son_ilk11']:
            s = v['son_ilk11']
            z = yerel(s['zaman'])
            d['ilk11']['son'] = (s['oyuncular'], f'Son maçın ilk 11\'i ({e(s["dizilis"])})' +
                                 (f', {kisa_gun(z.date())} · rakip {e(s["rakip"])}' if z else '') + '.')
        secenek = {k: ad for k, ad in (('cok', 'En güçlü 11 (bu sezon)'), ('son', 'Son maçın 11\'i')) if k in d['ilk11']}
        ilk11_sec.set_options(secenek, value=next(iter(secenek), None))
        ilk11_ciz()
        sk = [k for k in v['kadro'] if k['sakat']]
        sakatlar.content = ('<div class="liste">' + ''.join(
            f'<div class="tk-oyuncu"><span><span class="link" data-oyuncu="fm:{k["id"]}">{e(k["ad"])}</span> '
            f'<span class="cap">{e(k["mevki"])}</span></span>'
            f'<span class="cap">{"" if k["sakat"] == "Doubtful" else "dönüş: "}{e(takim.donus_metni(k["sakat"]))}</span></div>'
            for k in sk) + '</div>') if sk else '<p class="cap">Bilinen sakat yok.</p>'
        gruplar = {}
        for k in v['kadro']:
            gruplar.setdefault(k['grup'], []).append(k)
        def oyuncu(k):
            sakat_isaret = ' <span class="sakat-isaret" title="Sakat">✚</span>' if k['sakat'] else ''
            bilgi = ' · '.join(x for x in (k['mevki'], f'{k["yas"]} yaş' if k['yas'] else '', f'{k["gol"]} gol' if k['gol'] else '') if x)
            return (f'<div class="tk-oyuncu"><span><b class="tk-no">{e(k["no"] or "")}</b> '
                    f'<span class="link" data-oyuncu="fm:{k["id"]}">{e(k["ad"])}</span>{sakat_isaret}</span>'
                    f'<span class="cap">{e(bilgi)}</span></div>')
        kadro.content = ''.join(f'<div class="tk-grup">{GRUP_ADI.get(g, g)}</div>' + ''.join(oyuncu(k) for k in ks)
                                for g, ks in gruplar.items())

    G.takim_ac = lambda anahtar: G.arka_plan(ac(anahtar))
    return ac
