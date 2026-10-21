"""Takımlarım sekmesi: favori takımlar tek ekranda. Şu an oynayan favori takımlar (canlı skor), her takımın formu, son
maçı ve sıradaki maçları; bildirim ayarı. Takım, takım sayfasındaki yıldızla eklenir (favoriler bildirim.py'de)."""
import logging

from nicegui import app, run, ui

from .. import takim
from ..bicim import para
from ..logo import logo_html, takim_logo_url
from . import bildirim, takip
from .ortak import FORM, e, hata_metni, kisa_gun, takim_link, takim_logo, takim_tiklama, yerel

logger = logging.getLogger(__name__)
ID, AD = 'takimlarim', 'Takımlarım'
TEMBEL = True  # takım sayfaları FotMob'dan: yalnızca sekme açıkken


def _rozet(s):
    return f'<i class="{s}" title="{FORM[s][1]}">{FORM[s][0]}</i>' if s else ''


def _mac(m, tid):
    z = yerel(m['zaman'])
    zaman = f'{kisa_gun(z.date())} {z:%H:%M}' if z else ''
    rakip, rakip_id = (m['dep'], m['depId']) if m['evId'] == tid else (m['ev'], m['evId'])
    skor = (f'<b>{m["skor"][0]} – {m["skor"][1]}</b> <span class="form">{_rozet(m["sonuc"])}</span>' if m['skor']
            else '<span class="durum canli"><i class="nabiz"></i>Canlı</span>' if m['canli'] else '')
    return (f'<div class="tl-mac" data-mac="{e(m["id"])}"><span class="cap">{zaman} · {e(m["turnuva"])}</span>'
            f'<span>{"" if m["evId"] == tid else "@ "}{takim_logo(rakip_id)} {e(rakip)}</span><span>{skor}</span></div>')


