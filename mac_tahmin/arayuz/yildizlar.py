"""Öne çıkanlar sekmesi (açık lig, süren sezon): haftanın 11'i ve haftanın oyuncusu (maç puanlarından), form endeksi
(son 5 maç ile sezon ortalaması), gol ve asist krallığı yarışı (sezonun kalanı oynatılarak). Maç puanları FotMob'un;
endeks, 11 ve olasılıklar uygulamanın hesabı (lig_maclari.py, oyuncu_tahmin.py)."""
from nicegui import run, ui

from .. import lig_maclari, oyuncu_tahmin
from ..mac_ozeti import fiziksel_yazi
from ..sezon import SON_SEZON
from .ortak import e, fmt, takim_link, takim_logo, takim_tiklama, yuzde
from .takim_karti import _saha

ID, AD = 'yildizlar', 'Öne çıkanlar'
TEMBEL = True  # ligin maç sayfaları ilk açılışta indirilir: yalnızca sekme açıkken


def kur(G):
    d = {'satirlar': [], 'lig': None}
    with ui.column().classes('panel'):
        with ui.row().classes('w-full items-center'):
            ui.html('<h3>Haftanın 11\'i</h3>', sanitize=False)
            ui.space()
            hafta_sec = ui.select({}, label='Hafta', on_change=lambda _: hafta_ciz()).props(
                'outlined dense options-dense').style('min-width:140px')
        durum = ui.label().classes('cap')
        with ui.row().classes('w-full gap-4 items-start'):
            saha = ui.html('', sanitize=False).style('flex:1 1 360px;max-width:440px')
            with ui.column().classes('gap-1').style('flex:1 1 300px'):
                haftanin_oyuncusu = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
                on1_liste = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
        ui.label('Her mevkiye o haftanın maçlarında (en az 45 dakika oynayıp) en yüksek FotMob maç puanını alan oyuncu konur '
                 '(4-3-3). Oyuncuya tıklayınca kartı açılır.').classes('cap')
    with ui.column().classes('panel'):
        ui.html('<h3>Form endeksi</h3>', sanitize=False)
        ui.label('Uygulamanın hesabı: takımın son 5 maçında oyuncunun aldığı FotMob puanlarının ortalaması ve sezon '
                 'ortalamasıyla farkı (en az 20 dakika oynanan maçlar). Takımının son 5 maçının en az 3\'ünde oynamamış oyuncu '
                 '(sakat, cezalı, kadro dışı) listeye girmez.').classes('cap')
        form_kutu = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
    with ui.column().classes('panel') as fiz_panel:
        ui.html('<h3>Fiziksel liderler</h3>', sanitize=False)
        fiz_not = ui.label().classes('cap')
        fiz_kutu = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
    fiz_panel.set_visibility(False)
    with ui.column().classes('panel'):
        ui.html('<h3>Gol ve asist krallığı yarışı</h3>', sanitize=False)
        krallik_not = ui.label().classes('cap')
        krallik_kutu = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)

    def oyuncu_tiklandi(ev):
        a = str(ev.args or '')
        if a.startswith('idx:') and G.S:
            G.oyuncu_ac(int(a[4:]))
        elif a.startswith('fm:'):
            k = G.depo.oyuncu_kaydi(a[3:])
            if k:
                G.git(*k)
            else:
                ui.notify('Bu oyuncunun uygulamada kaydı yok.')

    js = '(e) => { const t = e.target.closest("[data-oyuncu]"); if (t) { e.stopPropagation(); emit(t.dataset.oyuncu); } }'
    for oge in (saha, haftanin_oyuncusu, on1_liste, form_kutu, krallik_kutu, fiz_kutu):
        oge.on('click', oyuncu_tiklandi, js_handler=js)

    def oyuncu_ad(pid, ad):
        return f'<span class="link" data-oyuncu="fm:{pid}">{e(ad)}</span>'

    def hafta_ciz():
        h = hafta_sec.value
        if h is None:
            return
        on1, en = lig_maclari.haftanin_11i(d['satirlar'], h)
        saha.content = _saha([{'ad': a['ad'], 'no': fmt(a['puan'], 1), 'x': a['x'], 'y': a['y'], 'id': a['pid']} for a in on1])
        if en:
            katki = ''.join(x for x in (f' · {en["gol"]} gol' if en['gol'] else '', f' · {en["asist"]} asist' if en['asist'] else ''))
            haftanin_oyuncusu.content = (
                f'<div class="lider-kutu"><div class="cap" style="font-weight:700">Haftanın oyuncusu</div>'
                f'<div class="disp" style="font-size:1.5rem;font-weight:700">{oyuncu_ad(en["pid"], en["ad"])}</div>'
                f'<div class="cap">{takim_logo(en["takim_id"])} {takim_link(en["takim"], en["takim_id"])} · '
                f'puan {fmt(en["puan"], 2)}{katki}</div></div>')
        else:
            haftanin_oyuncusu.content = '<p class="cap">Bu hafta veri yok.</p>'
        on1_liste.content = '<div class="lider-kutu">' + ''.join(
            f'<div class="lider"><span class="sira">{a["yer"]}</span><span class="ad">{oyuncu_ad(a["pid"], a["ad"])} '
            f'<span class="cap">{e(a["takim"])}</span></span><b>{fmt(a["puan"], 2)}</b><span></span></div>'
            for a in sorted(on1, key=lambda a: (a['y'], -a['x']))) + '</div>'

    def form_ciz():
        f = lig_maclari.form_tablosu(d['satirlar'])

        def tablo(baslik, liste, renk):
            satir = ''.join(
                f'<tr><td>{oyuncu_ad(r["pid"], r["ad"])}</td><td class="takim-hucre">{takim_logo(r["takim_id"])}'
                f'{takim_link(r["takim"], r["takim_id"])}</td><td class="hi">{fmt(r["son_ort"], 2)}</td>'
                f'<td style="color:{renk};font-weight:700">{"+" if r["fark"] > 0 else ""}{fmt(r["fark"], 2)}</td>'
                f'<td class="cap">{" ".join(fmt(x, 1) for x in r["son_puanlar"])}</td></tr>' for r in liste)
            return (f'<div><div class="disp" style="font-size:1.1rem;font-weight:700">{baslik}</div><table class="tb krallik-tablo">'
                    '<thead><tr><th>Oyuncu</th><th>Takım</th><th>Son 5 ort.</th><th>Fark</th><th>Puanları</th></tr></thead>'
                    f'<tbody>{satir}</tbody></table></div>')
        formda = sorted(f, key=lambda r: -r['son_ort'])[:8]
        yukselen = sorted((r for r in f if r['mac'] >= 4), key=lambda r: -r['fark'])[:8]
        dusen = sorted((r for r in f if r['mac'] >= 4), key=lambda r: r['fark'])[:8]
        form_kutu.content = ('<div class="krallik">' + tablo('En formdakiler (son 5 maç)', formda, 'var(--pitch-2)')
                             + tablo('Formu yükselenler ↑', yukselen, 'var(--pitch-2)')
                             + tablo('Formu düşenler ↓', dusen, 'var(--bad)') + '</div>')

    def fiziksel_ciz():
        """Fiziksel liderler (FotMob fiziksel veriyi verdiği liglerde; şimdilik Premier League): en hızlılar, 90 dakikada en
        çok sprint atan ve en çok koşanlar (en az FIZIKSEL_MIN_DK dakika oynamışlar)."""
        oz = lig_maclari.fiziksel_ozet(d['satirlar'])
        havuz = [dict(o, pid=pid) for pid, o in oz.items() if o['dk'] >= lig_maclari.FIZIKSEL_MIN_DK]
        fiz_panel.set_visibility(len(havuz) >= 10)
        if len(havuz) < 10:
            fiz_kutu.content = ''
            return

        def tablo(baslik, k, yaz, ek):
            satir = ''.join(
                f'<tr><td>{oyuncu_ad(r["pid"], r["ad"])}</td><td class="takim-hucre">{takim_logo(r["takim_id"])}'
                f'{takim_link(r["takim"], r["takim_id"])}</td><td class="hi">{yaz(r)}</td><td class="cap">{ek(r)}</td></tr>'
                for r in sorted(havuz, key=lambda r: -r[k])[:8])
            return (f'<div><div class="disp" style="font-size:1.1rem;font-weight:700">{baslik}</div><table class="tb krallik-tablo">'
                    f'<tbody>{satir}</tbody></table></div>')
        fiz_kutu.content = ('<div class="krallik">'
                            + tablo('En hızlılar', 'hiz', lambda r: fiziksel_yazi('hiz', r['hiz']), lambda r: f'{r["mac"]} maç')
                            + tablo('En çok sprint (90 dk)', 'sprint90', lambda r: fmt(r['sprint90'], 1),
                                    lambda r: f'toplam {r["sprint"]}')
                            + tablo('En çok koşan (90 dk)', 'mesafe90', lambda r: fiziksel_yazi('mesafe', r['mesafe90']),
                                    lambda r: f'toplam {fiziksel_yazi("mesafe", r["mesafe"])}') + '</div>')
        fiz_not.text = (f'Ligde en az {lig_maclari.FIZIKSEL_MIN_DK} dakika oynamış {len(havuz)} oyuncu, maç maç FotMob verisinden. '
                        'En yüksek hız sezonun tek maçındaki en iyisi; sprint ve koşu 90 dakika başına. FotMob fiziksel veriyi '
                        'şimdilik yalnızca Premier League\'de veriyor.')

    async def krallik_ciz(S):
        if getattr(S, '_krallik', None) is None:
            krallik_not.text = 'Krallık yarışı hesaplanıyor (kalan maçlar 10.000 kez oynatılıyor)…'
            krallik_kutu.content = ''

        def hesapla():  # sezonda bir kez (sezon verisi değişince sezon yeniden kurulur, yeniden hesaplanır)
            if getattr(S, '_krallik', None) is None:
                S._krallik = [oyuncu_tahmin.krallik(S, tur, adet=10, onceki=oyuncu_tahmin.onceki_sezonlar(
                    S, G.depo.veri_klasoru, tur)) for tur in ('gol', 'asist')]
            return S._krallik
        sonuc = await run.io_bound(hesapla)
        if G.S is not S or not sonuc:
            return
        gol, asist = sonuc

        def tablo(baslik, liste, birim):
            satir = ''.join(
                f'<tr><td><span class="link" data-oyuncu="idx:{r["p"]["idx"]}">{e(r["p"]["n"])}</span></td>'
                f'<td class="takim-hucre">{takim_logo(G.depo.takim_kimligi(S.lig, r["p"]["t"].split(" / ")[-1]))}'
                f'{takim_link(r["p"]["t"].split(" / ")[-1], r["p"]["t"].split(" / ")[-1])}</td><td>{r["mevcut"]}</td>'
                f'<td class="hi">{fmt(r["beklenen"], 1)}</td><td>{yuzde(r["kral"])}</td><td>{yuzde(r["ilk3"])}</td></tr>' for r in liste)
            return (f'<div><div class="disp" style="font-size:1.1rem;font-weight:700">{baslik}</div><table class="tb krallik-tablo">'
                    f'<thead><tr><th>Oyuncu</th><th>Takım</th><th>Şu an</th><th>Sezon sonu (bekl.)</th><th>Kral olur</th>'
                    f'<th>İlk 3</th></tr></thead><tbody>{satir}</tbody></table></div>')
        krallik_kutu.content = ('<div class="krallik">' + tablo('Gol krallığı', gol, 'gol')
                                + tablo('Asist krallığı', asist, 'asist') + '</div>')
        krallik_not.text = (f'Uygulamanın hesabı: kalan {len(S.U)} maç 10.000 kez oynatıldı. Her oyuncunun kalan maçlardaki golü '
                            '(asisti) 90 dakikadaki (gol + xG) / 2 oranı ve maç başına süresiyle çekilir. Oran, oyuncunun önceki '
                            'iki sezonuyla harmanlanır (uygulamadaki bütün ligler; geçen sezon daha ağır, en fazla 12 maçlık süre '
                            'kadar): sezon başında birkaç gol atan ama geçmişi zayıf oyuncu tepeye fırlamaz, sezon ilerledikçe bu '
                            'sezonun verisi öne geçer. Geçmişi olmayan ya da az süre alan oyuncunun oranı ligin tipik oranına doğru '
                            'çekilir; ligden ayrılan oyuncunun sayısı sabit kalır. Eşitlikte krallık paylaştırılır.')

    async def yenile():
        S = G.S
        if S.yil != SON_SEZON:
            durum.text = 'Öne çıkanlar süren sezon için hesaplanır; üstten süren sezonu seç.'
            for oge in (saha, haftanin_oyuncusu, on1_liste, form_kutu, krallik_kutu, fiz_kutu):
                oge.content = ''
            fiz_panel.set_visibility(False)
            hafta_sec.set_options({})
            return
        G.arka_plan(krallik_ciz(S))
        lig = S.lig
        if d.get('lig') != lig:  # yeni ligin verisi gelene kadar önceki ligin 11'i ve formu görünmesin
            for oge in (saha, haftanin_oyuncusu, on1_liste, form_kutu, fiz_kutu):
                oge.content = ''
            fiz_panel.set_visibility(False)
            hafta_sec.set_options({})
        d['lig'] = lig

        def guncel():
            return d['lig'] == lig and G.S is S

        def ciz(satirlar):
            d['satirlar'] = satirlar
            haftalar = sorted({s['hafta'] for s in satirlar}, key=lambda h: (not h.isdigit(), int(h) if h.isdigit() else h))
            secili = hafta_sec.value if hafta_sec.value in haftalar else (haftalar[-1] if haftalar else None)
            hafta_sec.set_options({h: f'{h}. hafta' if h.isdigit() else h for h in haftalar}, value=secili)
            hafta_ciz()
            form_ciz()
            fiziksel_ciz()

        # önce önbellekteki maçlarla hemen (ağ isteği yok); eksik maçlar varsa arka planda iner ve tablo yenilenir
        ham = G.depo.g.ham
        satirlar = await run.io_bound(lig_maclari.oyuncu_satirlari, lig, ham, None, False)
        if not guncel():
            return
        mac_sayisi = len({s['mac'] for s in satirlar})
        durum.text = f'{mac_sayisi} maçın oyuncu puanlarından.' if satirlar else 'Bu ligin maç verisi hazırlanıyor…'
        if satirlar:
            ciz(satirlar)
        eksik = await run.io_bound(lig_maclari.eksik_maclar, lig, ham) or []
        if not eksik or not guncel():
            if not satirlar and guncel():
                durum.text = 'Bu ligde henüz maç verisi yok.'
            return

        def ilerleme(k, n):
            if guncel():
                durum.text = ((f'{mac_sayisi} maçın oyuncu puanlarından; son {len(eksik)} maçın verisi arka planda alınıyor '
                               if mac_sayisi else 'Bu ligin maç verisi ilk kez alınıyor ')
                              + f'({k}/{n} maç işlendi; gelince tablo kendiliğinden güncellenir)')
        satirlar = await run.io_bound(lig_maclari.oyuncu_satirlari, lig, ham, ilerleme)
        if not guncel():
            return
        durum.text = f'{len({s["mac"] for s in satirlar})} maçın oyuncu puanlarından.' if satirlar else 'Bu ligde henüz maç verisi yok.'
        ciz(satirlar)

    return yenile
