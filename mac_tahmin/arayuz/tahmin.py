"""Maç tahmini sekmesi: takım seçimi, sonuç olasılıkları, skor matrisi, maç şeridi, olası golcüler ve tahmini ilk 11'ler.
Yakındaki maçlarda FotMob'un kadrosuna bakılır: açıklanmış kesin ilk 11 varsa listeler ve kadro düzeltmesi ona göre
yapılır; tahmini ilk 11 sahaları kesin kadro > FotMob'un tahmini > uygulamanın "en güçlü 11"i sırasıyla çizilir."""
import logging

from nicegui import run, ui

from .. import avrupa, lig_maclari, oyuncu_tahmin
from ..modeller import piyasalar
from ..sezon import SON_SEZON
from ..stadyum import stadyum_bul
from .ortak import e, fmt, hava_html, kisa_gun, lig_secenekleri, piyasa_kartlari, takim_logo, yerel, yuzde
from .tahmin_metin import (ASIST_ACIKLAMA, aciklama_html, bilgi_html, enolasi_ciz, golcu_metni, h2h_html, kart_metni, matris_html,
                           olasilik_html)
from .tahmin_kadro import (ILK11_NOT, alt_asist, alt_golcu, alt_kart, asist_listesi, eksik_html, golcu_listesi, ilk11_html,
                           kadro_topla, kart_listesi, kesin_ilk11, mac_kadrosu, suz)

logger = logging.getLogger(__name__)

ID, AD = 'tahmin', 'Maç tahmini'
SERIT_OYNANAN = 3  # şeritte sıradaki maçlardan önce gösterilen son oynanmış maç sayısı


async def _hava_ciz(depo, durum, S, h, a, yer):
    """Yaklaşan maçın maç saatindeki hava tahmini (yalnızca bilgi; tahmine katılmaz). Son gösterilen satır
    hatırlanır: dakikalık yenilemede satır kaybolup yeniden belirmesin."""
    try:
        hv = await run.io_bound(depo.lig_mac_havasi, S, h, a)
    except Exception:  # hava alınamazsa satır gösterilmez
        logger.debug('maç havası alınamadı', exc_info=True)
        hv = None
    icerik = hava_html(hv, kisa=True)
    durum.setdefault('hava', {})[(S.lig, h, a)] = icerik
    if not yer.is_deleted and yer.content != icerik:
        yer.content = icerik


def _canli_imza(canli, lig):
    c = canli or {}
    return tuple((m.get('id'), m.get('durum'), m.get('baslangic'), m.get('stadyum'), (m.get('hakem') or {}).get('ad'))
                 for m in (c.get('maclar') or []) + (c.get('yakinda') or []) if m.get('lig') == lig)


def _ust_bilgi(depo, S, h, a):
    """Yaklaşan maçın şeritteki ek satırları: stadyum ve (atandıysa) hakem."""
    fm = depo.canli_mac(S, h, a)
    std = {'ad': fm['stadyum']} if fm and fm.get('stadyum') else stadyum_bul(depo.stadyumlar(), S.lig, S.T[h])
    return (f'<small>{e(std["ad"])}</small>' if std else '') + (f'<small>Hakem: {e(fm["hakem"]["ad"])}</small>' if fm and fm.get('hakem') else '')


