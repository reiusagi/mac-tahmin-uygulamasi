"""Oyuncu kartı penceresi: özet, mevkidaşlara göre yüzdelikler, ayrıntılar, benzer oyuncular ve sezon geçmişi."""
import logging

from nicegui import run, ui

from .. import lig_maclari, oyuncu_tahmin, takim
from . import takip
from ..bicim import para as _para
from ..logo import logo_html, takim_logo_url
from ..mac_ozeti import fiziksel_yazi
from ..sezon import (BUYUK_MAC, EK, HAVA_HAKIMI, LIGLER, OZEL_ROLLER, POS, SON_SEZON, TAKVIM_YILI, benzer_esik,
                     benzer_oyuncular, kariyer, mevki_adi, sezon_etiketi, yas_hesap, yas_metni)
from .ortak import e, fmt, hata_metni, ilk_kucuk, kucuk, lig_bilgi, sayi, takim_link, takim_tiklama, yuzde

logger = logging.getLogger(__name__)

# "Ayrıntılar"da toplamın yanına 90 dakika başına değeri de yazılan istatistikler: sezon toplamı olan ek istatistikler
# (top çalma, uzaklaştırma, kurtarış…) ve şut, kilit pas. Maç sayısı gibi 90 dakikaya çevrilmesi anlamsız olanlar hariç.
DOKSAN = {ad for ad, tur in EK.values() if tur == 't'} - {'Gol yemeden maç'} | {'Şut', 'Kilit pas'}
FIZIKSEL_LIGLER = {'EPL'}  # FotMob'un fiziksel veri (koşu, sprint, hız) verdiği ligler
BENZER_SUZGEC = {'': 'Hepsi', 'genc': 'Daha genç', 'ucuz': 'Daha ucuz'}  # "daha ucuz" yalnızca süren sezonda
BENZER_ADET = 8
GELISIM_SEZON = 10  # gelişim grafiğinde en çok bu kadar son sezon
GELISIM_TREND_DK = 900  # gelişim eğilimi (yükselişte / düşüşte) yalnızca en az bu kadar oynanan sezonlardan
SUT_RENK = {'Goal': '#2f7a57', 'AttemptSaved': '#35598a', 'Post': '#c9960f', 'Miss': '#8a9088'}
SUT_AD = {'Goal': 'Gol', 'AttemptSaved': 'İsabetli (kurtarıldı)', 'Post': 'Direk', 'Miss': 'İsabetsiz'}
DURUM_AD = {'RegularPlay': 'açık oyun', 'FastBreak': 'hızlı hücum', 'SetPiece': 'duran top', 'FromCorner': 'korner',
            'Penalty': 'penaltı', 'FreeKick': 'serbest vuruş', 'ThrowInSetPiece': 'taç'}


def _sut_haritasi(sutlar):
    """Rakip yarı saha (kale üstte) üzerinde şutlar: FotMob x 0-105 (rakip kale 105), y 0-68 → SVG (y, 105 − x)."""
    cizgi = 'fill="none" stroke="currentColor" stroke-opacity=".35" stroke-width=".35"'
    saha = (f'<rect x="0" y="0" width="68" height="52.5" {cizgi}/>'
            f'<rect x="13.84" y="0" width="40.32" height="16.5" {cizgi}/>'
            f'<rect x="24.84" y="0" width="18.32" height="5.5" {cizgi}/>'
            f'<path d="M 26.7 16.5 A 9.15 9.15 0 0 0 41.3 16.5" {cizgi}/>'
            f'<circle cx="34" cy="11" r=".4" fill="currentColor" fill-opacity=".4"/>'
            f'<path d="M 24.85 52.5 A 9.15 9.15 0 0 1 43.15 52.5" {cizgi}/>'
            '<rect x="30.34" y="-1.2" width="7.32" height="1.2" fill="currentColor" fill-opacity=".45"/>')
    noktalar = []
    for s in sorted(sutlar, key=lambda s: s['sonuc'] == 'Goal'):  # goller üstte
        r = 0.7 + 3.2 * max(s['xg'] or 0, 0) ** 0.5
        renk = SUT_RENK.get(s['sonuc'], '#8a9088')
        dolu = s['sonuc'] in ('Goal', 'AttemptSaved', 'Post')
        baslik = (f'{s["dk"]}. dk · {s.get("rakip") or ""} · {SUT_AD.get(s["sonuc"], s["sonuc"])} · xG {fmt(s["xg"] or 0, 2)}'
                  f' · {DURUM_AD.get(s["durum"], s["durum"] or "")}')
        noktalar.append(f'<circle cx="{s["y"]:.2f}" cy="{105 - s["x"]:.2f}" r="{r:.2f}" fill="{renk}" '
                        f'fill-opacity="{.8 if dolu else .25}" stroke="{renk}" stroke-width=".35"><title>{e(baslik)}</title></circle>')
    return (f'<svg viewBox="-1 -2 70 55" style="width:100%;max-width:340px;color:var(--ink);background:var(--panel-2);'
            f'border-radius:8px">{saha}{"".join(noktalar)}</svg>')


