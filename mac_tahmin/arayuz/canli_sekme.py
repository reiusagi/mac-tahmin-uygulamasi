"""Canlı skorlar sekmesi: takip edilen liglerin ve milli turnuvaların seçilen günkü maçları. Üstteki gün çubuğuyla gün
değiştirilir, süzgeçlerle yalnızca canlı, lig ya da milli maçlar gösterilir. Bugün arka planda dakikada bir yenilenir;
başka günler istenince FotMob'dan alınır. Logolar FotMob'un görsel sunucusundan (internet yoksa boş kalır)."""
import logging
import time
from datetime import date, datetime, timedelta, timezone

from nicegui import run, ui

from ..canli import LIG_ADI, gunun_maclari
from ..logo import lig_logo_url, logo_html, takim_logo_url
from ..sezon import FOTMOB_ID
from . import bildirim
from .ortak import AYLAR, e, hata_metni, tahmine_git, yerel, yuzde

logger = logging.getLogger(__name__)

ID, AD = 'canli', 'Canlı'
GUNLER = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
GELECEK_TAZELE_SN = 30 * 60  # gelecek günlerin listesi (saat, hakem) bu kadar eskiyince yeniden alınır
SUZGECLER = [('tum', 'Tümü'), ('canli', 'Canlı'), ('favori', 'Takımlarım'), ('avrupa', 'Avrupa kupaları'), ('lig', 'Ligler'),
             ('milli', 'Milli maçlar')]


def sekme_ek():
    """Sekme başlığında canlı maç sayısı rozeti."""
    rozet = ui.badge('', color='negative').props('floating rounded')
    rozet.set_visibility(False)
    return rozet


def gun_adi(g):
    ek = {0: 'Bugün', -1: 'Dün', 1: 'Yarın'}.get((g - date.today()).days)
    return (f'{ek}, ' if ek else '') + f'{g.day} {AYLAR[g.month - 1]} {g.year}, {GUNLER[g.weekday()]}'


def _lig_logo(anahtar):
    fid = int(anahtar.split('-', 1)[1]) if anahtar.startswith(('milli-', 'avrupa-', 'kupa-')) else FOTMOB_ID.get(anahtar)
    return lig_logo_url(fid) if fid else ''


def _logo(url, sinif='logo'):
    # arka plan resmi: indirilemezse kırık resim simgesi yerine boş kalır
    return logo_html(url, sinif, bos=f'<span class="{sinif}"></span>')


def _uygun(m, suzgec):
    if suzgec == 'canli':
        return m['durum'] == 'canli'
    if suzgec == 'favori':
        return bool({str(m.get('evId')), str(m.get('depId'))} & bildirim.favori_idler())
    if suzgec == 'milli':
        return m['lig'].startswith('milli-')
    if suzgec == 'avrupa':
        return m['lig'].startswith('avrupa-')
    if suzgec == 'lig':
        return not m['lig'].startswith(('milli-', 'avrupa-'))
    return True