# ---------------------------------------------------------------- bölümler: her biri kendi arayüzünü ve işlevlerini kurar
def _kur_serit(G, durum, sec):
    """Haftanın maçları şeridi (en üstte: önce maç seçilir, altında analizi). sec(h, a): şeritte maça tıklanınca.
    Döner: serit_ciz (bir sonraki maçların listesi döner), serit_isaretle, tura_git."""
    with ui.row().classes('w-full items-center gap-1'):
        serit_baslik = ui.label().classes('disp text-lg font-bold')
        ui.space()
        tur_geri = ui.button(icon='chevron_left', on_click=lambda: tur_degistir(-1)).props('flat round dense').tooltip('Önceki hafta')
        tur_yazi = ui.label().classes('disp').style('min-width:84px;text-align:center;font-weight:700')
        tur_ileri = ui.button(icon='chevron_right', on_click=lambda: tur_degistir(1)).props('flat round dense').tooltip('Sonraki hafta')
    serit = ui.element('div').classes('serit')
    serit_ogeler = []

    def serit_isaretle():
        for el, (h, a) in serit_ogeler:
            if (h, a) == (durum['h'], durum['a']):
                el.classes(add='sec')
            else:
                el.classes(remove='sec')

    def tur_degistir(adim):
        turlar = durum.get('turlar') or []
        if durum.get('tur') in turlar:
            k = turlar.index(durum['tur']) + adim
            if 0 <= k < len(turlar):
                durum['tur'] = turlar[k]
                serit_ciz()
                serit_isaretle()

    def serit_ciz():
        """Süren sezonda hafta hafta (FotMob'un turları): seçili haftanın bütün maçları, ◀ ▶ ile önceki / sonraki hafta;
        açılışta sıradaki maçların haftası. Geçmiş sezonda son oynanan maçlar. Maça tıklanınca tahmini açılır."""
        S = G.S
        up = list(zip(S.U, S.raw['u'])) if S.yil == SON_SEZON else []
        fk = lig_maclari.fikstur(S.lig, G.depo.g.ham) if S.yil == SON_SEZON else []
        turlar = sorted({m['tur'] for m in fk if m['tur'] is not None})
        durum['turlar'] = turlar
        for oge in (tur_geri, tur_yazi, tur_ileri):
            oge.set_visibility(bool(turlar))
        if turlar:
            if durum.get('tur_lig') != S.lig or durum.get('tur') not in turlar:
                durum['tur_lig'] = S.lig
                durum['tur'] = next((m['tur'] for m in fk if not m['bitti'] and not m['iptal'] and m['tur'] is not None),
                                    turlar[-1])
            haftalik_serit(S, [m for m in fk if m['tur'] == durum['tur']], turlar)
            return up
        up = up[:10]
        played = S.M[-(SERIT_OYNANAN if up else 10):]
        serit_baslik.text = ('Son ve sıradaki maçlar' if played else 'Sıradaki maçlar') if up else 'Son oynanan maçlar'
        serit.clear()
        serit_ogeler.clear()
        ad = lambda i: f'{takim_logo(G.depo.takim_kimligi(S.lig, S.T[i]))}{e(S.T[i])}'  # logolu takım adı
        with serit:
            for m in played:
                with ui.element('div').classes('fx done').on('click', lambda _, h=m.h, a=m.a: sec(h, a)) as el:
                    ui.html(f'<small>{kisa_gun(m.d)} · Bitti</small><b><span>{ad(m.h)}</span><span>{m.hg}</span></b>'
                            f'<b><span>{ad(m.a)}</span><span>{m.ag}</span></b>', sanitize=False)
                serit_ogeler.append((el, (m.h, m.a)))
            for m, r in up:
                z = yerel(r[3]) if len(r) > 3 else None
                zaman = f'{kisa_gun(z.date())} · <span class="zaman">{z:%H:%M}</span>' if z else kisa_gun(m.d)
                with ui.element('div').classes('fx').on('click', lambda _, h=m.h, a=m.a: sec(h, a)) as el:
                    ui.html(f'<small>{zaman}</small><b><span>{ad(m.h)}</span></b><b><span>{ad(m.a)}</span></b>'
                            f'{_ust_bilgi(G.depo, S, m.h, m.a)}', sanitize=False)
                serit_ogeler.append((el, (m.h, m.a)))
        if not (up or played):
            serit_baslik.text = ''
        return up

    def tura_git(S, h, a):
        """Şeridi bu eşleşmenin haftasına getirir (oynanmamışı öncelikli; başka sekmeden bir maç açılınca)."""
        ids = G.depo.stadyumlar()['ligler'].get(S.lig) or {}
        eid, did = str(ids.get(S.T[h])), str(ids.get(S.T[a]))
        fk = [m for m in lig_maclari.fikstur(S.lig, G.depo.g.ham) if m['ev_id'] == eid and m['dep_id'] == did and m['tur']]
        m = next((x for x in fk if not x['bitti']), fk[-1] if fk else None)
        if m and m['tur'] != durum.get('tur'):
            durum['tur'], durum['tur_lig'] = m['tur'], S.lig
            serit_ciz()

    def haftalik_serit(S, maclar, turlar):
        """Seçili haftanın bütün maçları: oynananlar skoruyla, oynanmayanlar saatiyle (ve yaklaşanlarda stadyum / hakem)."""
        tur = durum['tur']
        tur_yazi.text = f'{tur}. hafta'
        tur_geri.set_enabled(tur != turlar[0])
        tur_ileri.set_enabled(tur != turlar[-1])
        oynanan = sum(1 for m in maclar if m['bitti'])
        serit_baslik.text = f'Haftanın maçları · {oynanan}/{len(maclar)} oynandı'
        ids = {str(v): S.T.index(k) for k, v in (G.depo.stadyumlar()['ligler'].get(S.lig) or {}).items() if k in S.T}
        serit.clear()
        serit_ogeler.clear()

        def ad(tid, yedek):
            i = ids.get(tid)
            return f'{takim_logo(tid)}{e(S.T[i] if i is not None else yedek)}'
        with serit:
            for m in maclar:
                h, a = ids.get(m['ev_id']), ids.get(m['dep_id'])
                z = yerel(m['zaman'])
                gun = f'{kisa_gun(z.date())} · <span class="zaman">{z:%H:%M}</span>' if z else ''
                if m['bitti'] and m['skor']:
                    sinif, govde = 'fx done', (f'<small>{kisa_gun(z.date()) if z else ""} · Bitti</small>'
                                               f'<b><span>{ad(m["ev_id"], m["ev_ad"])}</span><span>{m["skor"][0]}</span></b>'
                                               f'<b><span>{ad(m["dep_id"], m["dep_ad"])}</span><span>{m["skor"][1]}</span></b>')
                else:
                    ek = '<small>Ertelendi / iptal</small>' if m['iptal'] else (_ust_bilgi(G.depo, S, h, a) if h is not None and a is not None else '')
                    sinif, govde = 'fx', (f'<small>{gun}</small><b><span>{ad(m["ev_id"], m["ev_ad"])}</span></b>'
                                          f'<b><span>{ad(m["dep_id"], m["dep_ad"])}</span></b>{ek}')
                el = ui.element('div').classes(sinif)
                with el:
                    ui.html(govde, sanitize=False)
                if h is not None and a is not None:
                    el.on('click', lambda _, h=h, a=a: sec(h, a))
                    serit_ogeler.append((el, (h, a)))

    return serit_ciz, serit_isaretle, tura_git


