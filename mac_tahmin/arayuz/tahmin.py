"""Maç tahmini sekmesi: takım seçimi, sonuç olasılıkları, skor matrisi, maç şeridi, olası golcüler ve tahmini ilk 11'ler.
Yakındaki maçlarda FotMob'un kadrosuna bakılır: açıklanmış kesin ilk 11 varsa listeler ve kadro düzeltmesi ona göre
yapılır; tahmini ilk 11 sahaları kesin kadro > FotMob'un tahmini > uygulamanın "en güçlü 11"i sırasıyla çizilir."""
import logging
import time

from nicegui import run, ui

from .. import avrupa, karne, lig_maclari, oyuncu_tahmin
from .. import takim as takim_veri
from ..mac_ozeti import ayrinti
from ..modeller import piyasalar, sonuc_olasiliklari
from ..sezon import DC_RHO, SON_SEZON
from ..stadyum import stadyum_bul
from .ortak import e, piyasa_kartlari, fmt, hava_html, kisa_gun, lig_secenekleri, sayi, takim_logo, tarih_uzun, yerel, yuzde
from .takim_karti import _saha

logger = logging.getLogger(__name__)

ID, AD = 'tahmin', 'Maç tahmini'
SERIT_OYNANAN = 3  # şeritte sıradaki maçlardan önce gösterilen son oynanmış maç sayısı
MAC_KADRO_SN = 900  # maçın FotMob kadrosu (tahmini ya da kesin) bu kadar saniyede bir yeniden bakılır
GUVEN_YUKSEK, GUVEN_ORTA = 0.60, 0.45  # model güveni etiketi: en olası sonucun olasılığına göre


def ozet_cumlesi(ev, dep, p, pz):
    """Maçın tahmini sade dille, bir iki cümle: kim favori ve ne kadar, gollü mü (olasılıklardan kurallarla)."""
    ad = [ev, dep]
    fav = 0 if p[0] >= p[2] else 1
    pf, pd_ = p[0 if fav == 0 else 2], p[2 if fav == 0 else 0]
    if pf >= 0.6:
        bas = f'<b>{e(ad[fav])}</b> açık favori ({yuzde(pf)} kazanır).'
    elif pf >= 0.45:
        bas = f'<b>{e(ad[fav])}</b> favori ({yuzde(pf)}); {e(ad[1 - fav])} için kazanma şansı {yuzde(pd_)}.'
    elif pf - pd_ >= 0.05:
        bas = f'Dengeli bir maç: <b>{e(ad[fav])}</b> biraz önde ({yuzde(pf)} – {yuzde(pd_)}), beraberlik {yuzde(p[1])}.'
    else:
        bas = f'Çok dengeli bir maç: iki takımın kazanma şansı neredeyse eşit, beraberlik {yuzde(p[1])}.'
    if pz['ust25'] >= 0.6:
        gol = 'Gollü bir maç bekleniyor'
    elif pz['ust25'] <= 0.42:
        gol = 'Az gollü bir maç bekleniyor'
    else:
        gol = 'Gol sayısı ortalama civarında bekleniyor'
    gol += (', iki takımın da gol atması olası.' if pz['kg'] >= 0.58 else
            ', en az bir takımın gol atamaması olası.' if pz['kg'] <= 0.42 else '.')
    return f'{bas} {gol}'


def hakem_metni(h):
    p = ['Hakem: ' + h['ad'] + (f' ({h["ulke"]})' if h.get('ulke') else '')]
    if h.get('mac'):
        p.append(f'{h["mac"]} maç')
    if h.get('sariOrt') is not None:
        p.append(f'maç başına {fmt(h["sariOrt"])} sarı kart')
    if h.get('kirmizi') is not None:
        p.append(f'{h["kirmizi"]} kırmızı')
    if h.get('penalti') is not None:
        p.append(f'{h["penalti"]} penaltı')
    return ' · '.join(p)