def kur(G):
    rozet = G.ek[ID]
    d = {'gun': date.today(), 'son_bugun': date.today(), 'damga': object(), 'istek': 0, 'suzgec': 'tum', 'maclar': None,
         'olas': {}}  # olas: maç id → olasılıklar (Depo.mac_olasiliklari; arka planda hesaplanır, gelince yeniden çizilir)
    onbellek = {}  # 'YYYYMMDD' -> (alındığı an, maçlar, ayrıntılı mı)

    with ui.column().classes('panel gun-panel gap-2'):
        with ui.row().classes('w-full items-center no-wrap gap-1'):
            ui.button(icon='chevron_left', on_click=lambda: gun_degistir(d['gun'] - timedelta(days=1))).props(
                'flat round dense').tooltip('Önceki gün')
            with ui.button(icon='event').props('flat dense no-caps').classes('disp gun-dugme') as gun_dugme:
                with ui.menu() as menu:
                    takvim = ui.date(mask='YYYY-MM-DD', on_change=lambda ev: takvimden(ev.value, menu)).props(
                        'minimal first-day-of-week=1')
            ui.button(icon='chevron_right', on_click=lambda: gun_degistir(d['gun'] + timedelta(days=1))).props(
                'flat round dense').tooltip('Sonraki gün')
            bugun_dugme = ui.button('Bugün', on_click=lambda: gun_degistir(date.today())).props('outline dense no-caps size=sm')
            ui.space()
            ozet = ui.html('', sanitize=False).classes('gun-ozet')
        with ui.row().classes('w-full items-center gap-2'):
            suzgec_dugmeleri = {}
            for k, ad in SUZGECLER:
                suzgec_dugmeleri[k] = ui.button(ad, on_click=lambda _, k=k: suzgec_sec(k)).props('dense no-caps unelevated rounded').style(
                    'padding:2px 12px;font-size:.85rem')
            ui.space()
            lead = ui.label().classes('cap')
    govde = ui.column().classes('w-full gap-3')

    # ---------------------------------------------------------------- gün ve süzgeç
    def takvimden(deger, menu):
        if deger and date.fromisoformat(deger) != d['gun']:
            menu.close()
            gun_degistir(date.fromisoformat(deger))

    def gun_degistir(g):
        d['gun'] = g
        d['damga'] = object()  # yeniden çiz
        gun_dugme.set_text(gun_adi(g))
        takvim.set_value(g.isoformat())
        bugun_dugme.set_visibility(g != date.today())
        ciz(True)

    def suzgec_sec(k):
        d['suzgec'] = k
        if d['maclar'] is not None:
            maclari_ciz(d['maclar'], d.get('yakinda'))

    def suzgec_boya(ms):
        for k, ad in SUZGECLER:
            n = sum(1 for m in ms if _uygun(m, k))
            b = suzgec_dugmeleri[k]
            b.set_text(f'{ad} {n}' if n or k == 'tum' else ad)
            b.props(f'color={"primary" if d["suzgec"] == k else "grey-3"} text-color={"white" if d["suzgec"] == k else "grey-9"}')
            b.set_enabled(n > 0 or k == 'tum')

    def ciz(zorla=False):
        c = G.depo.g.canli
        canli_say = sum(1 for m in (c or {}).get('maclar', []) if m['durum'] == 'canli')
        rozet.set_text(str(canli_say))
        rozet.set_visibility(canli_say > 0)
        if d['gun'] == date.today() and (c or {}).get('tarih') in (None, date.today().strftime('%Y%m%d')):
            bugun_ciz(c, zorla)
        elif zorla:
            G.arka_plan(baska_gun(d['gun']))

    # ---------------------------------------------------------------- bugün: arka planda yenilenen veri
    def bugun_ciz(c, zorla):
        dk_metni(c)
        damga = (c or {}).get('guncellendi'), G.depo.g.canli_hata
        if damga == d['damga'] and not zorla:
            return
        d['damga'] = damga
        if not c:
            d['maclar'] = None
            ozet.content = ''
            govde.clear()
            with govde, ui.column().classes('panel'):
                ui.label('Canlı skorlar alınamadı; internet bağlantısını kontrol et. Uygulama dakikada bir yeniden dener.'
                         if G.depo.g.canli_hata else 'Canlı skorlar yükleniyor…').classes('lead')
            return
        maclari_ciz(c.get('maclar') or [], c.get('yakinda'))

    def dk_metni(c):
        if not c:
            lead.text = 'FotMob verisi, dakikada bir yenilenir.'
            return
        upd = datetime.fromisoformat(c['guncellendi'])
        dk = max(0, round((datetime.now(timezone.utc) - upd).total_seconds() / 60))
        lead.text = (f'Son güncelleme {upd.astimezone():%H:%M} ({"az önce" if dk < 1 else f"{dk} dk önce"}) · dakikada bir yenilenir'
                     + (' · son denemede bağlantı kurulamadı' if G.depo.g.canli_hata else ''))

    # ---------------------------------------------------------------- başka günler: istenince alınır
    async def baska_gun(g):
        d['istek'] += 1
        istek = d['istek']
        anahtar = g.strftime('%Y%m%d')
        gecmis = g < date.today()
        kayit = onbellek.get(anahtar)
        taze = kayit and (gecmis or time.time() - kayit[0] < GELECEK_TAZELE_SN)
        lead.text = 'Sonuçlar (FotMob)' if gecmis else 'Maç programı (FotMob)'
        if not taze:
            ozet.content = ''
            govde.clear()
            with govde, ui.row().classes('items-center gap-2'):
                ui.spinner(size='sm')
                ui.label('Maçlar alınıyor…').classes('lead')
            try:  # önce hızlı liste (hakemsiz), ardından ayrıntılar
                maclar = await run.io_bound(gunun_maclari, anahtar, stadyumlar=G.depo.stadyumlar())
            except Exception as ex:
                if istek == d['istek']:
                    govde.clear()
                    with govde, ui.column().classes('panel'):
                        ui.label(f'Maçlar alınamadı: {hata_metni(ex, "günün maçları")}').classes('lead')
                return
            kayit = (time.time(), maclar, False)
            onbellek[anahtar] = kayit
        if istek != d['istek']:
            return
        maclari_ciz(kayit[1])
        if not kayit[2] and kayit[1]:  # hakem ve maçın stadyumu (her maç için ayrı istek; önbelleğe alınır)
            lead.text += ' · hakem ve stadyum bilgisi yükleniyor…'
            try:
                ayrintili = await run.io_bound(gunun_maclari, anahtar, stadyumlar=G.depo.stadyumlar(), ham=G.depo.g.ham)
            except Exception:
                logger.warning('hakem ve stadyum bilgisi alınamadı: %s', anahtar, exc_info=True)
                return
            onbellek[anahtar] = (time.time(), ayrintili, True)
            if istek == d['istek']:
                lead.text = 'Sonuçlar (FotMob)' if gecmis else 'Maç programı (FotMob)'
                maclari_ciz(ayrintili)

    # ---------------------------------------------------------------- çizim
    async def olasiliklari_guncelle(ms, yakinda):
        """Maçların olasılıkları arka planda (ligin sezonu ilk kez kuruluyorsa birkaç saniye); değiştiyse yeniden çizilir."""
        try:
            olas = await run.io_bound(G.depo.mac_olasiliklari, ms) or {}
        except Exception:
            logger.debug('maç olasılıkları hesaplanamadı', exc_info=True)
            return
        if d['maclar'] is ms and olas != d['olas']:
            d['olas'] = olas
            maclari_ciz(ms, yakinda, hesapla=False)

    def maclari_ciz(ms, yakinda=None, hesapla=True):
        d['maclar'], d['yakinda'] = ms, yakinda
        if hesapla and ms:
            G.arka_plan(olasiliklari_guncelle(ms, yakinda))
        sayi = {k: sum(1 for m in ms if m['durum'] == k) for k in ('canli', 'bitti', 'baslamadi')}
        parca = [f'<b>{len(ms)}</b> maç']
        if sayi['canli']:
            parca.append(f'<span class="canli-yazi"><i class="nabiz"></i>{sayi["canli"]} canlı</span>')
        if sayi['bitti']:
            parca.append(f'{sayi["bitti"]} bitti')
        if sayi['baslamadi']:
            parca.append(f'{sayi["baslamadi"]} başlamadı')
        ozet.content = ' · '.join(parca) if ms else ''
        suzgec_boya(ms)
        secili = [m for m in ms if _uygun(m, d['suzgec'])]
        govde.clear()
        with govde:
            if not ms:
                with ui.column().classes('panel'):
                    ui.label('Bu tarihte takip edilen liglerde ve milli turnuvalarda maç yok.').classes('lead')
                if yakinda:
                    _lig_paneli('Önümüzdeki günler', '', [{**m, 'durum': 'baslamadi'} for m in
                                                          sorted(yakinda, key=lambda m: m.get('baslangic') or '')[:30]], tarihli=True)
                return
            if not secili:
                with ui.column().classes('panel'):
                    ui.label('Bu süzgece uyan maç yok.').classes('lead')
                return
            for k in dict.fromkeys(m['lig'] for m in secili):
                lm = [m for m in secili if m['lig'] == k]
                _lig_paneli(lm[0].get('baslik') or LIG_ADI.get(k, k), _lig_logo(k), lm)

    def _lig_paneli(ad, logo, lm, tarihli=False):
        cs = sum(1 for m in lm if m['durum'] == 'canli')
        rozet_html = (f'<span class="canli-rozet"><i class="nabiz"></i>{cs} canlı</span>' if cs
                      else f'<span class="cap">{len(lm)} maç</span>')
        with ui.column().classes('panel lig-panel gap-0'):
            ui.html(f'<div class="lig-baslik">{_logo(logo, "lig-logo")}<span class="disp">{e(ad)}</span>{rozet_html}</div>',
                    sanitize=False).classes('w-full')
            for m in lm:  # maça tıklanınca maç kartı (olaylar, istatistikler, kadrolar); olasılık satırına: maç tahmini
                ui.html(_satir({**m, '_olas': d['olas'].get(m.get('id'))}, tarihli), sanitize=False).classes('w-full').on(
                    'click', lambda ev, m=m: tahmine_git(G, m) if ev.args == 'tahmin' else G.mac_ac(m),
                    js_handler='(e) => emit(e.target.closest("[data-tahmin]") ? "tahmin" : "kart")')

    def zaman_kontrol():
        """Gece yarısını geçince 'bugün'e bakan görünüm yeni güne geçsin; bugünde "x dk önce" yazısı tazelensin."""
        bugun = date.today()
        if d['son_bugun'] != bugun:
            if d['gun'] == d['son_bugun']:
                gun_degistir(bugun)
            d['son_bugun'] = bugun
        if d['gun'] == bugun:
            ciz()

    G.dinle('canli', ciz)
    ui.timer(30, zaman_kontrol)
    gun_degistir(date.today())
    return lambda: None  # sezon değişince yapılacak bir şey yok