def _kur_pano(takim_sayfasi, degistir):
    """Takım seçimi (ev sahibi · değiştir · deplasman) ve olasılık panosu; kutudaki logoya tıklayınca takım sayfası
    açılır. Döner: ev_sec, dep_sec, ev_logo, dep_logo, olasilik, eksik_kutu, bilgi, aciklama."""
    with ui.column().classes('board'):
        # ev sahibi · değiştir · deplasman: iki kutu eşit genişlikte; kutudaki logoya tıklayınca takım sayfası açılır
        with ui.element('div').classes('w-full secim-satiri'):
            # iki listenin açılışı aynı: kutunun hemen altında, sol kenarı hizalı, kutu genişliğinde (Quasar'ın pencere
            # genişliğine göre kendi seçmesine bırakılmaz)
            liste = ('outlined dense dark options-dense behavior=menu menu-anchor="bottom left" menu-self="top left" '
                     'popup-content-class="secim-liste"')
            ev_sec = ui.select({}, label='Ev sahibi').props(liste).classes('w-full')
            with ev_sec.add_slot('prepend'):
                ev_logo = ui.html('', sanitize=False).classes('logo-dugme').tooltip('Takım sayfası')
                ev_logo.on('click.stop.prevent', lambda: takim_sayfasi(ev_sec))
            ui.button(icon='swap_horiz', on_click=degistir).props('flat round dense color=white').tooltip('Takımları değiştir')
            dep_sec = ui.select({}, label='Deplasman').props(liste).classes('w-full')
            with dep_sec.add_slot('prepend'):
                dep_logo = ui.html('', sanitize=False).classes('logo-dugme').tooltip('Takım sayfası')
                dep_logo.on('click.stop.prevent', lambda: takim_sayfasi(dep_sec))
        olasilik = ui.html('', sanitize=False).classes('w-full')
        eksik_kutu = ui.html('', sanitize=False).classes('w-full')
        bilgi = ui.element('div').classes('w-full mac-bilgi')  # tarih · stadyum · hakem · hava tek satırda
        with ui.expansion('Bu tahmin nasıl hesaplanıyor?', icon='help_outline').props('dense').classes('w-full'):
            aciklama = ui.html('', sanitize=False).classes('w-full')
    return ev_sec, dep_sec, ev_logo, dep_logo, olasilik, eksik_kutu, bilgi, aciklama


def _kur_skor_panelleri():
    """Skor matrisi, en olası skorlar, olasılık kartları ve geçmiş karşılaşmalar. Döner: matris, enolasi, goller, h2h_ozet, h2h."""
    with ui.row().classes('w-full gap-4 items-start'):
        with ui.column().classes('panel').style('flex:1 1 360px;width:auto'):
            ui.html('<h3>Skor olasılıkları</h3>', sanitize=False)
            matris = ui.html('', sanitize=False).classes('w-full')
            ui.label('Her kutu o skorun olasılığı (yüzde). Altın çerçeve en olası skor, koyu çerçeve (oynandıysa) gerçek '
                     'skor.').classes('cap')
        with ui.column().classes('panel').style('flex:1 1 280px;width:auto'):
            ui.html('<h3>En olası skorlar</h3>', sanitize=False)
            enolasi = ui.column().classes('liste')

    with ui.column().classes('panel'):
        ui.html('<h3>Olasılıklar</h3>', sanitize=False)
        goller = ui.html('', sanitize=False).classes('w-full')
        ui.label('Hepsi skor tablosundan: o sonucu veren skorların olasılıkları toplanır. Her kartta en olası seçenek '
                 'koyu. Bu tahminlerin geçmişteki başarısı Karne sekmesinde.').classes('cap')

    with ui.column().classes('panel'):
        ui.html('<h3>Geçmiş karşılaşmalar</h3>', sanitize=False)
        h2h_ozet = ui.html('', sanitize=False).classes('w-full')
        h2h = ui.html('', sanitize=False).classes('w-full')
    return matris, enolasi, goller, h2h_ozet, h2h


