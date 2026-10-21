"""Ayrıntılı maç tahmini penceresi: Kupalar ve Milli sekmelerindeki maçlar için (lig maçlarının tahmini Tahmin
sekmesinde). Elo modelinin beklenen gollerinden sonuç olasılıkları, skor tablosu, alt/üst ve karşılıklı gol, eleme
maçlarında tur atlama; iki takımın son maçları ve aralarındaki maçlar; kulüplerde kim gol atar (takımın uygulamadaki
liginin oyuncu verisinden, güncel kadroya göre).

Kullanım: ac = mac_tahmini.kur(G); ac(bilgi). bilgi: {'E': model (avrupa.KulupElo ya da milli.MilliElo), 'ev', 'dep':
FotMob takım id'leri, 'ev_ad', 'dep_ad', 'tarafsiz', 'baslik' (turnuva · tur), 'zaman' (ISO), 'turnuva_logo' (URL),
'skor' (oynandıysa), 'eleme' (None ya da {'onceki': (ev golü, dep golü)} rövanş, {'rovans': True} iki maçlı eşleşmenin
ilk maçı, {} tek maçlık eleme), 'kulup' (True: kulüp maçı), 'golcu' (kulüp maçında kim gol atar gösterilsin mi;
varsayılan evet. Güncel kadrolardan hesaplandığı için eski sezonlarda kapatılır)}."""
import logging

from nicegui import run, ui

from .. import milli, oyuncu_tahmin
from .. import takim as takim_veri
from ..logo import logo_html
from ..modeller import piyasalar, sonuc_olasiliklari, tur_atlama
from ..sezon import SON_SEZON
from .ortak import e, piyasa_kartlari, fmt, kisa_gun, takim_link, takim_logo, takim_tiklama, yerel, yuzde

logger = logging.getLogger(__name__)

FORM_ADET = 6
KARSILASMA_ADET = 8


def _sonuc(atilan, yenilen):
    return 'G' if atilan > yenilen else 'B' if atilan == yenilen else 'M'


def _rozet(s, baslik=''):
    return f'<i class="{s}" title="{e(baslik)}">{s}</i>'


def _turnuva(x):
    """Geçmiş kaydının turnuva adı (kulüplerde kayıtta, milli takımlarda turnuva kimliğinden)."""
    return x.get('turnuva') or (milli.TURNUVA[x['tid']][1] if x.get('tid') in milli.TURNUVA else '')


def _elo(E, t):
    return E.puan(t) if hasattr(E, 'puan') else E.R.get(t, 1500)


def eslesme_turu(maclar, ev, dep, zaman, eleme):
    """Bir eleme maçının türü: aynı turda iki takımın ters sahalı maçı varsa iki maçlı eşleşme. maclar: [(zaman, ev,
    dep, skor ya da None)] (o turun maçları). Döner: None (eleme değil), {} tek maç, {'rovans': True} ilk maç,
    {'onceki': (bu maçın ev sahibinin golü, deplasmanın golü)} rövanş (ilk maç oynandıysa)."""
    if not eleme:
        return None
    diger = next((m for m in maclar if m[1] == dep and m[2] == ev), None)
    if diger is None:
        return {}
    if diger[0] < zaman:  # bu maç rövanş
        return {'onceki': (diger[3][1], diger[3][0])} if diger[3] else {}
    return {'rovans': True}