def _satir(m, tarihli=False):
    """Maç kartı: durum · ev sahibi (logo) · skor · deplasman (logo); altında grup, stadyum ve hakem."""
    durum = m['durum']
    oyn = durum in ('canli', 'bitti')
    z = yerel(m.get('baslangic'))
    if durum == 'canli':
        st = f'<span class="durum canli"><i class="nabiz"></i>{e(m.get("dakika") or "Canlı")}</span>'
    elif durum == 'bitti':
        st = '<span class="durum bitti">MS</span>'
    elif durum == 'iptal':
        st = '<span class="durum iptal">İptal</span>'
    else:  # başlamadı: saat ortadaki kutuda, solda (önümüzdeki günler listesinde) tarih
        st = f'<span class="durum">{f"{GUNLER[z.weekday()][:3]}<br>{z:%d.%m}" if tarihli and z else ""}</span>'
    eg, dg = (m.get('evGol') or 0), (m.get('depGol') or 0)
    ev_kaz, dep_kaz = oyn and eg > dg, oyn and dg > eg
    if oyn:
        skor = f'<span class="skor{" canli" if durum == "canli" else ""}">{eg}<i>–</i>{dg}</span>'
    else:
        skor = f'<span class="skor saat">{f"{z:%H:%M}" if z else e(m.get("saat") or "–")}</span>'
    alt = ' · '.join(e(x) for x in (m.get('baslik') if tarihli else '', m.get('grup'), m.get('stadyum'),
                                     'Hakem: ' + m['hakem']['ad'] if m.get('hakem') else '') if x)
    def tlogo(i):
        return takim_logo_url(i)

    return (f'<div class="cm {durum}">{st}'
            f'<span class="takim ev{" kaz" if ev_kaz else ""}">{e(m["ev"])}{_logo(tlogo(m.get("evId")))}</span>{skor}'
            f'<span class="takim dep{" kaz" if dep_kaz else ""}">{_logo(tlogo(m.get("depId")))}{e(m["dep"])}</span>'
            + _olas_satiri(m.get('_olas'), durum)
            + (f'<span class="alt">{alt}</span>' if alt else '') + '</div>')