def _kur_oyuncu_paneller():
    """Kim gol atar / asist yapar / kart görür ve tahmini ilk 11'ler panelleri. Döner: golcu_aciklama, golcu_ev,
    golcu_dep, asist_aciklama, asist_ev, asist_dep, kart_aciklama, kart_ev, kart_dep, ilk11_panel, ilk11_not, ilk11_ev, ilk11_dep."""
    with ui.column().classes('panel'):
        ui.html('<h3>Kim gol atar?</h3>', sanitize=False)
        golcu_aciklama = ui.label().classes('cap')
        with ui.row().classes('w-full gap-6 items-start'):
            golcu_ev = ui.column().classes('liste').style('flex:1 1 300px')
            golcu_dep = ui.column().classes('liste').style('flex:1 1 300px')

    with ui.row().classes('w-full gap-4 items-start'):
        with ui.column().classes('panel').style('flex:1 1 440px;width:auto'):
            ui.html('<h3>Kim asist yapar?</h3>', sanitize=False)
            asist_aciklama = ui.label().classes('cap')
            with ui.row().classes('w-full gap-4 items-start'):
                asist_ev = ui.column().classes('liste').style('flex:1 1 200px')
                asist_dep = ui.column().classes('liste').style('flex:1 1 200px')
        with ui.column().classes('panel').style('flex:1 1 440px;width:auto'):
            ui.html('<h3>Kim kart görür?</h3>', sanitize=False)
            kart_aciklama = ui.label().classes('cap')
            with ui.row().classes('w-full gap-4 items-start'):
                kart_ev = ui.column().classes('liste').style('flex:1 1 200px')
                kart_dep = ui.column().classes('liste').style('flex:1 1 200px')

    with ui.column().classes('panel') as ilk11_panel:
        ui.html('<h3>Tahmini ilk 11\'ler</h3>', sanitize=False)
        ilk11_not = ui.label().classes('cap')
        with ui.row().classes('w-full gap-6 items-start'):
            ilk11_ev = ui.html('', sanitize=False).style('flex:1 1 340px;max-width:460px')
            ilk11_dep = ui.html('', sanitize=False).style('flex:1 1 340px;max-width:460px')
    return (golcu_aciklama, golcu_ev, golcu_dep, asist_aciklama, asist_ev, asist_dep, kart_aciklama, kart_ev, kart_dep,
            ilk11_panel, ilk11_not, ilk11_ev, ilk11_dep)