def kur(G):
    durum = {'h': None, 'a': None, 'sessiz': False}

    # haftanın maçları en üstte: önce maç seçilir, altında analizi
    with ui.row().classes('w-full items-center gap-1'):
        serit_baslik = ui.label().classes('disp text-lg font-bold')
        ui.space()
        tur_geri = ui.button(icon='chevron_left', on_click=lambda: tur_degistir(-1)).props('flat round dense').tooltip('Önceki hafta')
        tur_yazi = ui.label().classes('disp').style('min-width:84px;text-align:center;font-weight:700')
        tur_ileri = ui.button(icon='chevron_right', on_click=lambda: tur_degistir(1)).props('flat round dense').tooltip('Sonraki hafta')
    serit = ui.element('div').classes('serit')

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
            ui.button(icon='swap_horiz', on_click=lambda: degistir()).props('flat round dense color=white').tooltip('Takımları değiştir')
            dep_sec = ui.select({}, label='Deplasman').props(liste).classes('w-full')
            with dep_sec.add_slot('prepend'):
                dep_logo = ui.html('', sanitize=False).classes('logo-dugme').tooltip('Takım sayfası')
                dep_logo.on('click.stop.prevent', lambda: takim_sayfasi(dep_sec))
        olasilik = ui.html('', sanitize=False).classes('w-full')
        eksik_kutu = ui.html('', sanitize=False).classes('w-full')
        bilgi = ui.element('div').classes('w-full mac-bilgi')  # tarih · stadyum · hakem · hava tek satırda
        with ui.expansion('Bu tahmin nasıl hesaplanıyor?', icon='help_outline').props('dense').classes('w-full'):
            aciklama = ui.html('', sanitize=False).classes('w-full')

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

    # farklı liglerden iki takım: kulüp Elo'su (avrupa.KulupElo; bütün liglerin lig maçları ve Avrupa kupalarıyla tek ölçekte)
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

    def kl_takimlar(lig):
        """Ligin süren sezondaki takımları {FotMob id: ad} (adına göre sıralı)."""
        return dict(sorted(((int(t), ad) for ad, t in (G.depo.stadyumlar()['ligler'].get(lig) or {}).items()),
                           key=lambda x: x[1]))

    def kl_lig_degisti(lig_sec, takim_sec):
        secenek = kl_takimlar(lig_sec.value) if lig_sec.value else {}
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
        t = E.tahmin(kl_ev.value, kl_dep.value, kl_taraf.value)
        p, ilk = t['p'], t['skorlar'][0][2]
        ev_ad, dep_ad = kl_ev.options[kl_ev.value], kl_dep.options[kl_dep.value]
        kl_sonuc.content = (
            f'<div class="bar" style="margin-top:6px"><div class="h" style="flex-basis:{p[0] * 100:.1f}%">{yuzde(p[0]) if p[0] > .1 else ""}</div>'
            f'<div class="d" style="flex-basis:{p[1] * 100:.1f}%">{yuzde(p[1]) if p[1] > .1 else ""}</div>'
            f'<div class="a" style="flex-basis:{p[2] * 100:.1f}%">{yuzde(p[2]) if p[2] > .1 else ""}</div></div>'
            f'<div class="lead" style="margin:8px 0">{e(ev_ad)} kazanır {yuzde(p[0])} · beraberlik {yuzde(p[1])} · {e(dep_ad)} '
            f'kazanır {yuzde(p[2])}<br>Beklenen gol: {e(ev_ad)} <b>{fmt(t["lh"])} – {fmt(t["la"])}</b> {e(dep_ad)} · kulüp Elo\'su '
            f'{round(E.puan(kl_ev.value))} – {round(E.puan(kl_dep.value))}</div>'
            '<div class="liste" style="max-width:520px">' + ''.join(
                f'<div class="satir"><span class="disp" style="font-size:1.1rem;font-weight:700">{i} – {j}</span>'
                f'<div class="track"><i style="width:{pr / ilk * 100:.0f}%"></i></div><span class="pv">{fmt(pr * 100, 1)}%</span></div>'
                for i, j, pr in t['skorlar']) + '</div>')

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

    # oyuncu listeleri: (ev kutusu, deplasman kutusu, olasılık işlevi, satır altındaki bilgi)
    def _onceki(S, tur):
        """Oyuncuların önceki iki sezonu (sezonda bir kez hesaplanır; kariyer dizini uygulama açılırken hazırlanır)."""
        return oyuncu_tahmin.onceki_sezonlar(S, G.depo.veri_klasoru, tur)

    def _golcu_listesi(S, i, lam, hk):
        return S.golculer(i, lam, adet=None, onceki=_onceki(S, 'gol'))

    def _asist_listesi(S, i, lam, hk):
        return oyuncu_tahmin.asistciler(S, i, lam, onceki=_onceki(S, 'asist'))

    def _kart_listesi(S, i, lam, hk):
        return oyuncu_tahmin.kartcilar(S, i, hk)

    LISTELER = [
        (golcu_ev, golcu_dep, _golcu_listesi, lambda p: f'{p["g"]} gol · {p["a"]} asist · {fmt(p["xg"], 1)} xG', 0.6),
        (asist_ev, asist_dep, _asist_listesi,
         lambda p: f'{p["a"]} asist · {fmt(p["xa"], 1)} xA' + (f' · {p["kp"]} kilit pas' if p.get('kp') is not None else ''), 0.5),
        (kart_ev, kart_dep, _kart_listesi, lambda p: f'{p["yc"] or 0} sarı · {p["rc"] or 0} kırmızı · {p["mp"]} maç', 0.5),
    ]

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

    def guven_metni(S, p):
        """Model güveni: favorinin olasılığına göre etiket ve modelin geçmişte (Karne) buna benzer olasılık verdiği
        maçlarda favorinin gerçekten kazanma oranı."""
        pmax = max(p)
        fav = ['ev sahibi', 'beraberlik', 'deplasman'][p.index(pmax)]
        etiket, renk = (('yüksek', 'var(--pitch-2)') if pmax >= GUVEN_YUKSEK else ('orta', 'var(--lamp)') if pmax >= GUVEN_ORTA
                        else ('düşük (dengeli maç)', 'var(--bad)'))
        kayitlar = karne.oku_onbellek(G.depo.veri_klasoru)
        oran, n = karne.favori_isabeti(kayitlar, pmax)
        oran_l, n_l = karne.favori_isabeti(kayitlar, pmax, S.lig)
        gecmis = ''
        if n:
            alt, ust = max(0, pmax - karne.GUVEN_PAY), min(1, pmax + karne.GUVEN_PAY)
            gecmis = (f' Model geçmişte en olası sonuca %{round(alt * 100)}–{round(ust * 100)} verdiği {sayi(n)} maçta '
                      f'{yuzde(oran)} tuttu' + (f' (bu ligde {yuzde(oran_l)}, {n_l} maç)' if n_l >= karne.GUVEN_LIG_MIN else '')
                      + '.')
        return (f'<div class="soft" style="text-align:center;font-size:.85rem;margin-top:6px">Model güveni: '
                f'<b style="color:{renk}">{etiket}</b> · favori {fav} {yuzde(pmax)}.{gecmis}</div>')

    def tahmin_ciz():
        S = G.S
        h, a = ev_sec.value, dep_sec.value
        durum['h'], durum['a'] = h, a
        ev_logo.content = takim_logo(G.depo.takim_kimligi(S.lig, S.T[h])).replace('class="logo"', 'class="logo secim-logo"')
        dep_logo.content = takim_logo(G.depo.takim_kimligi(S.lig, S.T[a])).replace('class="logo"', 'class="logo secim-logo"')
        t = S.tahmin(h, a)
        p = t['p']
        pmax = max(p)
        sonuc_ad = [f'{S.T[h]} kazanır', 'Beraberlik', f'{S.T[a]} kazanır']
        i_, j_, pr_ = t['skorlar'][0]
        # pano: renkli çubuk (sayısız) ve altında üç sonuç, beklenen gol, kısa özet ve model güveni; ayrıntılı açıklama
        # "Bu tahmin nasıl hesaplanıyor?" altında
        pz_ = piyasalar(t['hucreler'])
        olasilik.content = (
            f'<div class="ozet-cumle">{ozet_cumlesi(S.T[h], S.T[a], p, pz_)}</div>'
            f'<div class="bar"><div class="h" style="flex-basis:{p[0] * 100:.2f}%"></div>'
            f'<div class="d" style="flex-basis:{p[1] * 100:.2f}%"></div>'
            f'<div class="a" style="flex-basis:{p[2] * 100:.2f}%"></div></div>'
            '<div class="oran" style="margin-top:10px">'
            + ''.join(f'<div class="{"top" if v == pmax else ""}"><div class="k">{e(k)}</div><div class="v">{yuzde(v)}</div></div>'
                      for k, v in zip(sonuc_ad, p))
            + '</div><div style="display:flex;justify-content:center;align-items:baseline;gap:14px;margin-top:8px">'
            f'<span class="soft">Beklenen gol</span><span class="eg">{fmt(t["lh"])} – {fmt(t["la"])}</span></div>'
            '<div class="ozet-cipler">'
            f'<span class="ozet-cip">En olası sonuç: <b>{e(sonuc_ad[p.index(pmax)])}</b> {yuzde(pmax)}</span>'
            f'<span class="ozet-cip">En olası skor: <b>{i_} – {j_}</b> {yuzde(pr_)}</span>'
            f'<span class="ozet-cip">2,5 üst: <b>{yuzde(pz_["ust25"])}</b></span>'
            f'<span class="ozet-cip">Karşılıklı gol: <b>{yuzde(pz_["kg"])}</b></span></div>'
            + guven_metni(S, p))
        aciklama.content = (
            '<div style="line-height:1.5">Beklenen gol: modelin bu maçta her takım için beklediği ortalama gol (soldaki ev '
            'sahibinin, sağdaki deplasmanın); skor olasılıkları bundan hesaplanır. Takım güçleri son sezonların gol ve '
            'xG\'sinden (eski maçların ağırlığı azalır)' + (', kadro değerine göre hafif düzeltmeyle' if S.kadro_degeri else '')
            + '; sonuç olasılıkları maç maç güncellenen Elo puanıyla harmanlanır (%65 gol modeli, %35 Elo). Model güveni: en '
            'olası sonucun olasılığı; yanında modelin geçmişte buna benzer olasılık verdiği maçlarda ne kadar tuttuğu. Kadro '
            'eksikleri: eksik oyuncuların sezondaki gol ve xG payının yarısı kadar beklenen gol düşülür (yerine oynayan açığın '
            'yarısını kapatır sayılır); savunma eksikleri hesaba katılmaz; ana tahmine değil ayrı satıra yansır.</div>')
        # stadyum ve hakem: yaklaşan maçın detayı varsa oradan, yoksa ev sahibinin iç sahası
        fm = G.depo.canli_mac(S, h, a)
        ev_std = stadyum_bul(G.depo.stadyumlar(), S.lig, S.T[h])
        if fm and fm.get('stadyum'):
            std = {'ad': fm['stadyum'], 'sehir': fm.get('sehir'),
                   'kapasite': ev_std.get('kapasite') if ev_std and ev_std.get('ad') == fm['stadyum'] else None}
        else:
            std = ev_std
        oynanan = next((m for m in reversed(S.M) if m.h == h and m.a == a), None)
        def oge(simge, metin, ipucu=''):
            return (f'<span title="{e(ipucu)}"><i class="material-icons">{simge}</i>{e(metin)}</span>' if metin else '')
        z = yerel(fm['baslangic']) if fm and fm.get('baslangic') else None
        parcalar = [
            oge('event', f'{kisa_gun(z.date())} · {z:%H:%M}' if z else ''),
            oge('stadium', ' · '.join(x for x in (std.get('ad'), std.get('sehir')) if x) if std else '',
                f'{sayi(std["kapasite"])} kişilik' if std and std.get('kapasite') else ''),
            oge('sports', (f'Hakem: {fm["hakem"]["ad"]}' + (f' · maç başına {fmt(fm["hakem"]["sariOrt"])} sarı'
                                                             if fm['hakem'].get('sariOrt') is not None else '')
                           if fm.get('hakem') else 'Hakem henüz atanmadı') if fm else '',
                hakem_metni(fm['hakem']) if fm and fm.get('hakem') else ''),
            oge('history', f'Bu sezon oynandı: {oynanan.hg}–{oynanan.ag} ({tarih_uzun(oynanan.d)})' if oynanan else '')]
        bilgi.clear()
        with bilgi:
            ui.html(''.join(parcalar), sanitize=False).style('display:contents')
            hava_yer = ui.html(durum.get('hava', {}).get((S.lig, h, a), ''), sanitize=False).style('display:contents')

        # skor matrisi (0-5 gol)
        hucre = {(i, j): pr for i, j, pr in t['hucreler']}
        N = 6
        alt = [hucre[(i, j)] for i in range(N) for j in range(N)]
        mx = max(alt)
        en = max(hucre, key=hucre.get)
        html = (f'<div class="matris-eksen"><span></span><span>{e(S.T[a])} golleri →</span></div>'
                f'<div class="matris-sar"><div class="matris-dikey">{e(S.T[h])} golleri ↓</div>'
                '<div class="matris"><span class="ax"></span>' + ''.join(f'<span class="ax">{j}</span>' for j in range(N)))
        for i in range(N):
            html += f'<span class="ax">{i}</span>'
            for j in range(N):
                q = hucre[(i, j)]
                al = q / mx
                sinif = ' '.join(c for c in ('best' if (i, j) == en else '',
                                             'real' if oynanan and (oynanan.hg, oynanan.ag) == (i, j) else '') if c)
                html += (f'<span class="{sinif}" title="{i}-{j}: {fmt(q * 100, 1)}%" style="background:color-mix(in srgb,'
                         f'var(--pitch) {round(al * 85)}%,transparent);color:{"#fff" if al > .5 else "inherit"}">{round(q * 100)}</span>')
        matris.content = html + '</div></div>'

        enolasi.clear()
        with enolasi:
            ilk = t['skorlar'][0][2]
            for i, j, pr in t['skorlar']:
                ui.html(f'<div class="satir"><span class="num disp" style="font-size:1.2rem;font-weight:700">{i} – {j}</span>'
                        f'<div class="track"><i style="width:{pr / ilk * 100:.0f}%"></i></div><span class="pv">{fmt(pr * 100, 1)}%</span></div>',
                        sanitize=False).classes('w-full')

        goller.content = piyasa_kartlari(p, piyasalar(t['hucreler']), t['lh'], t['la'], S.T[h], S.T[a])

        guncel = S.yil == SON_SEZON
        golcu_aciklama.text =(f'90 dakika oynarsa en az bir gol atma olasılığı. Takımın beklenen golü, oyuncunun gol ve xG '
                               f'oranına göre dağıtılır. Oran, oyuncunun önceki iki sezonuyla ve mevkisinin ortalamasıyla '
                               f'harmanlanır: sezon başında birkaç maçlık şanslı gidiş olasılığı şişirmez. En az {S.min_esik} '
                               f'dakika oynamış ya da önceki sezonlarda düzenli oynamış oyuncular.'
                               + (' Güncel kadro ve sakatlıklar FotMob\'dan: kadroda olmayan (transfer olan) ve sakat oyuncular '
                                  'listeye alınmaz, şüpheliler işaretlidir.' if guncel else ''))
        # hakemin sertliği: maç başına sarı kartı / ligin ortalaması (hakem atanmışsa; az maçlık hakemde ortalamaya çekilir)
        hk_bilgi = (G.depo.canli_mac(S, h, a) or {}).get('hakem') or {}
        hk = oyuncu_tahmin.hakem_carpani(hk_bilgi)
        durum['hakem'] = hk
        asist_aciklama.text = ('90 dakika oynarsa en az bir asist yapma olasılığı: takımın beklenen asistleri (beklenen golün '
                               '~%75\'i), oyuncunun asist ve xA oranına göre dağıtılır; oran önceki iki sezonla ve mevkinin '
                               'ortalamasıyla harmanlanır.')
        kart_aciklama.text = ('Sarı kart görme olasılığı: oyuncunun 90 dakikadaki sarı kart oranı (ligin ortalamasıyla 10 maçlık '
                              'süre kadar harmanlanır) × maç başına oynadığı süre'
                              + (f' × hakemin sertliği ({e(hk_bilgi["ad"])}: {hk_bilgi.get("mac") or "?"} maçta maç başına '
                                 f'{fmt(hk_bilgi["sariOrt"])} sarı, lig ortalaması {fmt(hk_bilgi["sariLigOrt"])} → ×{fmt(hk, 2)}; '
                                 f'az maç yönetmiş hakemde lig ortalamasına doğru çekilir)'
                                 if hk_bilgi.get('sariOrt') is not None and hk_bilgi.get('sariLigOrt') else
                                 ' (hakem henüz atanmadı; atanınca sertliği de hesaba katılır)') + '.')
        for kutu_ev, kutu_dep, fn, alt, olcek in LISTELER:
            for kutu, i, lam in ((kutu_ev, h, t['lh']), (kutu_dep, a, t['la'])):
                golcu_ciz(kutu, S.T[i], [(p, pr, '') for p, pr in fn(S, i, lam, hk)[:5]], [],
                          'Güncel kadro denetleniyor…' if guncel else '', alt, olcek)
        serit_isaretle()
        G.arka_plan(h2h_ciz(S, S.T[h], S.T[a]))
        G.arka_plan(hava_ciz(S, h, a, hava_yer))
        eksik_kutu.content = ('<div class="faint" style="margin-top:8px;text-align:center;font-size:.8rem">Güncel kadro ve '
                              'sakatlıklar denetleniyor…</div>' if guncel else '')
        # tahmini ilk 11 yalnızca ileride oynanacak bir maç seçiliyse (süren sezonun oynanmamış maçları)
        ileride = guncel and any(m.h == h and m.a == a for m in S.U)
        durum['ilk11_goster'] = ileride
        ilk11_panel.set_visibility(ileride)
        if ileride and durum.get('ilk11_cift') != (S.lig, h, a):  # aynı maçın dakikalık yenilemesinde sahalar titremesin
            durum['ilk11_cift'] = (S.lig, h, a)
            ilk11_ev.content = ilk11_dep.content = '<p class="cap">İlk 11 tahmini hazırlanıyor…</p>'
        if guncel:  # güncel kadroya göre süz (FotMob takım sayfası, bir saat önbellekte)
            durum['istek'] = durum.get('istek', 0) + 1
            G.arka_plan(kadroya_gore(S, h, a, t, durum['istek']))

    async def hava_ciz(S, h, a, yer):
        """Yaklaşan maçın maç saatindeki hava tahmini (yalnızca bilgi; tahmine katılmaz). Son gösterilen satır
        hatırlanır: dakikalık yenilemede satır kaybolup yeniden belirmesin."""
        try:
            hv = await run.io_bound(G.depo.lig_mac_havasi, S, h, a)
        except Exception:  # hava alınamazsa satır gösterilmez
            logger.debug('maç havası alınamadı', exc_info=True)
            hv = None
        icerik = hava_html(hv, kisa=True)
        durum.setdefault('hava', {})[(S.lig, h, a)] = icerik
        if not yer.is_deleted and yer.content != icerik:
            yer.content = icerik

    async def h2h_ciz(S, ev, dep):
        """İki takımın bu ligdeki son 10 karşılaşması (bütün sezonlar) ve özet."""
        maclar = await run.io_bound(G.depo.karsilasmalar, S.lig, ev, dep)
        if G.S is not S or (S.T[ev_sec.value], S.T[dep_sec.value]) != (ev, dep):
            return
        if not maclar:
            h2h_ozet.content = '<p class="cap">Bu ligde (uygulamadaki sezonlarda) aralarında maç yok.</p>'
            h2h.content = ''
            return
        g1 = sum(1 for m in maclar if (m[1] == ev and m[3] > m[4]) or (m[2] == ev and m[4] > m[3]))
        g2 = sum(1 for m in maclar if (m[1] == dep and m[3] > m[4]) or (m[2] == dep and m[4] > m[3]))
        b = len(maclar) - g1 - g2
        gol1 = sum(m[3] if m[1] == ev else m[4] for m in maclar)
        gol2 = sum(m[3] if m[1] == dep else m[4] for m in maclar)
        h2h_ozet.content = (
            f'<div class="lead">Son {len(maclar)} karşılaşma: <b>{e(ev)}</b> {g1} galibiyet · {b} beraberlik · '
            f'<b>{e(dep)}</b> {g2} galibiyet · goller {gol1}–{gol2}</div>'
            f'<div class="bar" style="margin:6px 0 4px"><div class="h" style="flex-basis:{g1 / len(maclar) * 100:.1f}%">'
            f'{g1 or ""}</div><div class="d" style="flex-basis:{b / len(maclar) * 100:.1f}%">{b or ""}</div>'
            f'<div class="a" style="flex-basis:{g2 / len(maclar) * 100:.1f}%">{g2 or ""}</div></div>')
        h2h.content = '<table class="tb"><tbody>' + ''.join(
            f'<tr><td class="cap">{m[0][8:10]}.{m[0][5:7]}.{m[0][:4]}</td><td style="text-align:right">'
            f'{"<b>" if m[3] > m[4] else ""}{e(m[1])}{"</b>" if m[3] > m[4] else ""}</td><td class="hi" style="text-align:center">'
            f'{m[3]} – {m[4]}</td><td>{"<b>" if m[4] > m[3] else ""}{e(m[2])}{"</b>" if m[4] > m[3] else ""}</td></tr>'
            for m in maclar) + '</tbody></table>'

    def golcu_ciz(kutu, takim_adi, liste, cikan, not_, alt=None, olcek=0.6):
        """Bir takımın oyuncu listesi (gol, asist ya da kart olasılığı). alt(oyuncu): satırın altındaki bilgi."""
        alt = alt or LISTELER[0][3]
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

    def eksik_etkisi(S, i, kadro, ilk11=False):
        """Takımın bu sezonki gol üretiminden eksik oyuncuların payı ve beklenen gol çarpanı. Oyuncunun katkısı: tahmini
        gol + xG oranı (önceki sezonlarla ve mevkinin ortalamasıyla harmanlanmış, oyuncu_tahmin.oran) × oynadığı süre;
        sezon başında birkaç golle payı şişmez. Eksik: güncel kadroda olmayan (ayrılan) ya da sakat oyuncu (tam), şüpheli
        (yarım). Yerine oynayan açığın yarısını kapatır sayılır; çarpan en az 0,7. ilk11=True: kadro açıklanan maç
        kadrosudur (kesin_ilk11); maç kadrosunda olmayan tam, yedekte olan yarım eksik sayılır."""
        if not kadro:
            return 1.0, []
        oyuncular = [p for p in S.PLY if S.T[i] in p['t'].split(' / ') and p['min'] > 0]
        onceki = _onceki(S, 'gol')
        katkilar = {p['idx']: oyuncu_tahmin.oran(S, p, 'gol', onceki) * p['min'] / 90 for p in oyuncular}
        toplam = sum(katkilar.values())
        if toplam <= 0:
            return 1.0, []
        eksikler, pay = [], 0.0
        eslesen = {p['n']: takim_veri.kadrodaki(p['n'], kadro, p.get('fm_id')) for p in oyuncular}
        if sum(1 for k in eslesen.values() if k) < len(oyuncular) / 2:  # adlar kaynaklar arasında eşleşmiyor: düzeltme yok
            return 1.0, []
        for p in oyuncular:
            k = eslesen[p['n']]
            agirlik = 1.0 if (k is None or (k['sakat'] and k['sakat'] != 'Doubtful')) else 0.5 if k['sakat'] == 'Doubtful' else 0
            katki = katkilar[p['idx']]
            if agirlik and katki > 0:
                pay += agirlik * katki / toplam
                if ilk11:
                    neden = 'yedekte' if agirlik == 0.5 else 'maç kadrosunda yok'
                else:
                    neden = 'şüpheli' if agirlik == 0.5 else 'sakat' if k else 'kadroda yok'
                eksikler.append((p['n'], neden, katki / toplam))
        return max(0.7, 1 - 0.5 * min(pay, 1)), sorted(eksikler, key=lambda x: -x[2])

    def eksik_ciz(S, h, a, t, etkiler):
        (fh, eh), (fa, ea) = etkiler
        ilk11 = durum.get('ilk11_var')
        if fh > 0.995 and fa > 0.995:
            eksik_kutu.content = ('<div class="soft" style="margin-top:8px;text-align:center">'
                                  + ('İlk 11\'ler açıklandı: gol katkısı olan oyuncuların hepsi ilk 11\'de.' if ilk11 else
                                     'Güncel kadro denetlendi: gol katkısı olan eksik oyuncu yok.') + '</div>')
            return
        # eksiklerin etkisi, modelin (Poisson + Elo harmanı) olasılıklarına göreli değişiklik olarak uygulanır
        once, _ = sonuc_olasiliklari(t['lh'], t['la'], DC_RHO)
        sonra, _ = sonuc_olasiliklari(t['lh'] * fh, t['la'] * fa, DC_RHO)
        p = [t['p'][k] * sonra[k] / once[k] if once[k] else t['p'][k] for k in range(3)]
        p = [x / sum(p) for x in p]

        def liste(ad, f, eksik):
            if not eksik:
                return f'<b>{e(ad)}</b>: eksik yok'
            lam = t['lh' if ad == S.T[h] else 'la']
            etki = (f'beklenen gol {fmt(lam)} → {fmt(lam * f)}' if abs(lam * f - lam) >= 0.01
                    else 'gol katkıları küçük, tahmine etkisi yok')
            return (f'<b>{e(ad)}</b> ({etki}): ' + ', '.join(
                f'{e(n)} <span class="faint">({d}' + (f', gol payı %{round(s * 100)}' if s >= 0.01 else '') + ')</span>'
                for n, d, s in eksik[:4]) + (f' <span class="faint">ve {len(eksik) - 4} oyuncu daha</span>' if len(eksik) > 4 else ''))
        eksik_kutu.content = (
            '<div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--board-line)">'
            f'<div class="soft" style="text-align:center"><b>{"Açıklanan ilk 11&#39;lere göre" if ilk11 else "Eksik oyuncularla"}</b>: '
            f'{e(S.T[h])} {yuzde(p[0])} · beraberlik {yuzde(p[1])} · {e(S.T[a])} {yuzde(p[2])}</div>'
            f'<div class="soft" style="font-size:.82rem;margin-top:4px;line-height:1.5">{liste(S.T[h], fh, eh)}<br>'
            f'{liste(S.T[a], fa, ea)}</div></div>')

    def suz(adaylar, kadro, ilk11=False):
        """Güncel kadroya göre: kadroda olmayan ve sakat olan çıkar (nedeniyle), şüpheli işaretlenir; ilk 5 kalır.
        ilk11=True (kesin ilk 11 açıklandı): yalnızca ilk 11'dekiler kalır; yedekler ve maç kadrosunda olmayanlar çıkar."""
        kayit = [(p, pr, takim_veri.kadrodaki(p['n'], kadro, p.get('fm_id'))) for p, pr in adaylar]
        if kadro and not any(k for _, _, k in kayit[:8]):  # adlar hiç eşleşmediyse süzme (kaynak farkı)
            return [(p, pr, '') for p, pr in adaylar[:5]], []
        kalan, cikan = [], []
        for p, pr, k in kayit:
            if len(kalan) >= 5:
                break
            if ilk11:
                if k and k.get('ilk11'):
                    kalan.append((p, pr, ''))
                elif len(cikan) < 4:
                    cikan.append((p['n'], 'yedekte' if k else 'maç kadrosunda yok'))
                continue
            if k is None:
                cikan.append((p['n'], f'{p["ayrildi"][0]} kulübüne gitti' if (p.get('ayrildi') or [''])[0] else 'güncel kadroda yok'))
            elif k['sakat'] and k['sakat'] != 'Doubtful':
                cikan.append((p['n'], f'sakat, dönüş: {takim_veri.donus_metni(k["sakat"])}'))
            else:
                kalan.append((p, pr, 'şüpheli' if k['sakat'] == 'Doubtful' else ''))
        return kalan, cikan

    async def mac_kadrosu(S, h, a):
        """Maçın FotMob kadrosu (yalnızca canlı skor listesindeki, yani önümüzdeki birkaç gündeki maçlar): mac_ozeti
        kadro biçimi {'tur', 'ev', 'dep'} ya da None. tur: 'standard' açıklanmış kesin kadro (kalıcı saklanır),
        'predicted' FotMob'un tahmini, 'lastStarting11' önceki maçın 11'i (bu ikisi MAC_KADRO_SN boyunca saklanır)."""
        fm = G.depo.canli_mac(S, h, a)
        if not fm or fm.get('durum', 'baslamadi') != 'baslamadi':
            return None
        onbellek = durum.setdefault('mac_kadro', {})
        eski = onbellek.get(fm['id'])
        if eski and (eski[1].get('tur') == 'standard' or time.time() - eski[0] < MAC_KADRO_SN):
            return eski[1]
        try:
            ay = await run.io_bound(ayrinti, fm['id'], G.depo.g.ham)
        except Exception:
            logger.debug('maç kadrosu alınamadı: %s', fm['id'], exc_info=True)
            return eski[1] if eski else None
        k = ay.get('kadro')
        if k:
            onbellek[fm['id']] = (time.time(), k)
        return k

    def kesin_ilk11(k, h, a):
        """Açıklanmış kesin ilk 11'ler (kadro türü 'standard'): {takım indeksi: [{'id', 'ad', 'sakat', 'ilk11'}]} (yedekler
        'şüpheli' gibi yarım eksik sayılır) ya da None."""
        if not k or k.get('tur') != 'standard' or not (k.get('ev') or {}).get('ilk11') or not (k.get('dep') or {}).get('ilk11'):
            return None

        def liste(tk):
            return ([{'id': p['id'], 'ad': p['ad'], 'sakat': None, 'ilk11': True} for p in tk['ilk11']]
                    + [{'id': p['id'], 'ad': p['ad'], 'sakat': 'Doubtful', 'ilk11': False} for p in tk.get('yedek') or []])
        return {h: liste(k['ev']), a: liste(k['dep'])}

    def ilk11_ciz(S, h, a, k, sayfalar):
        """İki takımın tahmini ilk 11'i: açıklanmış kesin kadro > FotMob'un tahmini > uygulamanın "en güçlü 11"i (bu sezon
        oynamış, sakat olmayanlar; puan ve süreye göre, takımın son dizilişinde)."""
        kaynaklar = set()
        for kutu, i, taraf in ((ilk11_ev, h, 'ev'), (ilk11_dep, a, 'dep')):
            tid = G.depo.takim_kimligi(S.lig, S.T[i])
            fk = (k or {}).get(taraf) or {}
            if k and k.get('tur') in ('standard', 'predicted') and len(fk.get('ilk11') or []) == 11:
                oyuncular, dizilis = fk['ilk11'], fk.get('dizilis') or ''
                kaynak = 'kesin ilk 11 (açıklandı)' if k['tur'] == 'standard' else 'FotMob\'un tahmini'
            elif sayfalar.get(i):
                v = sayfalar[i]
                adaylar, disarida, mac = takim_veri.ilk11_adaylari(S, S.T[i], v['kadro'])
                dizilis = (v.get('son_ilk11') or {}).get('dizilis') or '4-2-3-1'
                oyuncular = takim_veri.en_cok_oynayan(adaylar, dizilis, mac)
                no = {takim_veri.sadelestir(x['ad']): x['no'] for x in v['kadro']}
                supheli = {p['n'] for p in adaylar if p.get('_supheli')}
                for p in oyuncular:
                    p['no'] = no.get(takim_veri.sadelestir(p['ad']), '')
                    p['sakat'] = p['ad'] in supheli
                kaynak = 'uygulamanın tahmini' + (f' · sakat: {", ".join(disarida[:4])}' if disarida else '')
            else:
                kutu.content = (f'<div class="disp" style="font-weight:700">{takim_logo(tid)}{e(S.T[i])}</div>'
                                '<p class="cap">Bu takım için ilk 11 tahmini yapılamadı.</p>')
                continue
            kaynaklar.add(kaynak.split(' · ')[0])
            kutu.content = (f'<div class="disp" style="font-weight:700;font-size:1.05rem">{takim_logo(tid)}{e(S.T[i])}'
                            f'<span class="cap" style="font-weight:400"> · {e(dizilis)} · {e(kaynak)}</span></div>'
                            + _saha(oyuncular))
        ilk11_not.text = ('Kaynak sırası: açıklanmış kesin ilk 11 (maçtan ~1 saat önce), yoksa FotMob\'un tahmini (önümüzdeki '
                          'birkaç günün maçlarında), o da yoksa uygulamanın tahmini: bu sezon oynamış ve sakat olmayan oyunculardan, '
                          'FotMob puanı ve süre payına göre, takımın son maçtaki dizilişinde. ✚: şüpheli. Oyuncuya tıklayınca '
                          'kartı açılır.')

    async def kadroya_gore(S, h, a, t, istek):
        kadrolar, etkiler, notlar, sayfalar = {}, [], {}, {}
        k = await mac_kadrosu(S, h, a)
        ilk11 = kesin_ilk11(k, h, a)
        durum['ilk11_var'] = bool(ilk11)
        for i in (h, a):
            tid = G.depo.takim_kimligi(S.lig, S.T[i])
            if tid is not None:
                try:
                    sayfalar[i] = await run.io_bound(takim_veri.takim_sayfasi, tid, G.depo.g.ham)
                except Exception:
                    logger.debug('takım sayfası alınamadı: %s', tid, exc_info=True)
            if ilk11:
                kadrolar[i], notlar[i] = ilk11[i], 'İlk 11 açıklandı: liste kesin kadroya göre (yalnızca ilk 11\'dekiler).'
                etkiler.append(eksik_etkisi(S, i, ilk11[i], ilk11=True))
            elif i in sayfalar:
                kadrolar[i], notlar[i] = sayfalar[i]['kadro'], ''
                etkiler.append(eksik_etkisi(S, i, sayfalar[i]['kadro']))
            else:
                kadrolar[i] = None
                notlar[i] = '' if tid is None else 'Güncel kadro alınamadı; sezon verisine göre.'
                etkiler.append((1.0, []))
        if istek != durum.get('istek') or G.S is not S:
            return
        if durum.get('ilk11_goster'):
            ilk11_ciz(S, h, a, k, sayfalar)
        for kutu_ev, kutu_dep, fn, alt, olcek in LISTELER:
            for kutu, i, lam in ((kutu_ev, h, t['lh']), (kutu_dep, a, t['la'])):
                adaylar = fn(S, i, lam, durum.get('hakem', 1.0))
                if kadrolar[i] is None:
                    kalan, cikan = [(p, pr, '') for p, pr in adaylar[:5]], []
                else:
                    kalan, cikan = suz(adaylar, kadrolar[i], ilk11=bool(ilk11))
                golcu_ciz(kutu, S.T[i], kalan, cikan, notlar[i], alt, olcek)
        eksik_ciz(S, h, a, t, etkiler)

    def serit_isaretle():
        for el, (h, a) in serit_ogeler:
            if (h, a) == (durum['h'], durum['a']):
                el.classes(add='sec')
            else:
                el.classes(remove='sec')

    serit_ogeler = []

    def tur_degistir(adim):
        turlar = durum.get('turlar') or []
        if durum.get('tur') in turlar:
            k = turlar.index(durum['tur']) + adim
            if 0 <= k < len(turlar):
                durum['tur'] = turlar[k]
                serit_ciz()
                serit_isaretle()

    def ust_bilgi(S, h, a):
        """Yaklaşan maçın şeritteki ek satırları: stadyum ve (atandıysa) hakem."""
        fm = G.depo.canli_mac(S, h, a)
        std = {'ad': fm['stadyum']} if fm and fm.get('stadyum') else stadyum_bul(G.depo.stadyumlar(), S.lig, S.T[h])
        return (f'<small>{e(std["ad"])}</small>' if std else '') + (f'<small>Hakem: {e(fm["hakem"]["ad"])}</small>' if fm and fm.get('hakem') else '')

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
                            f'{ust_bilgi(S, m.h, m.a)}', sanitize=False)
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
                    ek = '<small>Ertelendi / iptal</small>' if m['iptal'] else (ust_bilgi(S, h, a) if h is not None and a is not None else '')
                    sinif, govde = 'fx', (f'<small>{gun}</small><b><span>{ad(m["ev_id"], m["ev_ad"])}</span></b>'
                                          f'<b><span>{ad(m["dep_id"], m["dep_ad"])}</span></b>{ek}')
                el = ui.element('div').classes(sinif)
                with el:
                    ui.html(govde, sanitize=False)
                if h is not None and a is not None:
                    el.on('click', lambda _, h=h, a=a: sec(h, a))
                    serit_ogeler.append((el, (h, a)))

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
        c = G.depo.g.canli or {}
        imza = tuple((m.get('id'), m.get('durum'), m.get('baslangic'), m.get('stadyum'), (m.get('hakem') or {}).get('ad'))
                     for m in (c.get('maclar') or []) + (c.get('yakinda') or []) if m.get('lig') == G.S.lig)
        if durum.get('canli_imza') == (G.S.lig, imza):
            return
        durum['canli_imza'] = (G.S.lig, imza)
        serit_ciz()
        tahmin_ciz()

    G.dinle('canli', canli_yenile)
    return yenile