def _olas_kutulari(p):
    """Ev · beraberlik · deplasman olasılık kutuları (favori yeşil, diğer taraf kırmızı)."""
    ev_s, dep_s = ('kaz', 'kay') if p[0] >= p[2] else ('kay', 'kaz')
    return (f'<span class="olas"><span class="{ev_s}">{yuzde(p[0])}</span><span class="ber">{yuzde(p[1])}</span>'
            f'<span class="{dep_s}">{yuzde(p[2])}</span></span>')


def _olas_satiri(o, durum):
    """Maçın altında olasılıklar: canlıysa skora ve kalan süreye göre "şu an" ile maç önü; başlamadıysa maç önü."""
    if not o:
        return ''
    git = '<span class="link cap">ayrıntılı tahmin ›</span>'
    if durum == 'canli' and o.get('simdi'):
        return (f'<span class="cm-olas" data-tahmin="1" title="Şu an: kalan süre ve skora göre (kırmızı kart ve oyunun akışı '
                f'hesaba katılmaz). Tıklayınca maçın ayrıntılı tahmini açılır.">'
                f'<span class="cap">Şu an</span>{_olas_kutulari(o["simdi"])}'
                f'<span class="cap">maç önü {yuzde(o["once"][0])} · {yuzde(o["once"][1])} · {yuzde(o["once"][2])}</span>{git}</span>')
    if durum == 'baslamadi':
        return (f'<span class="cm-olas" data-tahmin="1" title="Tıklayınca maçın ayrıntılı tahmini açılır.">'
                f'<span class="cap">Tahmin</span>{_olas_kutulari(o["once"])}{git}</span>')
    return ''