def _kur_oyuncu(G, durum, eksik_kutu):
    """Oyuncu olasılık listeleri ve tahmini ilk 11'ler (paneller dahil). Döner: oyuncu_ciz(S, h, a, t, guncel) (ilk
    listeler, kadro denetlenmeden), ilk11_hazirla(S, h, a, guncel), kadroya_gore (async: güncel kadroya göre yeniden çizer)."""
    (golcu_aciklama, golcu_ev, golcu_dep, asist_aciklama, asist_ev, asist_dep, kart_aciklama, kart_ev, kart_dep,
     ilk11_panel, ilk11_not, ilk11_ev, ilk11_dep) = _kur_oyuncu_paneller()

    def ilk11_oyuncu(ev_):
        """Sahadaki oyuncuya tıklanınca kartı: 'idx:' açık sezondaki oyuncu, 'fm:' FotMob id'si (uygulamadaki kaydı)."""
        a = str(ev_.args or '')
        if a.startswith('idx:') and G.S:
            G.oyuncu_ac(int(a[4:]))
        elif a.startswith('fm:'):
            k = G.depo.oyuncu_kaydi(a[3:])
            if k:
                G.git(*k)
            else:
                ui.notify('Bu oyuncunun uygulamada kaydı yok.')
    for kutu in (ilk11_ev, ilk11_dep):
        kutu.on('click', ilk11_oyuncu, js_handler='(e) => { const t = e.target.closest("[data-oyuncu]"); '
                                                   'if (t) { e.stopPropagation(); emit(t.dataset.oyuncu); } }')

    # oyuncu listeleri: (ev kutusu, deplasman kutusu, olasılık işlevi, satır altındaki bilgi, çubuk ölçeği)
    LISTELER = [
        (golcu_ev, golcu_dep, golcu_listesi, alt_golcu, 0.6),
        (asist_ev, asist_dep, asist_listesi, alt_asist, 0.5),
        (kart_ev, kart_dep, kart_listesi, alt_kart, 0.5),
    ]

    def golcu_ciz(kutu, takim_adi, liste, cikan, not_, alt=None, olcek=0.6):
        """Bir takımın oyuncu listesi (gol, asist ya da kart olasılığı). alt(oyuncu): satırın altındaki bilgi."""
        alt = alt or alt_golcu
        kutu.clear()
        with kutu:
            ui.html(f'<span class="tahmin-takim">{takim_logo(G.depo.takim_kimligi(G.S.lig, takim_adi))}{e(takim_adi)}</span>',
                    sanitize=False).classes('disp text-lg font-bold')
            if not liste:
                ui.label('Yeterli dakika almış oyuncu yok.').classes('cap')
            for pl, pr, isaret in liste:
                with ui.element('div').classes('satir'):
                    with ui.element('div'):
                        ui.button(pl['n'], on_click=lambda _, i=pl['idx']: G.oyuncu_ac(i)).props('flat dense no-caps').classes('link')
                        ui.html(f'<small>{alt(pl)}'
                                # önceki sezonlarıyla listeye giren, bu sezon az oynamış oyuncu (olasılık "90 dk oynarsa")
                                + (f' · bu sezon {pl["min"]} dk' if pl['min'] < G.S.min_esik else '')
                                + (f' · <span class="sakat-isaret">{e(isaret)}</span>' if isaret else '') + '</small>', sanitize=False)
                    ui.html(f'<div class="track"><i style="width:{min(100, pr / olcek * 100):.0f}%"></i></div>', sanitize=False)
                    ui.label(yuzde(pr)).classes('pv')
            if cikan:
                ui.html('<div class="cap" style="margin-top:4px">Listede yok: ' + '; '.join(f'{e(ad)} ({e(neden)})' for ad, neden in cikan)
                        + '</div>', sanitize=False)
            if not_:
                ui.label(not_).classes('cap')

    def oyuncu_ciz(S, h, a, t, guncel):
        golcu_aciklama.text = golcu_metni(S, guncel)
        # hakemin sertliği: maç başına sarı kartı / ligin ortalaması (hakem atanmışsa; az maçlık hakemde ortalamaya çekilir)
        hk_bilgi = (G.depo.canli_mac(S, h, a) or {}).get('hakem') or {}
        hk = oyuncu_tahmin.hakem_carpani(hk_bilgi)
        durum['hakem'] = hk
        asist_aciklama.text = ASIST_ACIKLAMA
        kart_aciklama.text = kart_metni(hk_bilgi, hk)
        for kutu_ev, kutu_dep, fn, alt, olcek in LISTELER:
            for kutu, i, lam in ((kutu_ev, h, t['lh']), (kutu_dep, a, t['la'])):
                golcu_ciz(kutu, S.T[i], [(p, pr, '') for p, pr in fn(G.depo, S, i, lam, hk)[:5]], [],
                          'Güncel kadro denetleniyor…' if guncel else '', alt, olcek)

    def ilk11_hazirla(S, h, a, guncel):
        # tahmini ilk 11 yalnızca ileride oynanacak bir maç seçiliyse (süren sezonun oynanmamış maçları)
        ileride = guncel and any(m.h == h and m.a == a for m in S.U)
        durum['ilk11_goster'] = ileride
        ilk11_panel.set_visibility(ileride)
        if ileride and durum.get('ilk11_cift') != (S.lig, h, a):  # aynı maçın dakikalık yenilemesinde sahalar titremesin
            durum['ilk11_cift'] = (S.lig, h, a)
            ilk11_ev.content = ilk11_dep.content = '<p class="cap">İlk 11 tahmini hazırlanıyor…</p>'

    def ilk11_ciz(S, h, a, k, sayfalar):
        for kutu, i, taraf in ((ilk11_ev, h, 'ev'), (ilk11_dep, a, 'dep')):
            kutu.content = ilk11_html(G.depo, S, i, k, taraf, sayfalar)
        ilk11_not.text = ILK11_NOT

    async def kadroya_gore(S, h, a, t, istek):
        k = await mac_kadrosu(G.depo, durum, S, h, a)
        ilk11 = kesin_ilk11(k, h, a)
        durum['ilk11_var'] = bool(ilk11)
        kadrolar, etkiler, notlar, sayfalar = await kadro_topla(G.depo, S, h, a, ilk11)
        if istek != durum.get('istek') or G.S is not S:
            return
        if durum.get('ilk11_goster'):
            ilk11_ciz(S, h, a, k, sayfalar)
        for kutu_ev, kutu_dep, fn, alt, olcek in LISTELER:
            for kutu, i, lam in ((kutu_ev, h, t['lh']), (kutu_dep, a, t['la'])):
                adaylar = fn(G.depo, S, i, lam, durum.get('hakem', 1.0))
                if kadrolar[i] is None:
                    kalan, cikan = [(p, pr, '') for p, pr in adaylar[:5]], []
                else:
                    kalan, cikan = suz(adaylar, kadrolar[i], ilk11=bool(ilk11))
                golcu_ciz(kutu, S.T[i], kalan, cikan, notlar[i], alt, olcek)
        eksik_kutu.content = eksik_html(S, h, a, t, etkiler, durum.get('ilk11_var'))

    return oyuncu_ciz, ilk11_hazirla, kadroya_gore