def kur(G):
    d = {'p': None, 'kapsam': 'lig', 'istek': 0, 'benzer_suz': ''}
    with ui.dialog().props('transition-show=fade transition-hide=fade') as dlg, \
            ui.card().classes('w-full gap-3').style('max-width:860px;background:var(--panel);color:var(--ink)'):
        with ui.row().classes('w-full items-start no-wrap'):
            with ui.column().classes('gap-0 grow'):
                ad = ui.label().classes('disp').style('font-size:2rem;font-weight:700;line-height:1.1')
                meta = ui.label().classes('cap')
                ozel = ui.html('', sanitize=False)
            rozet = ui.html('', sanitize=False).style('text-align:center')
            takip_dugme = ui.button('Takip et', icon='visibility', on_click=lambda: takip_et()).props(
                'flat dense no-caps color=accent').tooltip('Takip listene ekle: gol / asist, değer ve sözleşme bildirimleri; '
                                                          'liste Takımlarım sekmesinde')
            ui.button('Kıyasla', icon='compare_arrows', on_click=lambda: kiyasla()).props(
                'flat dense no-caps color=primary').tooltip('Bu oyuncuyu Kıyasla sekmesine ekle')
            ui.button(icon='close', on_click=dlg.close).props('flat round dense')
        # başka lig-sezonun oyuncusu açık lig değişmeden gösterilir; istenirse uygulama o sezona geçer
        gec_dugme = ui.button('', icon='open_in_new', on_click=lambda: sezona_gec()).props(
            'flat dense no-caps color=primary size=sm').tooltip('Uygulamayı bu oyuncunun lig ve sezonuna geçir')
        gec_dugme.set_visibility(False)
        kutular = ui.html('', sanitize=False).classes('w-full')
        with ui.row().classes('w-full gap-6 items-start'):
            with ui.column().classes('gap-1').style('flex:1 1 360px'):
                ui.label('Mevkidaşlarına göre').classes('disp text-lg font-bold')
                yuzdelik = ui.html('', sanitize=False).classes('w-full')
                yuzdelik_not = ui.label().classes('cap')
            with ui.column().classes('gap-1').style('flex:1 1 260px'):
                ui.label('Ayrıntılar').classes('disp text-lg font-bold')
                ayrinti = ui.html('', sanitize=False).classes('w-full')
        with ui.column().classes('w-full gap-1') as fiz_bolum:
            ui.label('Fiziksel (bu sezon)').classes('disp text-lg font-bold')
            fiz_kutu = ui.html('', sanitize=False).classes('w-full')
            fiz_not = ui.label().classes('cap')
        ui.label('Son maçları').classes('disp text-lg font-bold')
        son_not = ui.label().classes('cap')
        istikrar_not = ui.html('', sanitize=False).classes('w-full')
        son_grafik = ui.echart({
            'animation': False, 'tooltip': {'trigger': 'axis'}, 'legend': {'bottom': 0},
            'grid': {'left': 40, 'right': 40, 'top': 14, 'bottom': 56},
            'xAxis': {'type': 'category', 'data': [], 'axisLabel': {'fontSize': 10}},
            'yAxis': [{'type': 'value', 'name': 'Gol / asist', 'minInterval': 1, 'max': 3},
                      {'type': 'value', 'name': 'Puan', 'min': 4, 'max': 10, 'splitLine': {'show': False}}],
            'series': [{'name': 'Gol', 'type': 'bar', 'stack': 'ga', 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                       {'name': 'Asist', 'type': 'bar', 'stack': 'ga', 'itemStyle': {'color': '#c9960f'}, 'data': []},
                       {'name': 'FotMob puanı', 'type': 'line', 'yAxisIndex': 1, 'connectNulls': True,
                        'itemStyle': {'color': '#35598a'}, 'data': []}],
        }).classes('w-full').style('height:240px')
        son_tablo = ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:260px;overflow-y:auto')
        with ui.row().classes('w-full gap-6 items-start') as deger_sut:
            with ui.column().classes('gap-1').style('flex:1 1 300px;max-width:360px'):
                ui.label('Şut haritası (güncel sezon)').classes('disp text-lg font-bold')
                sut_kutu = ui.html('', sanitize=False).classes('w-full')
                sut_not = ui.label().classes('cap')
            with ui.column().classes('gap-1').style('flex:2 1 360px'):
                ui.label('Piyasa değeri geçmişi').classes('disp text-lg font-bold')
                deger_grafik = ui.echart({
                    'animation': False, 'tooltip': {'trigger': 'axis'},
                    'grid': {'left': 56, 'right': 16, 'top': 14, 'bottom': 30},
                    'xAxis': {'type': 'time'}, 'yAxis': {'type': 'value', 'name': 'M€', 'min': 0},
                    'series': [{'name': 'Piyasa değeri (M€)', 'type': 'line', 'step': 'end', 'showSymbol': False,
                                'areaStyle': {'opacity': .12}, 'itemStyle': {'color': '#2f7a57'}, 'data': [],
                                'markPoint': {'symbol': 'pin', 'symbolSize': 34, 'label': {'fontSize': 9}, 'data': []}}],
                }).classes('w-full').style('height:240px')
                deger_not = ui.label().classes('cap')
        deger_sut.set_visibility(False)
        with ui.row().classes('w-full items-center gap-2'):
            ui.label('Benzer oyuncular').classes('disp text-lg font-bold')
            ui.space()
            benzer_suz = ui.toggle(BENZER_SUZGEC, value='', on_change=lambda ev: suzgec_degisti(ev.value)).props(
                'dense no-caps unelevated toggle-color=primary')
            kapsam = ui.toggle({'lig': 'Bu lig', 'tum': 'Tüm ligler'}, value='lig',
                               on_change=lambda ev: kapsam_degisti(ev.value)).props('dense no-caps unelevated toggle-color=primary')
        benzer = ui.column().classes('liste')
        benzer_not = ui.label().classes('cap')
        with ui.column().classes('w-full gap-1') as gelisim_bolum:
            ui.label('Gelişim (sezon sezon, uygulamadaki ligler)').classes('disp text-lg font-bold')
            gelisim_grafik = ui.echart({
                'animation': False, 'tooltip': {'trigger': 'axis'}, 'legend': {'bottom': 0},
                'grid': {'left': 40, 'right': 44, 'top': 16, 'bottom': 60},
                'xAxis': {'type': 'category', 'data': [], 'axisLabel': {'fontSize': 10}},
                'yAxis': [{'type': 'value', 'name': 'Endeks', 'min': 0, 'max': 100},
                          {'type': 'value', 'name': 'G+A / 90', 'min': 0, 'splitLine': {'show': False}}],
                'series': [{'name': 'Performans endeksi', 'type': 'line', 'connectNulls': True, 'symbolSize': 8,
                            'lineStyle': {'width': 3}, 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                           {'name': 'Gol + asist (90 dk)', 'type': 'bar', 'yAxisIndex': 1, 'barMaxWidth': 26,
                            'itemStyle': {'color': 'rgba(201,150,15,.55)'}, 'data': []}],
            }).classes('w-full').style('height:250px')
            gelisim_not = ui.label().classes('cap')
        gelisim_bolum.set_visibility(False)
        with ui.row().classes('w-full items-center'):
            ui.label('Sezon geçmişi').classes('disp text-lg font-bold')
            ui.space()
            gecmis_gorunum = ui.toggle({'tum': 'Bütün kulvarlar', 'lig': 'Lig ayrıntısı (dakika, xG)'}, value='tum',
                                       on_change=lambda _: gorunum_degisti()).props('dense no-caps unelevated toggle-color=primary')
        tum_kutu = takim_tiklama(ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:480px;overflow-y:auto'), G)
        tum_not = ui.label().classes('cap')
        with ui.column().classes('w-full gap-0') as lig_bolum:
            kariyer_kutu = ui.column().classes('w-full gap-0 kaydir')
            kariyer_not = ui.label().classes('cap')

    def gorunum_degisti():
        tum = gecmis_gorunum.value == 'tum'
        tum_kutu.set_visibility(tum)
        tum_not.set_visibility(tum)
        lig_bolum.set_visibility(not tum)

    def kiyasla():
        if d['p'] is not None:
            dlg.close()
            G.kiyasa_ekle(d['S'].lig, d['S'].yil, d['p'])

    def sezona_gec():
        if d['p'] is not None:
            G.lige_gec(d['S'].lig, d['S'].yil, d['p']['id'])

    def takip_ciz():
        p = d['p']
        takip_dugme.set_visibility(bool(p and p.get('fm_id')))
        var = bool(p and p.get('fm_id') and takip.takipte_mi(p['fm_id']))
        takip_dugme.text = 'Takipte' if var else 'Takip et'
        takip_dugme.props(f'icon={"visibility_off" if var else "visibility"}')

    def takip_et():
        p = d['p']
        if p is None or not p.get('fm_id'):
            return
        eklendi = takip.degistir(p, d['S'].lig, d['S'].yil)
        takip_ciz()
        ui.notify(f'{p["n"]} takip listene eklendi: gol / asist, değer ve sözleşme değişikliklerinde bildirim alırsın '
                  '(liste Takımlarım sekmesinde).' if eklendi else f'{p["n"]} takip listenden çıkarıldı.')
        G.yay('takip')

    def kapsam_degisti(k):
        d['kapsam'] = k
        if d['p'] is not None:
            G.arka_plan(benzer_yukle(d['p'], d['istek']))

    def suzgec_degisti(k):
        d['benzer_suz'] = k or ''
        if d['p'] is not None:
            G.arka_plan(benzer_yukle(d['p'], d['istek']))

    async def ac(idx=None, oyuncu_id=None, S=None):
        """Oyuncunun kartı. S: oyuncunun sezonu (verilmezse açık sezon); başka lig-sezonun oyuncusu açık lig değişmeden
        gösterilir, başlıkta "bu sezona geç" düğmesi çıkar."""
        S = S or G.S
        if oyuncu_id is not None:
            p = next((q for q in S.PLY if q['id'] == oyuncu_id), None)
        else:
            p = S.PLY[idx] if 0 <= idx < len(S.PLY) else None
        if p is None:
            return
        d['p'], d['S'] = p, S
        baska = G.S is None or (G.S.lig, G.S.yil) != (S.lig, S.yil)
        gec_dugme.set_visibility(baska)
        if baska:
            gec_dugme.text = f'{lig_bilgi(S.lig)[1]} {sezon_etiketi(S.yil, S.lig)} sayfasına geç'
        d['istek'] += 1
        istek = d['istek']
        takip_ciz()
        k = S.oyuncu_karti(p)
        lg = lig_bilgi(S.lig)
        ad.text = p['n']
        mevki = mevki_adi(p)
        if p.get('pos_tahmin') == 'coklu':
            mevki += f' ({" ve ".join(kucuk(POS[x]) for x in p["adaylar"])} oynadı; ana mevki istatistiklere göre)'
        elif p.get('pos_tahmin'):
            mevki += ' (istatistiklere göre tahmini)'
        neden = S.rol_nedeni(p)
        if p.get('rol'):
            rol_metni = f'Rol: {p["rol"]}'
        elif neden == 'az süre':
            rol_metni = f'Rol yok (az süre: en az {S.roller["esik"]} dk gerekir)'
        elif neden == 'kaleci':
            rol_metni = ''  # kaleciler için rol tanımlı değil; mevki zaten "Kaleci"
        else:
            rol_metni = f'Rol yok ({neden})'
        ayr = p.get('ayrildi')
        if ayr and ayr[0]:
            tarih = f', {ayr[1][8:10]}.{ayr[1][5:7]}.{ayr[1][:4]} transfer' if ayr[1] else ''
            takim = f'{ayr[0]} (önceki kulübü {p["t"]}{tarih}; bu sezonki istatistikleri {p["t"]} formasıyla)'
        elif ayr:
            takim = f'{p["t"]} (takımdan ayrıldı; bu sezonki istatistikleri {p["t"]} formasıyla)'
        else:
            takim = p['t']
        meta.text = ' · '.join(x for x in (takim, mevki, yas_metni(p.get('yas'), S.yil), rol_metni, p['cc'],
                                           f'{lg[1]} {sezon_etiketi(S.yil, S.lig)}') if x)
        aciklama = {ad_: ac for ad_, ac, _ in OZEL_ROLLER}
        aciklama[HAVA_HAKIMI[0]] = HAVA_HAKIMI[1]
        aciklama[BUYUK_MAC[0]] = BUYUK_MAC[1]
        ozel.content = ''.join(f'<span class="ozel-rol" title="{e(aciklama.get(r, ""))}">★ {e(r)}</span>'
                               for r in p.get('ozel') or [])
        rt = k['puan']
        rozet.content = (f'<div class="disp" style="font-size:2rem;font-weight:700;color:var(--pitch)">{fmt(rt) if rt is not None else p["g"] + p["a"]}</div>'
                         f'<div class="cap">{"FotMob puanı" if rt is not None else "gol + asist"}</div>')
        kutular.content = '<div class="tiles">' + ''.join(
            f'<div class="tile"><span class="num">{v}</span><small>{l}</small></div>'
            for l, v in (('Maç', p['mp']), ('Dakika', sayi(p['min'])), ('Gol', p['g']), ('Asist', p['a']),
                         ('xG', fmt(p['xg'], 1)), ('xA', fmt(p['xa'], 1)))) + '</div>'
        if k['yuzdelik']:
            yuzdelik.content = ''.join(
                f'<div class="pctrow"><span>{e(l)} <small>{fmt(v)}</small></span><div class="track"><i style="width:{max(pc, 2)}%;'
                f'background:{"var(--pitch)" if pc >= 67 else "var(--lamp)" if pc >= 34 else "var(--draw)"}"></i></div>'
                f'<span class="pv">{pc}</span></div>' for l, v, pc in k['yuzdelik'])
            gk = p['pos'] == 'G'
            grup = 'kaleci' if gk else 'saha oyuncusu' if p['pos'] in ('S', 'U') else f'{kucuk(POS[p["pos"]])} oyuncusu'
            yuzdelik_not.text = (f'Değerler 90 dakika başına (oranlar olduğu gibi). Sağdaki sayı yüzdelik dilim: ligde en az {S.min_esik} '
                                 f'dakika oynayan {k["es_sayisi"]} {grup} arasında yüzde kaçının önünde olduğu (99: neredeyse '
                                 'hepsinden iyi, 50: ortada).'
                                 + (' Bu oyuncu az süre aldığı için oranlar yanıltıcı olabilir.' if k['az_sure'] else ''))
        else:
            yuzdelik.content = ''
            yuzdelik_not.text = 'Bu oyuncu için karşılaştırma yapılacak veri yok.'
        satirlar = []
        for etiket, v in k['detay']:
            if v is None:
                continue
            ham = v  # biçimlendirmeden önceki sayı (90 dk başına değer bundan hesaplanır)
            if etiket == 'Gol − xG':
                v = ('+' if v > 0 else '') + fmt(v, 1)
            elif etiket == 'Gol katkısı sıklığı (dk)':
                etiket, v = 'Gol katkısı sıklığı', f'{v} dakikada bir'
            elif etiket == 'Takım gollerindeki payı':
                v = yuzde(v)
            elif etiket == 'Şut başına gol':
                v = fmt(v)
            elif isinstance(v, float):
                tur = next((t for ad_, t in EK.values() if ad_ == etiket), 't')
                v = fmt(v, 2) if tur == 'r' or not v.is_integer() else int(v)
            ek = ''
            if etiket in DOKSAN and p['min'] > 0 and isinstance(ham, (int, float)) and ham:
                ek = f' <small class="cap">(90 dk\'da {fmt(ham / p["min"] * 90, 2 if abs(ham / p["min"] * 90) < 1 else 1)})</small>'
            satirlar.append(f'<dt>{e(etiket)}</dt><dd>{e(v)}{ek}</dd>')
        ayrinti.content = '<dl class="kv">' + ''.join(satirlar) + '</dl>'
        kapsam.set_value(d['kapsam'])
        # "daha ucuz": piyasa değerleri bugünkü, yalnızca süren sezonda anlamlı
        secenek = BENZER_SUZGEC if S.yil == SON_SEZON else {k: v for k, v in BENZER_SUZGEC.items() if k != 'ucuz'}
        if d['benzer_suz'] not in secenek:
            d['benzer_suz'] = ''
        benzer_suz.set_options(secenek, value=d['benzer_suz'])
        gelisim_bolum.set_visibility(False)
        benzer.clear()
        benzer_not.text = 'Benzer oyuncular aranıyor…'
        kariyer_kutu.clear()
        kariyer_not.text = 'Diğer sezonlar yükleniyor…'
        tum_kutu.content = ''
        tum_not.text = 'Bütün kulvarlardaki sezonlar alınıyor…' if p.get('fm_id') else 'Bu oyuncunun FotMob kaydı bulunamadı.'
        if not p.get('fm_id'):
            gecmis_gorunum.set_value('lig')
        gorunum_degisti()
        son_not.text = 'Son maçlar alınıyor…' if p.get('fm_id') else 'Bu oyuncunun FotMob kaydı bulunamadı.'
        son_tablo.content = ''
        son_grafik.options['xAxis']['data'] = []
        for s in son_grafik.options['series']:
            s['data'] = []
        son_grafik.update()
        fiz_kutu.content = ''
        fiz_bolum.set_visibility(S.lig in FIZIKSEL_LIGLER and S.yil == SON_SEZON and bool(p.get('fm_id')))
        dlg.open()
        if S.lig in FIZIKSEL_LIGLER and S.yil == SON_SEZON and p.get('fm_id'):
            fiz_not.text = 'Fiziksel veriler hazırlanıyor…'
            G.arka_plan(fiziksel_yukle(S, p, istek))
        G.arka_plan(benzer_yukle(p, istek))
        G.arka_plan(kariyer_yukle(p, istek))
        deger_sut.set_visibility(False)
        istikrar_not.content = ''
        if p.get('fm_id'):
            G.arka_plan(son_maclar_yukle(p, istek))
            G.arka_plan(deger_sut_yukle(p, istek))
            G.arka_plan(tum_kulvarlar_yukle(p, istek))
            if S.yil == SON_SEZON:
                G.arka_plan(istikrar_yukle(S, p, istek))

    async def istikrar_yukle(S, p, istek):
        """Maçtan maça istikrar (lig_maclari.istikrar): bu sezon ligdeki maç puanlarının dalgalanması, ligdeki
        oyuncularla kıyas. Yalnızca önceden indirilmiş maçlar (ağ isteği yok)."""
        try:
            satirlar = await run.io_bound(lig_maclari.oyuncu_satirlari, S.lig, G.depo.g.ham, None, False)
        except Exception:
            logger.debug('istikrar için maç verisi okunamadı: %s', S.lig, exc_info=True)
            return
        if istek != d['istek'] or not str(p['fm_id']).isdigit():
            return
        v = lig_maclari.istikrar(satirlar).get(int(p['fm_id']))
        istikrar_not.content = (
            f'<div class="cap"><b>Maçtan maça istikrar:</b> {e(lig_maclari.istikrar_yazisi(v))}. Bu sezon ligde en az '
            f'{lig_maclari.ISTIKRAR_MIN_DK} dakika oynadığı maçlardaki FotMob puanlarının ne kadar dalgalandığı; yüzdelik, '
            f'ligdeki oyuncuların (kalecilerde kalecilerin) yüzde kaçından daha istikrarlı olduğu. Kötü maç: '
            f'{fmt(lig_maclari.ISTIKRAR_KOTU, 1)} altı.</div>' if v else
            f'<div class="cap"><b>Maçtan maça istikrar:</b> hesaplamak için bu sezon ligde en az '
            f'{lig_maclari.ISTIKRAR_MIN_MAC} maç ({lig_maclari.ISTIKRAR_MIN_DK}+ dakika) gerekiyor.</div>')

    async def deger_sut_yukle(p, istek):
        """Piyasa değeri geçmişi ve güncel sezonun şut haritası (FotMob oyuncu sayfası; son maçlarla aynı sayfa)."""
        try:
            degerler, sutlar = await run.io_bound(takim.deger_ve_sutlar, p['fm_id'], G.depo.g.ham)
        except Exception:
            logger.debug('değer geçmişi ve şutlar alınamadı: %s', p['fm_id'], exc_info=True)
            return
        if istek != d['istek'] or (not degerler and not sutlar):
            return
        deger_sut.set_visibility(True)
        sut_kutu.content = _sut_haritasi(sutlar) if sutlar else '<p class="cap">Bu sezon şut kaydı yok.</p>'
        if sutlar:
            gol = sum(1 for s in sutlar if s['sonuc'] == 'Goal' and not s['kk'])
            isabet = sum(1 for s in sutlar if s['sonuc'] in ('Goal', 'AttemptSaved'))
            xg = sum(s['xg'] or 0 for s in sutlar)
            ceza = sum(1 for s in sutlar if s['x'] >= 88.5 and 13.84 <= s['y'] <= 54.16)
            sut_not.text = (f'{len(sutlar)} şut, {isabet} isabetli, {gol} gol · toplam xG {fmt(xg, 1)} '
                            f'(şut başına {fmt(xg / len(sutlar), 2)}) · %{round(ceza / len(sutlar) * 100)} ceza sahası içinden. '
                            'Daire büyüklüğü xG; yeşil gol, mavi isabetli, sarı direk, gri isabetsiz.')
        if degerler:
            deger_grafik.options['series'][0]['data'] = [[t, round(v / 1e6, 2)] for t, v, _ in degerler]
            # takım değişiklikleri: yeni takımın ilk ayına işaret
            isaret = [{'coord': [t, round(v / 1e6, 2)], 'value': tk[:10]}
                      for k, (t, v, tk) in enumerate(degerler) if k and tk != degerler[k - 1][2]]
            deger_grafik.options['series'][0]['markPoint']['data'] = isaret[-6:]
            deger_grafik.update()
            en = max(degerler, key=lambda x: x[1])
            deger_not.text = (f'Şu an {_para(degerler[-1][1])}; en yüksek {_para(en[1])} ({en[0][5:7]}.{en[0][:4]}). '
                              f'Aylık, FotMob\'un değer tahmini (SciSports); işaretler takım değişikliği.')
        else:
            deger_not.text = 'Değer geçmişi yok.'

    async def fiziksel_yukle(S, p, istek):
        """Sezonluk fiziksel veriler (maç maç FotMob verisinden; lig_maclari.fiziksel_ozet) ve ligdeki yüzdelik sırası."""
        def ilerleme(k, n):
            if istek == d['istek']:
                fiz_not.text = f'Ligin maç verisi hazırlanıyor… {k}/{n} (ilk açılışta bir kez indirilir)'
        try:
            satirlar = await run.io_bound(lig_maclari.oyuncu_satirlari, S.lig, G.depo.g.ham, ilerleme)
        except Exception:
            logger.warning('ligin maç verisi alınamadı: %s', S.lig, exc_info=True)
            satirlar = []
        if istek != d['istek']:
            return
        oz = lig_maclari.fiziksel_ozet(satirlar)
        o = oz.get(int(p['fm_id'])) if str(p['fm_id']).isdigit() else None
        if not o:
            fiz_kutu.content = ''
            fiz_not.text = 'Bu oyuncu için fiziksel veri yok (bu sezon ligde oynadığı maçlarda kaydedilmemiş).'
            return
        havuz = [x for x in oz.values() if x['dk'] >= lig_maclari.FIZIKSEL_MIN_DK]

        def sira(k):
            if o['dk'] < lig_maclari.FIZIKSEL_MIN_DK or len(havuz) < 10:
                return ''
            alt = sum(1 for x in havuz if x[k] < o[k])
            return f'<small style="display:block">ligde yüzdelik: {round(alt / len(havuz) * 100)}</small>'
        fiz_kutu.content = '<div class="tiles">' + ''.join(
            f'<div class="tile"><span class="num">{v}</span><small>{a}</small>{s}</div>' for a, v, s in (
                ('En yüksek hız', fiziksel_yazi('hiz', o['hiz']), sira('hiz')),
                ('Koşu (90 dk)', fiziksel_yazi('mesafe', o['mesafe90']), sira('mesafe90')),
                ('Sprint (90 dk)', fmt(o['sprint90'], 1), sira('sprint90')),
                ('Toplam koşu', fiziksel_yazi('mesafe', o['mesafe']), ''),
                ('Toplam sprint', str(o['sprint']), ''),
                ('Sprint mesafesi', fiziksel_yazi('sprint_m', o['sprint_m']), ''))) + '</div>'
        fiz_not.text = (f'{o["mac"]} maç, {sayi(o["dk"])} dakika. Kaynak FotMob (şimdilik yalnızca Premier League\'de var). '
                        f'Kıyas: ligde en az {lig_maclari.FIZIKSEL_MIN_DK} dakika oynamış {len(havuz)} oyuncu. Sprint: '
                        'yüksek hızdaki koşular; en yüksek hız sezonun tek maçındaki en iyisi.')

    def kilometre_taslari(sezonlar):
        """Kariyer toplamları (kulüp ve milli takım) ve yaklaşan yuvarlak sayılar: '100. kulüp golüne 3 gol kaldı'."""
        esikler = [10, 25, 50, 75, 100, 150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900, 1000]
        toplam, son_yil = {}, {}
        for s in sezonlar:
            t = toplam.setdefault(s['grup'], {'mac': 0, 'gol': 0, 'asist': 0})
            for k in t:
                t[k] += s[k]
            yil = s['sezon'][:4]
            if yil.isdigit():
                son_yil[s['grup']] = max(son_yil.get(s['grup'], 0), int(yil))
        notlar = []
        for grup, t in toplam.items():
            # yaklaşan sayı yalnızca hâlâ oynayana: kulüpte son iki sezon, milli takımda son üç yıl içinde oynamış
            if son_yil.get(grup, 0) < SON_SEZON - (1 if grup == 'Kulüp' else 2):
                continue
            onek = 'kulüp' if grup == 'Kulüp' else 'milli takım'
            for k, ad, yakin in (('mac', 'maçına', 10), ('gol', 'golüne', 5), ('asist', 'asistine', 5)):
                sonraki = next((x for x in esikler if x > t[k]), None)
                if sonraki and t[k] >= 5 and sonraki - t[k] <= yakin:
                    kalan = sonraki - t[k]
                    birim = {'mac': 'maç', 'gol': 'gol', 'asist': 'asist'}[k]
                    notlar.append(f'{sonraki}. {onek} {ad} {kalan} {birim} kaldı')
        ozet = ' · '.join(f'{"Kulüp" if g == "Kulüp" else "Milli takım"}: {t["mac"]} maç, {t["gol"]} gol, {t["asist"]} asist'
                          for g, t in toplam.items())
        return (f'<div class="kariyer-ozet"><b>Kariyer</b> · {e(ozet)}'
                + (''.join(f'<div class="kilometre">🎯 {e(n)}</div>' for n in notlar)) + '</div>')

    async def tum_kulvarlar_yukle(p, istek):
        """FotMob kariyer bilgisi: sezon sezon, takım takım toplam ve altında kulvar kulvar (lig, kupa, Avrupa…)."""
        try:
            sezonlar = await run.io_bound(takim.oyuncu_kariyeri, p['fm_id'], G.depo.g.ham)
        except Exception as ex:
            if istek == d['istek']:
                tum_not.text = f'Kariyer bilgisi alınamadı: {hata_metni(ex, "kariyer bilgisi")}'
            return
        if istek != d['istek']:
            return
        if not sezonlar:
            tum_not.text = 'FotMob\'da kariyer bilgisi yok.'
            return

        def puan(x):
            if not x:
                return '–'
            renk = 'var(--pitch-2)' if x >= 7.5 else 'var(--lamp)' if x >= 6.5 else 'var(--bad)'
            return f'<span style="font-weight:700;color:{renk}">{fmt(x, 2)}</span>'

        satirlar, grup0 = [], None
        for s in sezonlar:
            if s['grup'] != grup0:
                grup0 = s['grup']
                satirlar.append(f'<tr class="kr-grup"><td colspan="6">{"Kulüp kariyeri" if grup0 == "Kulüp" else "Milli takım"}</td></tr>')
            logo = logo_html(takim_logo_url(s['takim_id']), bos='')
            logo = logo + ' ' if logo else ''
            takim_ad = takim_link(s['takim'], s['takim_id']) if s['takim_id'] and s['grup'] == 'Kulüp' else e(s['takim'])
            # tek kulvar: alt satır toplamı tekrarlamasın, kulvarın adı takımın yanına yazılır
            tek_kulvar = f' <span class="cap">· {e(s["turnuvalar"][0]["ad"])}</span>' if len(s['turnuvalar']) == 1 else ''
            kiralik = ' <span class="cap">(kiralık)</span>' if s['kiralik'] else ''
            satirlar.append(f'<tr class="kr-sezon"><td>{e(s["sezon"])}</td><td>{logo}{takim_ad}{kiralik}{tek_kulvar}</td>'
                            f'<td>{s["mac"]}</td><td>{s["gol"]}</td><td>{s["asist"]}</td><td>{puan(s["puan"])}</td></tr>')
            if len(s['turnuvalar']) > 1:
                for t in s['turnuvalar']:
                    satirlar.append(f'<tr class="kr-kulvar"><td></td><td>{e(t["ad"])}{" (hazırlık)" if t["hazirlik"] else ""}</td>'
                                    f'<td>{t["mac"]}</td><td>{t["gol"]}</td><td>{t["asist"]}</td><td>{puan(t["puan"])}</td></tr>')
        tum_kutu.content = (kilometre_taslari(sezonlar)
                            + '<table class="tb kariyer-tablo"><thead><tr><th>Sezon</th><th>Takım / kulvar</th><th>Maç</th><th>Gol</th>'
                            '<th>Asist</th><th>Puan</th></tr></thead><tbody>' + ''.join(satirlar) + '</tbody></table>')
        tum_not.text = ('Kaynak: FotMob. Her sezonda takımla oynadığı bütün kulvarlar (lig, yerel kupa, Avrupa kupaları…) ve '
                        'toplamı; uygulamada olmayan ligler dahil. Puan: FotMob maç puanı ortalaması. Dakika ve xG için '
                        '"Lig ayrıntısı"na geç.')

    async def son_maclar_yukle(p, istek):
        """FotMob'dan son maçlar: maç maç gol, asist ve puan grafiği ve tablo (bütün kulvarlar ve milli takım)."""
        try:
            maclar = await run.io_bound(takim.oyuncu_son_maclar, p['fm_id'], G.depo.g.ham)
        except Exception as ex:
            if istek == d['istek']:
                son_not.text = f'Son maçlar alınamadı: {hata_metni(ex, "son maçlar")}'
            return
        if istek != d['istek']:
            return
        maclar = maclar[-25:]
        if not maclar:
            son_not.text = 'FotMob\'da son maç kaydı yok.'
            return
        puanlar = [m['puan'] for m in maclar if m['puan']]
        # form endeksi (uygulamanın hesabı): son 5 maçın puan ortalaması, son 25 maçın ortalamasıyla karşılaştırılır
        son5 = [m['puan'] for m in maclar if m['puan'] and m['dk'] >= 20][-5:]
        form = ''
        if len(son5) >= 3 and puanlar:
            f5, genel = sum(son5) / len(son5), sum(puanlar) / len(puanlar)
            durum = 'formda ↑' if f5 - genel >= 0.25 else 'düşüşte ↓' if f5 - genel <= -0.25 else 'normal'
            form = f' Form: son {len(son5)} maç ortalaması {fmt(f5)} (genel {fmt(genel)}) → {durum}.'
        son_not.text = (f'Son {len(maclar)} maç (bütün kulvarlar ve milli takım): {sum(m["gol"] for m in maclar)} gol, '
                        f'{sum(m["asist"] for m in maclar)} asist, {sum(m["dk"] for m in maclar)} dakika'
                        + (f', ortalama FotMob puanı {fmt(sum(puanlar) / len(puanlar))}' if puanlar else '') + '.' + form
                        + ' Puanlar FotMob\'un, form uygulamanın hesabı (fark en az ±0,25 puansa).')
        son_grafik.options['xAxis']['data'] = [f'{m["zaman"][8:10]}.{m["zaman"][5:7]} {m["rakip"][:10]}' for m in maclar]
        son_grafik.options['series'][0]['data'] = [m['gol'] for m in maclar]
        son_grafik.options['series'][1]['data'] = [m['asist'] for m in maclar]
        son_grafik.options['series'][2]['data'] = [m['puan'] for m in maclar]
        son_grafik.update()
        satirlar = []
        for m in reversed(maclar):
            biz, onlar = (m['skor'][0], m['skor'][1]) if m['ev'] else (m['skor'][1], m['skor'][0])
            sonuc = '' if biz is None else 'G' if biz > onlar else 'B' if biz == onlar else 'M'
            puan = m['puan']
            renk = '' if not puan else 'var(--pitch-2)' if puan >= 7.5 else 'var(--lamp)' if puan >= 6.5 else 'var(--bad)'
            satirlar.append(
                f'<tr><td class="cap">{m["zaman"][8:10]}.{m["zaman"][5:7]}.{m["zaman"][:4]}</td><td class="cap">{e(m["turnuva"])}</td>'
                f'<td>{e(m["takim"])} – {e(m["rakip"])} <span class="cap">({"ev" if m["ev"] else "dep."})</span></td>'
                f'<td>{"" if biz is None else f"{biz}–{onlar}"} <span class="form">{f"<i class={sonuc}>{sonuc}</i>" if sonuc else ""}</span></td>'
                f'<td>{m["dk"]}\'</td><td>{m["gol"] or ""}</td><td>{m["asist"] or ""}</td>'
                f'<td style="font-weight:700;color:{renk}">{fmt(puan, 1) if puan else "–"}</td></tr>')
        son_tablo.content = ('<table class="tb"><thead><tr><th>Tarih</th><th>Turnuva</th><th>Maç</th><th>Skor</th><th>Dk</th>'
                             '<th>Gol</th><th>Asist</th><th>Puan</th></tr></thead><tbody>' + ''.join(satirlar) + '</tbody></table>')

    def benzer_suz_uygula(S, p, sonuc):
        """Benzer oyuncular süzgeci: 'genc' kendisinden genç, 'ucuz' piyasa değeri kendisinden düşük (değeri bilinenler).
        Döner: [(oyuncu, lig, benzerlik, yaş, değer)] (en çok BENZER_ADET)."""
        degerler = {}
        out = []
        for q, lig_anahtar, b in sonuc:
            yas = q.get('yas') if lig_anahtar == S.lig else yas_hesap(q.get('dogum'), S.yil, lig_anahtar in TAKVIM_YILI)
            if lig_anahtar not in degerler:
                degerler[lig_anahtar] = G.depo.degerler_onbellek(lig_anahtar) if S.yil == SON_SEZON else {}
            fm = q.get('fm_id')
            dg = degerler[lig_anahtar].get(int(fm)) if str(fm).isdigit() else None
            if d['benzer_suz'] == 'genc' and not (yas is not None and p.get('yas') is not None and yas < p['yas']):
                continue
            if d['benzer_suz'] == 'ucuz' and not (dg and d.get('deger') and dg < d['deger']):
                continue
            out.append((q, lig_anahtar, b, yas, dg))
            if len(out) >= BENZER_ADET:
                break
        return out

    async def benzer_yukle(p, istek):
        S = d['S']
        r = await run.io_bound(benzer_oyuncular, S, p, G.depo.veri_klasoru, d['kapsam'] == 'tum', None)
        if istek != d['istek'] or d['S'] is not S or r is None:
            return
        benzer.clear()
        if r.get('kaleci'):
            benzer_not.text = 'Bu ligin veri kaynağı kaleciler için ayrıntılı istatistik vermediği için karşılaştırma yapılamıyor.'
            return
        esik = benzer_esik(S)
        if r.get('yok'):
            benzer_not.text = (f'Benzer oyuncu araması için en az {esik} dakika gerekiyor.' if p['min'] < esik
                               else 'Bu oyuncu için karşılaştırma yapılacak yeterli veri yok.')
            return
        fm = p.get('fm_id')
        d['deger'] = (G.depo.degerler_onbellek(S.lig).get(int(fm)) if S.yil == SON_SEZON and str(fm).isdigit() else None)
        if d['benzer_suz'] == 'ucuz' and not d['deger']:
            benzer_not.text = 'Bu oyuncunun piyasa değeri bilinmediği için "daha ucuz" süzgeci uygulanamıyor.'
            return
        liste = benzer_suz_uygula(S, p, r['sonuc'])
        if not liste:
            benzer_not.text = 'Bu süzgeçle benzer oyuncu bulunamadı; "Tüm ligler"i dene.'
            return
        with benzer:
            for q, lig_anahtar, b, yas, dg in liste:
                pc = max(0, round(b * 100))
                l = lig_bilgi(lig_anahtar)
                with ui.element('div').classes('satir'):
                    with ui.element('div'):
                        if lig_anahtar == S.lig:
                            ui.button(q['n'], on_click=lambda _, i=q['idx']: G.arka_plan(ac(idx=i, S=S))).props(
                                'flat dense no-caps').classes('link')
                        else:
                            ui.button(q['n'], on_click=lambda _, k=lig_anahtar, i=q['id']: G.git(k, S.yil, i)).props(
                                'flat dense no-caps').classes('link')
                        ui.html(f'<small>{e(q["t"])} · {e(mevki_adi(q))}'
                                + (f' · {yas} yaş' if yas is not None else '') + (f' · {_para(dg)}' if dg else '')
                                + (f' · {e(l[1])} ({e(l[2])})' if lig_anahtar != S.lig else '')
                                + f' · {q["g"]} gol, {q["a"]} asist</small>', sanitize=False)
                    ui.html(f'<div class="track"><i style="width:{pc}%"></i></div>', sanitize=False)
                    ui.label(f'{pc}%').classes('pv')
        tanim = ', '.join(ilk_kucuk(t[1]) for t in r['tanimlar'])
        benzer_not.text = (f'Benzerlik; {tanim} değerlerinin (90 dakika başına) '
                           + ('bu ligde' if d['kapsam'] == 'lig' else 'aynı veri kaynağındaki liglerde')
                           + f' en az {esik} dakika oynayan {r["n"]} oyuncu arasındaki konumuna göre hesaplanır; '
                             'hem oyun tarzı hem üretim düzeyi benzer olmalı.'
                           + ({'genc': f' Yalnızca kendisinden ({p.get("yas")} yaş) genç olanlar.',
                               'ucuz': f' Yalnızca piyasa değeri kendisinden ({_para(d["deger"]) if d.get("deger") else "–"}) '
                                       'düşük olanlar (FotMob değeri).', '': ''}[d['benzer_suz']])
                           + (' Bu oyuncu az süre aldığı için sonuçlar yanıltıcı olabilir.' if p['min'] < esik else ''))

    async def gelisim_yukle(satirlar, istek):
        """Sezon sezon performans endeksi (o sezonki mevkidaşlarına göre; oyuncu_tahmin.performans_endeksi) ve 90 dakikada
        gol + asist. satirlar: kariyer() satırları (her lig-sezonda oyuncunun kendi id'si)."""
        noktalar = []
        for r in sorted(satirlar, key=lambda r: (r['yil'], r['lig']))[-GELISIM_SEZON:]:
            try:
                S2 = await run.io_bound(G.depo.sezon, r['anahtar'], r['yil'])
                endeks = await run.io_bound(oyuncu_tahmin.performans_endeksi, S2)
            except Exception:
                logger.debug('gelişim noktası hesaplanamadı: %s %s', r['anahtar'], r['yil'], exc_info=True)
                continue
            if istek != d['istek']:
                return
            q = next((x for x in S2.PLY if x['id'] == r['id'] and x['t'] == r['takim']), None) \
                or next((x for x in S2.PLY if x['id'] == r['id']), None)
            if q is None or not q['min']:
                continue
            e_ = endeks.get(q['idx']) if endeks else None
            noktalar.append((f'{sezon_etiketi(r["yil"], r["anahtar"])}\n{r["takim"][:12]}',
                             round(e_, 1) if e_ is not None else None, round((q['g'] + q['a']) / q['min'] * 90, 2), q['min']))
        if istek != d['istek'] or len(noktalar) < 2:
            return
        gelisim_grafik.options['xAxis']['data'] = [n[0] for n in noktalar]
        gelisim_grafik.options['series'][0]['data'] = [n[1] for n in noktalar]
        gelisim_grafik.options['series'][1]['data'] = [n[2] for n in noktalar]
        gelisim_grafik.update()
        gelisim_bolum.set_visibility(True)
        # eğilim yalnızca yeterli süre alınan sezonlardan (az maçlı sezonda endeks 50'ye çekilir, yanıltır)
        dolu = [n[1] for n in noktalar if n[1] is not None and n[3] >= GELISIM_TREND_DK]
        egilim = ''
        if len(dolu) >= 3:
            fark = dolu[-1] - sum(dolu[:-1]) / len(dolu[:-1])
            egilim = (f' En az {GELISIM_TREND_DK} dakika oynadığı son sezonu, önceki sezonlarının ortalamasından '
                      + (f'{fmt(fark, 0)} puan yüksek: yükselişte.' if fark >= 5
                         else f'{fmt(-fark, 0)} puan düşük: düşüşte.' if fark <= -5 else 'farksız: istikrarlı.'))
        gelisim_not.text = ('Performans endeksi (0-100): o sezon ligindeki mevkidaşlarına göre yüzdeliklerin ortalaması; az süre '
                            'alınan sezonda ortalamaya (50) çekilir, eşiğin altında süre alınan sezonda yoktur. Çubuklar 90 '
                            'dakikada gol + asist. Lig seviyeleri farklıdır: aynı endeks zor ligde daha değerlidir.' + egilim)

    async def kariyer_yukle(p, istek):
        S = d['S']
        kariyer_kutu.clear()
        if p['id'] is None:
            kariyer_not.text = 'Bu oyuncu için sezon geçmişi yok.'
            return
        satirlar = await run.io_bound(kariyer, G.depo.veri_klasoru, S.src, p['id'], p.get('fm_id'))
        if istek != d['istek'] or d['S'] is not S or satirlar is None:
            return
        with kariyer_kutu:
            with ui.element('div').classes('w-full').style(
                    'display:grid;grid-template-columns:90px minmax(0,1.2fr) minmax(0,1.4fr) repeat(6,56px);gap:2px 8px;font-size:.88rem'):
                for b in ('Sezon', 'Lig', 'Takım', 'Maç', 'Dk', 'Gol', 'xG', 'Asist', 'xA'):
                    ui.label(b).classes('cap').style('font-weight:600')
                for r in satirlar:
                    bu = r['anahtar'] == S.lig and r['yil'] == S.yil
                    etiket = sezon_etiketi(r['yil'], r['anahtar'])
                    if bu:
                        ui.label(etiket).style('font-weight:700')
                    else:
                        # o lig-sezondaki kendi id'siyle (kaynaklar arasında id değişir)
                        ui.button(etiket, on_click=lambda _, k=r['anahtar'], y=r['yil'], i=r['id']: G.git(k, y, i)).props(
                            'flat dense no-caps').classes('link')
                    for v in (r['lig'], r['takim'], r['mp'], sayi(r['min']), r['g'], fmt(r['xg'], 1), r['a'], fmt(r['xa'], 1)):
                        ui.label(str(v)).style('font-weight:700' if bu else '')
        G.arka_plan(gelisim_yukle(satirlar, istek))
        kariyer_not.text = (f'Uygulamadaki {len(LIGLER)} ligde bulunan sezonlar (veri kaynakları arasında FotMob kimliğiyle '
                            'eşleştirilir). Uygulamada olmayan liglerdeki ve kupalardaki sezonlar burada görünmez. Başka bir '
                            'sezona geçmek için sezona tıkla.')

    return ac