def kur(G):
    d = {'veri': {}}
    with ui.column().classes('panel'):
        with ui.row().classes('w-full items-center'):
            ui.html('<h3>Takımlarım</h3>', sanitize=False)
            ui.space()
            ui.button('Deneme bildirimi gönder', icon='notifications_active', on_click=lambda: deneme()).props(
                'flat dense no-caps').tooltip('Bildirimlerin nasıl göründüğünü görmek için (Windows bildirimi ve uygulama içi)')
            ui.switch('Bildirimler', value=app.storage.general.get('bildirim', True),
                      on_change=lambda ev: app.storage.general.__setitem__('bildirim', ev.value)).tooltip(
                'Favori takımların maçlarında başlama, gol ve maç sonu bildirimi (Windows bildirimi ve uygulama içinde)')
        bos = ui.label('Henüz takım eklemedin. Bir takımın adına tıkla, açılan takım sayfasında "Takımlarıma ekle"ye bas.').classes('lead')
        canli = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
        izgara = ui.element('div').classes('w-full').style(
            'display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px')
    with ui.column().classes('panel'):
        ui.html('<h3>Bildirim sesi</h3>', sanitize=False)
        ui.label('Bildirimlerde çalınacak ses. Takımlarına ayrı ses seçebilirsin (seçmezsen genel ses çalar; takip ettiğin '
                 'oyuncuların bildirimlerinde de genel ses). Kendi sesini eklemek için MP3 ya da WAV dosyası seç (en çok '
                 '5 MB): kısık düzeyde ve en çok 6 saniye çalınır.').classes('cap')
        with ui.row().classes('w-full items-center gap-3'):
            genel_ses = ui.select({}, label='Genel ses').props('outlined dense options-dense').style('min-width:240px')
            ui.button('Dinle', icon='play_arrow', on_click=lambda: bildirim.sesi_dinle(genel_ses.value)).props(
                'flat dense no-caps color=primary')
            ui.upload(label='Ses dosyası ekle (MP3 / WAV)', auto_upload=True, max_file_size=bildirim.SES_EN_BUYUK,
                      on_upload=lambda ev: ses_yuklendi(ev),
                      on_rejected=lambda: ui.notify('Dosya eklenemedi: en çok 5 MB, MP3 ya da WAV olmalı.', type='warning')
                      ).props('accept=".mp3,.wav" flat bordered dense').classes('ses-yukle').style('max-width:300px')
        takim_sesleri = ui.column().classes('w-full gap-1')

    def sesleri_ciz():
        """Genel ses ve favori takımların sesleri (bildirim.ses_ayarlari)."""
        secenek = bildirim.ses_secenekleri()
        a = bildirim.ses_ayarlari()
        genel_ses.set_options(secenek, value=a.get('genel') if a.get('genel') in secenek else 'duduk')
        takim_sesleri.clear()
        favs = bildirim.favoriler()
        with takim_sesleri:
            if not favs:
                ui.label('Takım ekleyince her birine ayrı ses seçebilirsin.').classes('cap')
            for f in favs:
                s = (a.get('takimlar') or {}).get(str(f['id']))
                with ui.row().classes('w-full items-center no-wrap gap-2'):
                    ui.html(takim_logo(f['id']), sanitize=False)
                    ui.label(f['ad']).style('min-width:180px')
                    sec = ui.select({'genel': 'Genel ses', **secenek}, value=s if s in secenek else 'genel').props(
                        'outlined dense options-dense').style('min-width:240px')
                    sec.on_value_change(lambda ev, t=f['id']: bildirim.ses_ayarla(ev.value, t))
                    ui.button(icon='play_arrow', on_click=lambda _, t=f['id']: bildirim.sesi_dinle(bildirim.ses_secimi(t))).props(
                        'flat round dense color=primary').tooltip('Dinle')

    genel_ses.on_value_change(lambda ev: bildirim.ses_ayarla(ev.value)
                              if ev.value and ev.value != bildirim.ses_ayarlari().get('genel', 'duduk') else None)

    async def ses_yuklendi(ev):
        try:
            ad = bildirim.ses_ekle(ev.file.name, await ev.file.read())
        except ValueError as ex:  # kendi yazdığımız, yol içermeyen açıklamalar (tür, sayı ve boyut sınırları)
            ui.notify(f'Ses eklenemedi: {ex}', type='warning')
            return
        except Exception as ex:
            ui.notify(f'Ses eklenemedi: {hata_metni(ex, "bildirim sesi yükleme")}', type='warning')
            return
        finally:
            ev.sender.reset()
        bildirim.ses_ayarla(ad)  # eklenen ses genel ses olur; takımlara ayrıca seçilebilir
        sesleri_ciz()
        ui.notify(f'"{ad}" eklendi ve genel bildirim sesi yapıldı.', type='positive')

    with ui.column().classes('panel'):
        ui.html('<h3>Takip ettiğim oyuncular</h3>', sanitize=False)
        ui.label('Oyuncu kartındaki "Takip et" ile eklenir. Gol ya da asist yaptığında (takımının maçı bittikten ~10 dakika '
                 'sonra), sözleşmesi son 6 aya girdiğinde ve piyasa değeri %10 ve üstü değiştiğinde bildirim gelir.').classes('cap')
        takip_kutu = ui.html('', sanitize=False).classes('w-full kaydir')

    def takip_satirlari():
        """Takip edilenlerin güncel durumu (arka planda: sezonlar gerekirse kurulur, ağ isteği yok)."""
        from ..sezon import SON_SEZON
        out = []
        for t in takip.liste():
            fm = str(t['fm_id'])
            g = takip.guncel_takim(fm)
            lig = g[0] if g else t['lig']
            p = None
            try:
                S = G.depo.sezon(lig, SON_SEZON)
                p = next((q for q in S.PLY if str(q.get('fm_id')) == fm and not q.get('ayrildi')), None)
            except Exception:
                logger.debug('takip edilen oyuncunun sezonu kurulamadı: %s', lig, exc_info=True)
            deger = G.depo.degerler_onbellek(lig).get(int(fm)) if fm.isdigit() else None
            bitis = G.depo.sozlesmeler([fm], None, False).get(fm)
            out.append({'t': t, 'takim': g[1] if g else (p['t'].split(' / ')[-1] if p else '–'), 'tid': g[2] if g else None,
                        'lig': lig, 'p': p, 'deger': deger, 'bitis': bitis})
        return out

    async def takip_ciz():
        L = takip.liste()
        if not L:
            takip_kutu.content = '<p class="cap">Henüz oyuncu takip etmiyorsun.</p>'
            return
        satirlar = await run.io_bound(takip_satirlari) or []
        d['takip'] = satirlar

        def satir(i, r):
            p = r['p']
            sezon = f'{p["g"]} gol · {p["a"]} asist · {p["min"]} dk' if p else '–'
            takim_html = takim_link(r['takim'], r['tid']) if r['tid'] else e(r['takim'])
            bitis = f'{r["bitis"][5:7]}.{r["bitis"][:4]}' if r['bitis'] else '–'
            return (f'<tr><td><span class="link" data-takip="ac:{i}">{e(r["t"]["ad"])}</span></td>'
                    f'<td class="takim-hucre">{takim_logo(r["tid"])}{takim_html}</td><td>{sezon}</td>'
                    f'<td>{para(r["deger"], "–")}</td><td>{bitis}</td>'
                    f'<td><span class="link cap" data-takip="cikar:{i}" title="Takipten çıkar">✕</span></td></tr>')
        takip_kutu.content = ('<table class="tb"><thead><tr><th>Oyuncu</th><th>Takım</th><th>Bu sezon (lig)</th><th>Değer</th>'
                              '<th>Sözleşme bitişi</th><th></th></tr></thead><tbody>'
                              + ''.join(satir(i, r) for i, r in enumerate(satirlar)) + '</tbody></table>')

    def takip_tiklandi(ev):
        """Oyuncu adı: kartı (güncel sezondaki kaydı, yoksa eklendiği sezon); ✕: takipten çıkar."""
        islem, _, sira = str(ev.args or '').partition(':')
        satirlar = d.get('takip') or []
        if not sira.isdigit() or int(sira) >= len(satirlar):
            return
        r = satirlar[int(sira)]
        if islem == 'cikar':
            takip.degistir({'fm_id': r['t']['fm_id'], 'n': r['t']['ad'], 'id': r['t']['id']}, r['t']['lig'], r['t']['yil'])
            ui.notify(f'{r["t"]["ad"]} takip listenden çıkarıldı.')
            G.arka_plan(takip_ciz())
        elif r['p'] is not None:
            from ..sezon import SON_SEZON
            G.git(r['lig'], SON_SEZON, r['p']['id'])
        else:
            G.git(r['t']['lig'], r['t']['yil'], r['t']['id'])

    takim_tiklama(takip_kutu, G)
    takip_kutu.on('click', takip_tiklandi,
                  js_handler='(e) => { const t = e.target.closest("[data-takip]"); if (t) { e.stopPropagation(); emit(t.dataset.takip); } }')

    def deneme():
        favs = bildirim.favoriler()
        ad = favs[0]['ad'] if favs else 'Takımın'
        bildirim.gonder(f'GOL! {ad}', f'Deneme bildirimi: {ad} 1 – 0 Rakip (23\')', takim=favs[0]['id'] if favs else None)
        ui.notify('Deneme bildirimi gönderildi. Windows bildirimi gelmediyse: Ayarlar → Sistem → Bildirimler\'de '
                  '"Maç Tahmin Laboratuvarı" açık mı?', timeout=8000)

    def canli_ciz():
        fav = bildirim.favori_idler()
        c = G.depo.g.canli or {}
        maclar = [m for m in c.get('maclar') or [] if {str(m.get('evId')), str(m.get('depId'))} & fav and m.get('durum') == 'canli']
        canli.content = ('<div class="disp" style="font-weight:700;margin-bottom:4px">Şu an oynanan</div>' + ''.join(
            f'<div class="tl-canli"><span class="durum canli"><i class="nabiz"></i>{e(m.get("dakika") or "Canlı")}</span> '
            f'{takim_logo(m["evId"])} {takim_link(m["ev"], m["evId"])} <b>{m.get("evGol") or 0} – {m.get("depGol") or 0}</b> '
            f'{takim_link(m["dep"], m["depId"])} {takim_logo(m["depId"])} <span class="cap">· {e(m.get("baslik") or "")}</span></div>'
            for m in maclar)) if maclar else ''

    def kart(f):
        tid = f['id']
        v = d['veri'].get(str(tid))
        with ui.element('div').classes('tl-kart'):
            with ui.row().classes('w-full items-center no-wrap gap-2'):
                ui.html(logo_html(takim_logo_url(tid, 'small'), 'tk-logo', 'width:40px;height:40px;',
                                  bos='<span class="tk-logo" style="width:40px;height:40px"></span>'), sanitize=False)
                ui.button(f['ad'], on_click=lambda _, t=tid: G.takim_ac(t)).props('flat dense no-caps').classes('link disp').style(
                    'font-size:1.2rem')
                ui.space()
                ui.button(icon='close', on_click=lambda _, t=tid, a=f['ad']: cikar(t, a)).props('flat round dense size=sm').tooltip(
                    'Takımlarımdan çıkar')
            if v is None:
                ui.label('Yükleniyor…').classes('cap')
                return
            oynanan = [m for m in v['maclar'] if m['skor'] and not m['iptal']]
            gelecek = [m for m in v['maclar'] if not m['skor'] and not m['iptal']]
            sakat = sum(1 for k in v['kadro'] if k['sakat'] and k['sakat'] != 'Doubtful')
            ui.html(f'<div class="cap">{e(takim.LIG_ADI.get(v["lig_id"], v["lig"]))}'
                    + (f' · {sakat} sakat' if sakat else '') + '</div>'
                    f'<div style="margin:4px 0"><span class="cap">Form: </span><span class="form">'
                    f'{"".join(_rozet(m["sonuc"]) for m in oynanan[-5:])}</span></div>', sanitize=False)
            maclar = ui.html('<div class="cap">Son maç</div>' + ''.join(_mac(m, tid) for m in oynanan[-1:])
                             + '<div class="cap" style="margin-top:4px">Sıradaki maçlar</div>'
                             + (''.join(_mac(m, tid) for m in gelecek[:3]) or '<div class="cap">Planlanmış maç yok.</div>'),
                             sanitize=False).classes('w-full')
            maclar.on('click', lambda ev, v=v: mac_ac(v, ev.args),
                      js_handler='(e) => { const t = e.target.closest("[data-mac]"); if (t) emit(t.dataset.mac); }')

    def mac_ac(v, mac_id):
        m = next((x for x in v['maclar'] if str(x['id']) == str(mac_id)), None)
        if m:
            G.mac_ac({'id': m['id'], 'baslik': m['turnuva'], 'grup': '', 'baslangic': m['zaman'],
                      'durum': 'canli' if m['canli'] else 'bitti' if m['bitti'] else 'baslamadi'})

    def ciz():
        favs = bildirim.favoriler()
        bos.set_visibility(not favs)
        canli_ciz()
        sesleri_ciz()
        izgara.clear()
        with izgara:
            for f in favs:
                kart(f)

    def cikar(tid, ad):
        bildirim.favori_degistir(tid, ad)
        ui.notify(f'{ad} takımlarından çıkarıldı.')
        G.arka_plan(yenile())

    async def yenile():
        ciz()
        G.arka_plan(takip_ciz())
        for f in bildirim.favoriler():
            try:
                d['veri'][str(f['id'])] = await run.io_bound(takim.takim_sayfasi, f['id'], G.depo.g.ham)
            except Exception:
                logger.warning('favori takımın sayfası alınamadı: %s', f['id'], exc_info=True)
                continue
        ciz()

    G.dinle('favoriler', lambda: G.arka_plan(yenile()))
    G.dinle('takip', lambda: G.arka_plan(takip_ciz()))
    G.dinle('canli', canli_ciz)
    return yenile