def _kur_kulup(G):
    """Farklı liglerden iki takım: kulüp Elo'su (avrupa.KulupElo; bütün liglerin lig maçları ve Avrupa kupalarıyla tek
    ölçekte). Döner: kl_hazirla (async; sekme yenilenince)."""
    kl = {'E': None}
    with ui.column().classes('panel'):
        ui.html('<h3>Farklı liglerden iki takım</h3>', sanitize=False)
        ui.label('İki farklı ligin takımları karşılaşsaydı: olasılıklar Kupalar sekmesindeki kulüp Elo\'sundan. Bütün liglerin '
                 'lig maçları ve Avrupa kupaları tek ölçekte; ligler arasındaki güç farkı kupa maçlarından öğrenilir. Lig içi '
                 'tahminden kabadır: xG, kadro değeri ve sakatlıklar hesaba katılmaz.').classes('cap')
        with ui.row().classes('w-full items-end gap-3'):
            kl_ev_lig = ui.select(lig_secenekleri(), label='Ev sahibinin ligi').props('outlined dense options-dense').style('min-width:220px')
            kl_ev = ui.select({}, label='Ev sahibi', with_input=True).props('outlined dense options-dense').style('min-width:200px')
            kl_dep_lig = ui.select(lig_secenekleri(), label='Deplasmanın ligi').props('outlined dense options-dense').style('min-width:220px')
            kl_dep = ui.select({}, label='Deplasman', with_input=True).props('outlined dense options-dense').style('min-width:200px')
            kl_taraf = ui.checkbox('Tarafsız saha')
            ui.button('Ayrıntılı tahmin', icon='insights', on_click=lambda: kl_ayrinti()).props('flat dense no-caps color=primary')
        kl_sonuc = ui.html('', sanitize=False).classes('w-full')

    def kl_lig_degisti(lig_sec, takim_sec):
        secenek = _kl_takimlar(G.depo, lig_sec.value) if lig_sec.value else {}
        takim_sec.set_options(secenek, value=takim_sec.value if takim_sec.value in secenek else next(iter(secenek), None))

    async def kl_hazirla():
        """İlk açılışta: ev sahibi açık lig, deplasman başka bir büyük lig; kulüp Elo'su bir kez yüklenir."""
        if kl_ev_lig.value is None and G.S:
            kl_ev_lig.set_value(G.S.lig)
            kl_dep_lig.set_value('EPL' if G.S.lig != 'EPL' else 'La_liga')
        if kl['E'] is None:
            kl['E'] = await run.io_bound(avrupa.elo, G.depo.veri_klasoru)
            kl_ciz()

    def kl_ciz(_=None):
        E = kl['E']
        if not E or kl_ev.value is None or kl_dep.value is None:
            kl_sonuc.content = '' if E or kl['E'] is None else '<p class="cap">Kulüp Elo\'su için Avrupa kupalarının verisi gerekiyor.</p>'
            return
        if kl_ev.value == kl_dep.value:
            kl_sonuc.content = '<p class="cap">İki farklı takım seç.</p>'
            return
        kl_sonuc.content = _kl_html(E, kl_ev.value, kl_dep.value, kl_ev.options[kl_ev.value], kl_dep.options[kl_dep.value],
                                    kl_taraf.value)

    def kl_ayrinti():
        E = kl['E']
        if not E or kl_ev.value is None or kl_dep.value is None or kl_ev.value == kl_dep.value:
            ui.notify('Önce farklı liglerden iki takım seç.')
            return
        G.ayrintili_tahmin({'E': E, 'ev': kl_ev.value, 'dep': kl_dep.value, 'ev_ad': kl_ev.options[kl_ev.value],
                            'dep_ad': kl_dep.options[kl_dep.value], 'tarafsiz': kl_taraf.value,
                            'baslik': 'Farklı liglerden iki takım', 'eleme': None, 'kulup': True})

    kl_ev_lig.on_value_change(lambda _: kl_lig_degisti(kl_ev_lig, kl_ev))
    kl_dep_lig.on_value_change(lambda _: kl_lig_degisti(kl_dep_lig, kl_dep))
    for s in (kl_ev, kl_dep, kl_taraf):
        s.on_value_change(kl_ciz)
    return kl_hazirla