def kur(G):
    d = {'bilgi': None, 'istek': 0}
    with ui.dialog() as pencere, ui.card().classes('w-full gap-3').style(
            'max-width:980px;background:var(--panel);color:var(--ink)'):
        with ui.row().classes('w-full items-center no-wrap'):
            baslik = ui.html('', sanitize=False).classes('grow')
            ui.button(icon='close', on_click=pencere.close).props('flat round dense')
        govde = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
        golcu = ui.html('', sanitize=False).classes('w-full')
        ui.label('Olasılıklar Elo modelinden: iki takımın güç farkı (ve ev sahibi avantajı) beklenen gollere, beklenen goller '
                 'Poisson dağılımıyla skorlara çevrilir. Sakatlık, rotasyon ve maçın önemi hesaba katılmaz.').classes('cap')

    def oyuncu_tiklandi(ev):
        a = str(ev.args or '')
        if a.count(':') != 2:
            return
        lig, yil, pid = a.split(':')
        pencere.close()
        if G.S and G.S.lig == lig and G.S.yil == int(yil):
            p = next((q for q in G.S.PLY if str(q['id']) == pid), None)
            if p:
                G.oyuncu_ac(p['idx'])
                return
        G.git(lig, int(yil), int(pid) if pid.lstrip('-').isdigit() else pid)

    golcu.on('click', oyuncu_tiklandi,
             js_handler='(e) => { const t = e.target.closest("[data-oyuncu]"); if (t) { e.stopPropagation(); emit(t.dataset.oyuncu); } }')
    takim_tiklama(golcu, G)

    def ad_bul(b, t):
        E = b['E']
        if t == b['ev']:
            return b['ev_ad']
        if t == b['dep']:
            return b['dep_ad']
        ad = E.ad.get(t)
        if ad:
            return ad
        k = G.depo.takim_ligi(t)
        return k[1] if k else str(t)

    def gecmis(b, t):
        """Takımın maç başlamadan önceki maçları (yeniden eskiye)."""
        return [x for x in reversed(b['E'].gecmis.get(t, [])) if not b.get('zaman') or x['zaman'] < b['zaman']]

    def ac(b):
        d['bilgi'] = b
        E, h, a = b['E'], b['ev'], b['dep']
        t = E.tahmin(h, a, b.get('tarafsiz', False)) if b.get('avantaj') is None else E.tahmin(h, a, False, b['avantaj'])
        lh, la, p = t['lh'], t['la'], t['p']
        _, hucreler = sonuc_olasiliklari(lh, la)
        z = yerel(b.get('zaman') or '')
        logo = logo_html(e(b.get('turnuva_logo') or ''), 'turnuva-logo')
        baslik.content = (f'<div class="turnuva-baslik">{logo}<div><div class="disp" style="font-size:1.5rem;font-weight:700;'
                          f'line-height:1.1">{e(b["ev_ad"])} – {e(b["dep_ad"])}</div><div class="cap">'
                          + ' · '.join(x for x in (e(b.get('baslik') or ''), f'{kisa_gun(z.date())} {z:%H:%M}' if z else '',
                                                   'tarafsız saha' if b.get('tarafsiz') else '') if x)
                          + '</div></div></div>')
        parca = []

        # sonuç olasılıkları
        pmax = max(p)
        parca.append(
            f'<div class="mt-ust"><div class="mt-takim">{takim_logo(h)}{takim_link(b["ev_ad"], h)}</div>'
            f'<div class="mt-eg"><span class="cap">Beklenen gol</span><span class="eg">{fmt(lh)} – {fmt(la)}</span></div>'
            f'<div class="mt-takim sag">{takim_link(b["dep_ad"], a)}{takim_logo(a)}</div></div>'
            f'<div class="bar"><div class="h" style="flex-basis:{p[0] * 100:.2f}%"></div>'
            f'<div class="d" style="flex-basis:{p[1] * 100:.2f}%"></div>'
            f'<div class="a" style="flex-basis:{p[2] * 100:.2f}%"></div></div>'
            '<div class="tiles mt-oran">' + ''.join(
                f'<div class="tile{" mt-top" if v == pmax else ""}"><span class="num">{yuzde(v)}</span><small>{k}</small></div>'
                for k, v in ((f'{e(b["ev_ad"])} kazanır', p[0]), ('Beraberlik', p[1]), (f'{e(b["dep_ad"])} kazanır', p[2])))
            + f'</div><div class="lead" style="text-align:center">En olası skor <b>{t["skorlar"][0][0]} – {t["skorlar"][0][1]}</b> '
              f'({yuzde(t["skorlar"][0][2])}) · güç (Elo) {round(_elo(E, h))} – {round(_elo(E, a))}</div>')
        uyari = [x for x in (E.belirsizlik(h, b['ev_ad']), E.belirsizlik(a, b['dep_ad']))
                 if x] if hasattr(E, 'belirsizlik') else []
        if uyari:  # kulüp Elo'su takımlardan birini az tanıyor (ligi uygulamada yok)
            parca.append('<div class="belirsiz-kutu"><b>⚠ Bu tahmin daha belirsiz.</b> ' + ' '.join(e(x) for x in uyari)
                         + ' Olasılıklar yalnızca kulüp Elo\'sundan; bu takımın gerçek gücü bundan belirgin farklı olabilir.</div>')
        if b.get('skor'):
            parca.append(f'<div class="lead" style="text-align:center">Maç oynandı: <b>{b["skor"][0]} – {b["skor"][1]}</b> '
                         '(tahmin bugünkü Elo puanlarıyla; maç önceki puanlarla biraz farklı olabilir)</div>')

        # eleme: tur atlama
        el = b.get('eleme')
        if el is not None:
            if 'rovans' in el:
                lh2, la2 = E.tahmin(a, h, False)['lh'], E.tahmin(a, h, False)['la']
                q = tur_atlama(lh, la, rovans=(lh2, la2))
                aciklama = 'İki maçlı eşleşmenin ilk maçı: rövanş da (deplasman takımının sahasında) hesaplanır.'
            elif 'onceki' in el:
                q = tur_atlama(lh, la, onceki=el['onceki'])
                aciklama = (f'Rövanş; ilk maç {e(b["dep_ad"])} {el["onceki"][1]} – {el["onceki"][0]} {e(b["ev_ad"])} bitti, '
                            'toplam skora göre.')
            else:
                q = tur_atlama(lh, la)
                aciklama = 'Tek maçlık eleme.'
            parca.append(
                f'<h4 class="mt-h">Turu kim geçer?</h4><div class="bar"><div class="h" style="flex-basis:{q * 100:.2f}%">'
                f'{e(b["ev_ad"])} {yuzde(q)}</div><div class="a" style="flex-basis:{(1 - q) * 100:.2f}%">{e(b["dep_ad"])} '
                f'{yuzde(1 - q)}</div></div><div class="cap">{aciklama} Eşitlikte uzatma (beklenen gollerin üçte biri) ve '
                'penaltılar (yarı yarıya).</div>')

        # skor tablosu ve en olası skorlar
        hucre = {(i, j): pr for i, j, pr in hucreler}
        N = 6
        mx = max(hucre[(i, j)] for i in range(N) for j in range(N))
        en = max(hucre, key=hucre.get)
        mat = (f'<div class="matris-eksen"><span></span><span>{e(b["dep_ad"])} golleri →</span></div>'
               f'<div class="matris-sar"><div class="matris-dikey">{e(b["ev_ad"])} golleri ↓</div>'
               '<div class="matris"><span class="ax"></span>' + ''.join(f'<span class="ax">{j}</span>' for j in range(N)))
        for i in range(N):
            mat += f'<span class="ax">{i}</span>'
            for j in range(N):
                qq = hucre[(i, j)]
                al = qq / mx
                sinif = ' '.join(c for c in ('best' if (i, j) == en else '',
                                             'real' if b.get('skor') and tuple(b['skor']) == (i, j) else '') if c)
                mat += (f'<span class="{sinif}" title="{i}-{j}: {fmt(qq * 100, 1)}%" style="background:color-mix(in srgb,'
                        f'var(--pitch) {round(al * 85)}%,transparent);color:{"#fff" if al > .5 else "inherit"}">{round(qq * 100)}</span>')
        mat += '</div></div>'
        ilk = t['skorlar'][0][2]
        skorlar = '<div class="liste">' + ''.join(
            f'<div class="satir"><span class="disp" style="font-size:1.1rem;font-weight:700">{i} – {j}</span>'
            f'<div class="track"><i style="width:{pr / ilk * 100:.0f}%"></i></div><span class="pv">{fmt(pr * 100, 1)}%</span></div>'
            for i, j, pr in t['skorlar']) + '</div>'
        parca.append('<div class="mt-iki"><div><h4 class="mt-h">Skor olasılıkları</h4>' + mat
                     + '<div class="cap">Her kutu o skorun olasılığı (yüzde); altın çerçeve en olası skor.</div></div>'
                     f'<div><h4 class="mt-h">En olası skorlar</h4>{skorlar}</div></div>')

        # olasılıklar: maç sonucu ve çifte şans, goller, handikap, ilk yarı (Maç tahmini sekmesiyle aynı kartlar)
        parca.append('<h4 class="mt-h">Olasılıklar</h4>' + piyasa_kartlari(p, piyasalar(hucreler), lh, la, b['ev_ad'], b['dep_ad'])
                     + '<div class="cap">Hepsi skor tablosundan; her kartta en olası seçenek koyu.</div>')

        # son maçlar
        def form(tk):
            g = gecmis(b, tk)[:FORM_ADET]
            if not g:
                return '<p class="cap">Kayıtlı maç yok.</p>'
            rozet = ''.join(_rozet(_sonuc(x['atilan'], x['yenilen'])) for x in reversed(g))
            satir = ''.join(
                f'<tr><td class="cap">{x["zaman"][8:10]}.{x["zaman"][5:7]}.{x["zaman"][2:4]}</td>'
                f'<td>{e(x.get("rakip_ad") or ad_bul(b, x["rakip"]))} <span class="cap">'
                f'({"tarafsız" if x.get("tarafsiz") else "ev" if x["ev"] else "dep."})</span></td>'
                f'<td class="hi">{x["atilan"]}–{x["yenilen"]}</td><td><span class="form">{_rozet(_sonuc(x["atilan"], x["yenilen"]))}</span></td>'
                f'<td class="cap">{e(_turnuva(x))}</td></tr>' for x in g)
            return (f'<div class="cap" style="margin-bottom:4px">Son {len(g)} maç (eskiden yeniye): <span class="form">{rozet}</span></div>'
                    f'<table class="tb"><tbody>{satir}</tbody></table>')
        parca.append(f'<div class="mt-iki"><div><h4 class="mt-h">{e(b["ev_ad"])}: son maçlar</h4>{form(h)}</div>'
                     f'<div><h4 class="mt-h">{e(b["dep_ad"])}: son maçlar</h4>{form(a)}</div></div>')

        # aralarındaki maçlar
        km = [x for x in gecmis(b, h) if x['rakip'] == a][:KARSILASMA_ADET]
        if km:
            g1 = sum(1 for x in km if x['atilan'] > x['yenilen'])
            g2 = sum(1 for x in km if x['atilan'] < x['yenilen'])
            satir = ''.join(
                f'<tr><td class="cap">{x["zaman"][8:10]}.{x["zaman"][5:7]}.{x["zaman"][:4]}</td><td class="cap">{e(_turnuva(x))}</td>'
                + (f'<td style="text-align:right">{e(b["ev_ad"])}</td><td class="hi">{x["atilan"]} – {x["yenilen"]}</td><td>{e(b["dep_ad"])}</td>'
                   if x['ev'] else
                   f'<td style="text-align:right">{e(b["dep_ad"])}</td><td class="hi">{x["yenilen"]} – {x["atilan"]}</td><td>{e(b["ev_ad"])}</td>')
                + '</tr>' for x in km)
            parca.append(f'<h4 class="mt-h">Aralarındaki maçlar</h4><div class="lead">Son {len(km)} karşılaşma: {e(b["ev_ad"])} {g1} '
                         f'galibiyet · {len(km) - g1 - g2} beraberlik · {e(b["dep_ad"])} {g2} galibiyet</div>'
                         f'<table class="tb"><tbody>{satir}</tbody></table>')
        else:
            parca.append('<h4 class="mt-h">Aralarındaki maçlar</h4><p class="cap">Kayıtlı karşılaşma yok'
                         + (' (uygulamanın ligleri ve Avrupa kupaları, 2016\'dan bu yana).' if b.get('kulup') else ' (2008\'den bu yana).') + '</p>')
        govde.content = ''.join(parca)

        golcu_goster = b.get('kulup') and b.get('golcu', True)
        golcu.content = ('<h4 class="mt-h">Kim gol atar?</h4><p class="cap">Oyuncu verisi ve güncel kadro yükleniyor…</p>'
                         if golcu_goster else '')
        pencere.open()
        if golcu_goster:
            d['istek'] += 1
            G.arka_plan(golculer(b, lh, la, d['istek']))

    async def golculer(b, lh, la, istek):
        sutunlar = []
        for tk, lam, ad in ((b['ev'], lh, b['ev_ad']), (b['dep'], la, b['dep_ad'])):
            sutunlar.append(await run.io_bound(golcu_listesi, tk, lam, ad))
        if istek != d['istek']:
            return
        golcu.content = ('<h4 class="mt-h">Kim gol atar?</h4><div class="mt-iki">' + ''.join(sutunlar) + '</div>'
                         '<div class="cap">90 dakika oynarsa en az bir gol atma olasılığı: bu maçın beklenen golü, oyuncunun '
                         'liginde takımın gol ve xG\'sindeki payına göre dağıtılır (pay, önceki iki sezonla ve mevkinin '
                         'ortalamasıyla harmanlanır; bu sezon az oynamış oyuncunun süresi yazılır). Güncel kadroda olmayan ve sakat '
                         'oyuncular listeye alınmaz. Oyuncuya tıklayınca kartı açılır.</div>')

    def golcu_listesi(tk, lam, ad):
        bas = f'<div><div class="disp" style="font-weight:700;font-size:1.05rem">{takim_logo(tk)}{e(ad)}</div>'
        k = G.depo.takim_ligi(tk)
        if not k:
            return bas + '<p class="cap">Bu takımın ligi uygulamada yok; oyuncu verisi bulunmuyor.</p></div>'
        lig, takim_ad = k
        try:
            S = G.depo.sezon(lig, SON_SEZON)
            i = S.T.index(takim_ad)
        except Exception:
            logger.debug('takımın sezon verisi yok: %s', takim_ad, exc_info=True)
            return bas + '<p class="cap">Takımın bu sezonki lig verisi yok.</p></div>'
        adaylar = S.golculer(i, lam, adet=None, onceki=oyuncu_tahmin.onceki_sezonlar(S, G.depo.veri_klasoru, 'gol'))
        try:
            kadro = takim_veri.takim_sayfasi(tk, G.depo.g.ham)['kadro']
        except Exception:
            logger.debug('takım kadrosu alınamadı: %s', tk, exc_info=True)
            kadro = None
        kalan = []
        for p, pr in adaylar:
            if len(kalan) >= 5:
                break
            kayit = takim_veri.kadrodaki(p['n'], kadro, p.get('fm_id')) if kadro else True
            if kayit is None or (kayit is not True and kayit['sakat'] and kayit['sakat'] != 'Doubtful'):
                continue
            kalan.append((p, pr, kayit is not True and kayit['sakat'] == 'Doubtful'))
        if not kalan:
            return bas + '<p class="cap">Yeterli dakika almış oyuncu yok.</p></div>'
        return bas + '<div class="liste">' + ''.join(
            f'<div class="satir"><div><span class="link" data-oyuncu="{e(lig)}:{SON_SEZON}:{e(p["id"])}">{e(p["n"])}</span>'
            f'<small>{p["g"]} gol · {fmt(p["xg"], 1)} xG (lig)' + (f' · bu sezon {p["min"]} dk' if p['min'] < S.min_esik else '')
            + (' · <span class="sakat-isaret">şüpheli</span>' if supheli else '')
            + f'</small></div><div class="track"><i style="width:{min(100, pr / .6 * 100):.0f}%"></i></div>'
              f'<span class="pv">{yuzde(pr)}</span></div>' for p, pr, supheli in kalan) + '</div></div>'

    return ac