def _kl_takimlar(depo, lig):
    """Ligin süren sezondaki takımları {FotMob id: ad} (adına göre sıralı)."""
    return dict(sorted(((int(t), ad) for ad, t in (depo.stadyumlar()['ligler'].get(lig) or {}).items()),
                       key=lambda x: x[1]))


def _kl_html(E, ev, dep, ev_ad, dep_ad, taraf):
    t = E.tahmin(ev, dep, taraf)
    p, ilk = t['p'], t['skorlar'][0][2]
    return (
        f'<div class="bar" style="margin-top:6px"><div class="h" style="flex-basis:{p[0] * 100:.1f}%">{yuzde(p[0]) if p[0] > .1 else ""}</div>'
        f'<div class="d" style="flex-basis:{p[1] * 100:.1f}%">{yuzde(p[1]) if p[1] > .1 else ""}</div>'
        f'<div class="a" style="flex-basis:{p[2] * 100:.1f}%">{yuzde(p[2]) if p[2] > .1 else ""}</div></div>'
        f'<div class="lead" style="margin:8px 0">{e(ev_ad)} kazanır {yuzde(p[0])} · beraberlik {yuzde(p[1])} · {e(dep_ad)} '
        f'kazanır {yuzde(p[2])}<br>Beklenen gol: {e(ev_ad)} <b>{fmt(t["lh"])} – {fmt(t["la"])}</b> {e(dep_ad)} · kulüp Elo\'su '
        f'{round(E.puan(ev))} – {round(E.puan(dep))}</div>'
        '<div class="liste" style="max-width:520px">' + ''.join(
            f'<div class="satir"><span class="disp" style="font-size:1.1rem;font-weight:700">{i} – {j}</span>'
            f'<div class="track"><i style="width:{pr / ilk * 100:.0f}%"></i></div><span class="pv">{fmt(pr * 100, 1)}%</span></div>'
            for i, j, pr in t['skorlar']) + '</div>')


def kur(G):
    durum = {'h': None, 'a': None, 'sessiz': False}

    # haftanın maçları en üstte: önce maç seçilir, altında analizi
    serit_ciz, serit_isaretle, tura_git = _kur_serit(G, durum, lambda h, a: sec(h, a))
    ev_sec, dep_sec, ev_logo, dep_logo, olasilik, eksik_kutu, bilgi, aciklama = _kur_pano(
        lambda secim: takim_sayfasi(secim), lambda: degistir())
    matris, enolasi, goller, h2h_ozet, h2h = _kur_skor_panelleri()
    oyuncu_ciz, ilk11_hazirla, kadroya_gore = _kur_oyuncu(G, durum, eksik_kutu)
    # farklı liglerden iki takım: kulüp Elo'su (avrupa.KulupElo; bütün liglerin lig maçları ve Avrupa kupalarıyla tek ölçekte)
    kl_hazirla = _kur_kulup(G)

    def takim_sayfasi(secim):
        if secim.value is not None and G.S:
            G.takim_ac(G.S.T[secim.value])

    def degistir():
        if durum['h'] is None:
            return
        sec(durum['a'], durum['h'])

    def sec(h, a):
        durum['sessiz'] = True
        ev_sec.value, dep_sec.value = h, a
        durum['sessiz'] = False
        tahmin_ciz()

    def secim_degisti(_):
        if durum['sessiz'] or ev_sec.value is None or dep_sec.value is None:
            return
        if ev_sec.value == dep_sec.value:  # aynı takım seçilemez: diğerini sıradakine kaydır
            secenek = list(dep_sec.options)
            durum['sessiz'] = True
            dep_sec.value = secenek[(secenek.index(dep_sec.value) + 1) % len(secenek)]
            durum['sessiz'] = False
        tahmin_ciz()

    ev_sec.on_value_change(secim_degisti)
    dep_sec.on_value_change(secim_degisti)

    def tahmin_ciz():
        S = G.S
        h, a = ev_sec.value, dep_sec.value
        durum['h'], durum['a'] = h, a
        ev_logo.content = takim_logo(G.depo.takim_kimligi(S.lig, S.T[h])).replace('class="logo"', 'class="logo secim-logo"')
        dep_logo.content = takim_logo(G.depo.takim_kimligi(S.lig, S.T[a])).replace('class="logo"', 'class="logo secim-logo"')
        t = S.tahmin(h, a)
        olasilik.content = olasilik_html(G.depo, S, h, a, t)
        aciklama.content = aciklama_html(S)
        oynanan = next((m for m in reversed(S.M) if m.h == h and m.a == a), None)
        bilgi.clear()
        with bilgi:
            ui.html(bilgi_html(G.depo, S, h, a, oynanan), sanitize=False).style('display:contents')
            hava_yer = ui.html(durum.get('hava', {}).get((S.lig, h, a), ''), sanitize=False).style('display:contents')
        matris.content = matris_html(S, h, a, t, oynanan)
        enolasi_ciz(enolasi, t)
        goller.content = piyasa_kartlari(t['p'], piyasalar(t['hucreler']), t['lh'], t['la'], S.T[h], S.T[a])
        guncel = S.yil == SON_SEZON
        oyuncu_ciz(S, h, a, t, guncel)
        serit_isaretle()
        G.arka_plan(h2h_ciz(S, S.T[h], S.T[a]))
        G.arka_plan(_hava_ciz(G.depo, durum, S, h, a, hava_yer))
        eksik_kutu.content = ('<div class="faint" style="margin-top:8px;text-align:center;font-size:.8rem">Güncel kadro ve '
                              'sakatlıklar denetleniyor…</div>' if guncel else '')
        ilk11_hazirla(S, h, a, guncel)
        if guncel:  # güncel kadroya göre süz (FotMob takım sayfası, bir saat önbellekte)
            durum['istek'] = durum.get('istek', 0) + 1
            G.arka_plan(kadroya_gore(S, h, a, t, durum['istek']))

    async def h2h_ciz(S, ev, dep):
        """İki takımın bu ligdeki son 10 karşılaşması (bütün sezonlar) ve özet."""
        maclar = await run.io_bound(G.depo.karsilasmalar, S.lig, ev, dep)
        if G.S is not S or (S.T[ev_sec.value], S.T[dep_sec.value]) != (ev, dep):
            return
        h2h_ozet.content, h2h.content = h2h_html(maclar, ev, dep)

    def yenile():
        S = G.S
        secenek = {i: S.T[i] for i in sorted(range(len(S.T)), key=lambda i: S.T[i])}
        durum['sessiz'] = True
        ev_sec.options, dep_sec.options = secenek, dict(secenek)
        ev_sec.update(); dep_sec.update()
        durum['sessiz'] = False
        up = serit_ciz()
        bekleyen = G.bekleyen_tahmin  # başka sekmeden istenen maç (ör. Haftanın maçları): (lig, ev adı, deplasman adı)
        if bekleyen and bekleyen[0] == S.lig and bekleyen[1] in S.T and bekleyen[2] in S.T:
            G.bekleyen_tahmin = None
            tura_git(S, S.T.index(bekleyen[1]), S.T.index(bekleyen[2]))
            sec(S.T.index(bekleyen[1]), S.T.index(bekleyen[2]))
        elif up:
            sec(up[0][0].h, up[0][0].a)
        else:
            sec(S.tablo[0]['i'], S.tablo[1]['i'])
        G.arka_plan(kl_hazirla())

    def tahmin_ac(lig, ev, dep):
        """Başka sekmeden: maçın tahminini aç (gerekirse o lige geçer)."""
        G.sekme_ac(ID)
        if G.S and G.S.lig == lig and G.S.yil == SON_SEZON and ev in G.S.T and dep in G.S.T:
            tura_git(G.S, G.S.T.index(ev), G.S.T.index(dep))
            sec(G.S.T.index(ev), G.S.T.index(dep))
        else:
            G.bekleyen_tahmin = (lig, ev, dep)
            G.git(lig, SON_SEZON)
    G.tahmin_ac = tahmin_ac

    def canli_yenile():
        """Canlı skor verisi gelince hakem, stadyum ve maç saati şeride ve skorborda yansısın. Canlı veri dakikada bir
        gelir: açık ligin maçlarında bu bilgiler değişmediyse sayfa yeniden çizilmez."""
        if not G.S or durum['h'] is None:
            return
        imza = _canli_imza(G.depo.g.canli, G.S.lig)
        if durum.get('canli_imza') == (G.S.lig, imza):
            return
        durum['canli_imza'] = (G.S.lig, imza)
        serit_ciz()
        tahmin_ciz()

    G.dinle('canli', canli_yenile)
    return yenile
