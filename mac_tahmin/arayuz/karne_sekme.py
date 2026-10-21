"""Tahmin karnesi sekmesi: modelin ne kadar doğru çalıştığı, sade bir dille. Her maç, yalnızca o haftadan önceki
maçlarla kurulan modelle tahmin edilip gerçek sonuçla karşılaştırılır (karne.py). Sırasıyla: dört cümlelik özet, güvene
göre başarı (model emin olduğunda gerçekten daha çok mu tutturuyor?), hafta hafta başarı (basit yöntemle yan yana),
olasılıkların dürüstlüğü (kalibrasyon), lig lig, son tahminler, goller; teknik ölçüler (log-kayıp, Brier) en altta,
açılır kutuda. Süzgeç: sezon ve lig."""
from collections import defaultdict

from nicegui import run, ui

from .. import karne
from ..sezon import LIG_ADI, LIGLER, SON_SEZON
from .ortak import e, fmt, kisa_gun, yuzde

ID, AD = 'karne', 'Karne'
TEMBEL = True
# güven dilimleri: en olası sonucun olasılığına göre (Maç tahmini sekmesindeki model güveniyle aynı sınırlar)
GUVEN = [('Emin (%60 ve üstü)', 0.60, 1.01), ('Orta (%45–60)', 0.45, 0.60), ('Dengeli maç (%45 altı)', 0.0, 0.45)]
HAFTA_SAYISI = 30  # hafta hafta grafikte en çok bu kadar son hafta
KAL_EN_AZ = 20  # kalibrasyon grafiğinde bir dilimin gösterilmesi için en az olasılık sayısı (azı çok oynak)


def _sonuc(r):
    return 0 if r[8] > r[9] else 1 if r[8] == r[9] else 2


def _tuttu(r):
    p = r[5:8]
    return p.index(max(p)) == _sonuc(r)


def guven_dilimleri(K):
    """[(ad, maç sayısı, favori tuttu oranı, modelin ortalama söylediği)] (GUVEN sırasıyla; boş dilim atlanır)."""
    out = []
    for ad, alt, ust in GUVEN:
        L = [r for r in K if alt <= max(r[5:8]) < ust]
        if L:
            out.append((ad, len(L), sum(_tuttu(r) for r in L) / len(L), sum(max(r[5:8]) for r in L) / len(L)))
    return out


def haftalik(K):
    """Hafta hafta: [(hafta başı, maç, model tuttu, hep ev sahibi tuttu)], eskiden yeniye."""
    h = defaultdict(lambda: [0, 0, 0])
    for r in K:
        x = h[karne._hafta_basi(r[2])]
        x[0] += 1
        x[1] += _tuttu(r)
        x[2] += _sonuc(r) == 0
    return [(g, *v) for g, v in sorted(h.items())]


def kalibrasyon_sapmasi(tablo):
    """Kalibrasyon dilimlerinde (karne.kalibrasyon_tablosu) söylenen ile gerçekleşen arasındaki ortalama fark: beklenen
    kalibrasyon hatası, yüzde puanı (olasılık sayısıyla ağırlıklı). Boş tabloda None."""
    h = karne.kalibrasyon_hatasi(tablo)
    return None if h is None else h * 100


def kalibrasyon_noktalari(tablo, en_az=KAL_EN_AZ):
    """Grafik noktaları: en az en_az olasılıklı dilimler; nokta büyüklüğü olasılık sayısıyla artar."""
    return [{'value': [round(d['tahmin'] * 100, 1), round(d['oran'] * 100, 1)], 'name': f'{d["n"]} olasılık',
             'symbolSize': round(min(22, 6 + d['n'] ** 0.5 / 3))} for d in tablo if d['n'] >= en_az]


def kalibrasyon_html(tablo):
    """Kalibrasyon tablosu: dilim, olasılık sayısı, modelin dediği, gerçekte olan ve fark (yüzde puanı)."""
    if not tablo:
        return ''
    satir = []
    for d in tablo:
        f = (d['oran'] - d['tahmin']) * 100
        satir.append(f'<tr><td>%{round(d["alt"] * 100)}–{round(d["ust"] * 100)}</td><td>{d["n"]}</td>'
                     f'<td>{yuzde(d["tahmin"])}</td><td class="hi">{yuzde(d["oran"])}</td>'
                     f'<td style="color:{"var(--bad)" if abs(f) >= 5 and d["n"] >= KAL_EN_AZ else "inherit"}">'
                     f'{"+" if f >= 0 else "−"}{fmt(abs(f), 1)}</td></tr>')
    return ('<table class="tb"><thead><tr><th>Dilim</th><th>Olasılık</th><th>Dediği (ort.)</th><th>Gerçekte</th>'
            '<th>Fark (puan)</th></tr></thead><tbody>' + ''.join(satir) + '</tbody></table>')


def kur(G):
    d = {'kayit': []}
    with ui.column().classes('panel'):
        ui.html('<h3>Model ne kadar doğru?</h3>', sanitize=False)
        ui.label('Her maç, yalnızca o haftadan önce oynanmış maçlarla kurulan modelle tahmin edildi ve gerçek sonuçla '
                 'karşılaştırıldı: maç günü yapılmış tahminin aynısı, sonradan öğrenilen hiçbir şey kullanılmadı. Süren ve '
                 'geçen sezon, bütün ligler.').classes('lead')
        ui.label(f'Not: Model ayarları (yarı ömür, xG payı, Elo harmanı…) {SON_SEZON - 1} sezonunda seçildi; o sezonun sonuçları '
                 f'"ayar dönemi (örneklem içi)" olduğundan iyi görünebilir. Gerçek sınav {SON_SEZON} sezonudur '
                 '(doğrulama). Karne, ekrandaki tahminle aynı işlevi (Poisson + Dixon-Coles + Elo harmanı) ölçer; yalnızca kadro '
                 'değeri eğimi dışarıda: elde yalnızca bugünkü kadro değerleri var, geçmiş maçlarda kullanmak sonradan '
                 'öğrenilen bilgi olur.').classes('cap')
        with ui.row().classes('w-full items-end gap-3'):
            sezon_sec = ui.select({0: 'İki sezon', SON_SEZON: 'Bu sezon (doğrulama)', SON_SEZON - 1: 'Geçen sezon (ayar dönemi, örneklem içi)'}, value=0,
                                  label='Sezon', on_change=lambda _: ciz()).props('outlined dense options-dense').style('min-width:150px')
            lig_sec = ui.select({'': 'Bütün ligler', **{l[0]: l[1] for l in LIGLER}}, value='', label='Lig',
                                on_change=lambda _: ciz()).props('outlined dense options-dense').style('min-width:200px')
            durum = ui.label().classes('cap')
        ozet = ui.html('', sanitize=False).classes('w-full')
    with ui.row().classes('w-full gap-4 items-start'):
        with ui.column().classes('panel').style('flex:1 1 380px;width:auto'):
            ui.html('<h3>Emin olduğunda daha mı çok tutturuyor?</h3>', sanitize=False)
            guven = ui.html('', sanitize=False).classes('w-full')
        with ui.column().classes('panel').style('flex:1 1 380px;width:auto'):
            ui.html('<h3>Söylediği olasılıklar dürüst mü?</h3>', sanitize=False)
            kal_yazi = ui.label().classes('cap')
            grafik = ui.echart({
                'animation': False, 'tooltip': {'trigger': 'item'},
                'grid': {'left': 50, 'right': 16, 'top': 16, 'bottom': 44},
                'xAxis': {'type': 'value', 'min': 0, 'max': 100, 'name': 'Modelin dediği (%)', 'nameLocation': 'middle', 'nameGap': 26},
                'yAxis': {'type': 'value', 'min': 0, 'max': 100, 'name': 'Gerçekte olan (%)'},
                'series': [{'type': 'line', 'data': [[0, 0], [100, 100]], 'showSymbol': False, 'silent': True,
                            'lineStyle': {'type': 'dashed', 'color': '#8a9088'}},
                           {'type': 'scatter', 'data': [], 'symbolSize': 9, 'itemStyle': {'color': '#2f7a57'}}],
            }).classes('w-full').style('height:280px')
            with ui.expansion('Dilim dilim kalibrasyon tablosu', icon='table_rows').classes('w-full').props('dense'):
                kal_tablo = ui.html('', sanitize=False).classes('w-full kaydir')
    with ui.column().classes('panel'):
        ui.html('<h3>Hafta hafta</h3>', sanitize=False)
        hafta_yazi = ui.label().classes('cap')
        hafta_grafik = ui.echart({
            'animation': False, 'tooltip': {'trigger': 'axis'}, 'legend': {'bottom': 0},
            'grid': {'left': 44, 'right': 16, 'top': 16, 'bottom': 56},
            'xAxis': {'type': 'category', 'data': [], 'axisLabel': {'fontSize': 10}},
            'yAxis': {'type': 'value', 'min': 0, 'max': 100, 'name': '%'},
            'series': [{'name': 'Model (o hafta)', 'type': 'bar', 'itemStyle': {'color': 'rgba(47,122,87,.35)'}, 'data': []},
                       {'name': 'Model (4 haftalık ortalama)', 'type': 'line', 'smooth': True, 'showSymbol': False,
                        'lineStyle': {'width': 3}, 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                       {'name': 'Hep ev sahibi (4 haftalık ortalama)', 'type': 'line', 'smooth': True, 'showSymbol': False,
                        'lineStyle': {'width': 2, 'type': 'dashed'}, 'itemStyle': {'color': '#8a9088'}, 'data': []}],
        }).classes('w-full').style('height:280px')
    with ui.row().classes('w-full gap-4 items-start'):
        with ui.column().classes('panel').style('flex:1 1 420px;width:auto'):
            ui.html('<h3>Lig lig</h3>', sanitize=False)
            ligler = ui.html('', sanitize=False).classes('w-full kaydir')
        with ui.column().classes('panel').style('flex:1 1 420px;width:auto'):
            ui.html('<h3>Goller: alt/üst ve karşılıklı gol</h3>', sanitize=False)
            goller = ui.html('', sanitize=False).classes('w-full kaydir')
    with ui.column().classes('panel'):
        with ui.row().classes('w-full items-center'):
            ui.html('<h3>Son tahminler</h3>', sanitize=False)
            ui.space()
            yalniz = ui.toggle({'hepsi': 'Hepsi', 'tutmayan': 'Yalnızca tutmayanlar'}, value='hepsi',
                               on_change=lambda _: ciz()).props('dense no-caps unelevated toggle-color=primary')
        son = ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:520px;overflow-y:auto')
    with ui.expansion('Teknik ölçüler (log-kayıp, Brier)', icon='functions').classes('w-full panel').props('dense'):
        teknik = ui.html('', sanitize=False).classes('w-full')

    def sec():
        return [r for r in d['kayit'] if (not sezon_sec.value or r[1] == sezon_sec.value) and (not lig_sec.value or r[0] == lig_sec.value)]

    def ciz():
        K = sec()
        o = karne.ozet(K)
        if not o:
            ozet.content = '<p class="cap">Bu seçimde tahmin yok.</p>'
            for oge in (guven, ligler, son, goller, teknik, kal_tablo):
                oge.content = ''
            return
        n = o['n']
        gd = guven_dilimleri(K)
        emin = next((x for x in gd if x[0].startswith('Emin')), None)
        fark = (o['isabet'] - o['ev_isabet']) * 100
        sapma = kalibrasyon_sapmasi(o['kalibrasyon_tablosu'])

        def kart(buyuk, cumle, alt):
            return (f'<div class="dg-kart"><div class="dg-sayi">{buyuk}</div><div class="dg-cumle">{cumle}</div>'
                    f'<div class="cap">{alt}</div></div>')
        ozet.content = '<div class="dg-izgara">' + ''.join((
            kart(f'{round(o["isabet"] * 100)} / 100', 'maçta favoriyi bildi',
                 f'{n} maçta, en olası gördüğü sonuç (ev, beraberlik ya da deplasman) gerçekleşti. Futbolda en iyi modeller '
                 'de ancak yarıya yakınını bilir: üç sonuç var ve şans payı büyük.'),
            kart(f'{round(emin[2] * 100)} / 100' if emin else '–', 'maçta bildi, emin olduğunda',
                 f'Favoriye %60 ve üstü verdiği {emin[1]} maçta.' if emin else 'Bu seçimde model hiç %60 ve üstü vermemiş.'),
            kart(f'{"+" if fark >= 0 else "−"}{fmt(abs(fark), 0)}', 'maç fazla bildi (her 100 maçta)',
                 f'"Hep ev sahibi kazanır" diyen birine göre (o yöntem {round(o["ev_isabet"] * 100)} / 100 bilir).'),
            kart(f'±{fmt(sapma, 1)}' if sapma is not None else '–', 'puan: olasılıkların sapması',
                 'Model "%70" dediğinde gerçekte ne kadar oldu? Ortalama fark bu kadar yüzde puanı; küçük olması '
                 'olasılıkların dürüst olduğunu gösterir.'))) + '</div>'
        guven.content = ('<table class="tb"><thead><tr><th>Model ne kadar emindi?</th><th>Maç</th><th>Dediği (ort.)</th>'
                         '<th>Gerçekte bildi</th></tr></thead><tbody>' + ''.join(
                             f'<tr><td>{e(ad)}</td><td>{m}</td><td>{yuzde(soy)}</td><td class="hi">{yuzde(t)}'
                             f'<div class="sc-bar" style="width:120px"><i style="width:{round(t * 100)}%"></i></div></td></tr>'
                             for ad, m, t, soy in gd) + '</tbody></table>'
                         '<p class="cap">İyi bir model emin olduğunda daha çok tutturur ve "dediği" ile "gerçekte bildiği" '
                         'birbirine yakın olur. Dengeli maçlarda en olası sonuç bile düşük olasılıklıdır; orada çok tutmaması '
                         'normaldir.</p>')
        grafik.options['series'][1]['data'] = kalibrasyon_noktalari(o['kalibrasyon_tablosu'])
        grafik.update()
        kal_yazi.text = ('Her nokta bir olasılık dilimi (her maçın ev, beraberlik ve deplasman olasılıkları ayrı ayrı): yatayda '
                         'modelin dediği, dikeyde o tahminlerin gerçekleşme oranı; büyük nokta çok tahmin demek. Noktalar '
                         'kesikli çizgiye ne kadar yakınsa olasılıklar o kadar dürüst: "%60" dediği şeyler gerçekten ~%60 oluyor '
                         f'demektir. Ortalama sapma (beklenen kalibrasyon hatası, ECE): ±{fmt(sapma, 1)} puan.')
        kal_tablo.content = (kalibrasyon_html(o['kalibrasyon_tablosu'])
                             + f'<p class="cap">Fark: gerçekte olan eksi modelin dediği. {KAL_EN_AZ} olasılıktan az olan dilimler '
                             'grafikte gösterilmez (çok oynak); kırmızı: yeterince tahminli dilimde 5 puan ve üstü sapma.</p>')
        hf = haftalik(K)[-HAFTA_SAYISI:]
        ort = lambda i, j: round(sum(x[j] for x in hf[max(0, i - 3):i + 1]) / sum(x[1] for x in hf[max(0, i - 3):i + 1]) * 100, 1)  # noqa: E731
        hafta_grafik.options['xAxis']['data'] = [kisa_gun(g) for g, *_ in hf]
        hafta_grafik.options['series'][0]['data'] = [{'value': round(t / m * 100, 1), 'name': f'{m} maç'} for _, m, t, _ in hf]
        hafta_grafik.options['series'][1]['data'] = [ort(i, 2) for i in range(len(hf))]
        hafta_grafik.options['series'][2]['data'] = [ort(i, 3) for i in range(len(hf))]
        hafta_grafik.update()
        ustte = sum(1 for i in range(len(hf)) if ort(i, 2) > ort(i, 3))
        hafta_yazi.text = (f'Son {len(hf)} hafta: çubuklar o haftanın bilme oranı, çizgiler 4 haftalık ortalama. Model, 4 haftalık '
                           f'ortalamada {len(hf)} haftanın {ustte} tanesinde "hep ev sahibi" yönteminin önünde. Tek bir hafta '
                           'az maçla çok oynaktır; çizgiye bakmak daha doğru.')
        satirlar = []
        for l in LIGLER:
            lk = [r for r in K if r[0] == l[0]]
            ol = karne.ozet(lk)
            if not ol:
                continue
            em = next((x for x in guven_dilimleri(lk) if x[0].startswith('Emin')), None)
            iyi = (1 - ol['log_kayip'] / ol['bilgisiz_log_kayip']) * 100
            satirlar.append((ol['isabet'], f'<tr><td>{e(l[1])}</td><td>{ol["n"]}</td><td class="hi">{yuzde(ol["isabet"])}</td>'
                                           f'<td>{yuzde(em[2]) if em else "–"}</td><td>{yuzde(ol["ev_isabet"])}</td>'
                                           f'<td style="color:{"var(--pitch-2)" if iyi > 0 else "var(--bad)"};font-weight:700">'
                                           f'{"+" if iyi > 0 else ""}%{fmt(iyi, 1)}</td></tr>'))
        ligler.content = ('<table class="tb"><thead><tr><th>Lig</th><th>Maç</th><th>Bildi</th><th>Emin olduğunda</th>'
                          '<th>Hep ev sahibi</th><th>Bilgisizden iyi</th></tr></thead><tbody>'
                          + ''.join(s for _, s in sorted(satirlar, key=lambda x: -x[0])) + '</tbody></table>'
                          '<p class="cap">Bilgisizden iyi: her maça ligin genel oranlarını vermeye göre olasılıkların ne kadar '
                          'iyi olduğu (teknik ölçü: log-kayıp). Artı iyi; bazı liglerde favoriyi bilmek doğası gereği zordur.</p>')
        gs = karne.gol_ozeti(K)
        goller.content = ('<table class="tb"><thead><tr><th>Tahmin</th><th>Maç</th><th>Bildi</th><th>Model ort.</th>'
                          '<th>Gerçekte</th></tr></thead><tbody>' + ''.join(
                              f'<tr><td><b>{e(g["ad"])}</b></td><td>{g["n"]}</td><td class="hi">{yuzde(g["isabet"])}</td>'
                              f'<td>{yuzde(g["tahmin"])}</td><td>{yuzde(g["oran"])}</td></tr>' for g in gs) + '</tbody></table>'
                          '<p class="cap">Bildi: %50 üstü "olur", altı "olmaz" dendiğinde tutma oranı. "Model ort." ile "Gerçekte" '
                          'yakınsa model golleri doğru düzeyde bekliyor.</p>') if gs else '<p class="cap">Gol tahmini kaydı yok.</p>'
        liste = [r for r in sorted(K, key=lambda r: r[2], reverse=True) if yalniz.value == 'hepsi' or not _tuttu(r)][:60]
        son_satir = []
        for r in liste:
            p, sonuc, tuttu = r[5:8], _sonuc(r), _tuttu(r)
            son_satir.append(
                f'<tr><td class="cap">{r[2][8:10]}.{r[2][5:7]}.{r[2][:4]}</td><td class="cap">{e(LIG_ADI.get(r[0], r[0]))}</td>'
                f'<td style="text-align:right">{e(r[3])}</td><td class="hi" style="text-align:center">{r[8]} – {r[9]}</td><td>{e(r[4])}</td>'
                + ''.join(f'<td style="{"font-weight:700;" if k == sonuc else ""}text-align:right">{yuzde(p[k])}</td>' for k in range(3))
                + f'<td style="color:{"var(--pitch-2)" if tuttu else "var(--bad)"};font-weight:700">{"✓" if tuttu else "✗"}</td></tr>')
        son.content = ('<table class="tb"><thead><tr><th>Tarih</th><th>Lig</th><th style="text-align:right">Ev</th><th>Skor</th>'
                       '<th>Deplasman</th><th style="text-align:right">Ev</th><th style="text-align:right">B</th>'
                       '<th style="text-align:right">D</th><th></th></tr></thead><tbody>' + ''.join(son_satir) + '</tbody></table>'
                       '<p class="cap">Yüzdeler maçtan önce verilen olasılıklar; kalın olan gerçekleşen sonuca verilen. ✓: en olası '
                       'görülen sonuç gerçekleşti. %35\'le favori olan bir takımın kaybetmesi "hata" değildir: o maçta her sonuç '
                       'mümkündü.</p>')
        iyilesme = (1 - o['log_kayip'] / o['bilgisiz_log_kayip']) * 100
        teknik.content = (
            '<div class="tiles">' + ''.join(f'<div class="tile"><span class="num">{v}</span><small>{a}</small></div>' for a, v in (
                ('Log-kayıp', fmt(o['log_kayip'], 3)), ('Bilgisiz tahminin', fmt(o['bilgisiz_log_kayip'], 3)),
                ('Brier', fmt(o['brier'], 3)), ('Kalibrasyon hatası (ECE)', fmt(o['ece'], 3)))) + '</div>'
            f'<p class="cap" style="margin-top:6px"><b>Log-kayıp</b> ve <b>Brier</b> düşük olan iyidir; yalnızca "bildi mi" '
            f'değil olasılıkların kendisini ölçer (%90 deyip yanılmak, %55 deyip yanılmaktan çok daha pahalıdır). Modeldeki '
            f'her değişiklik bu ölçüyle sınanır. <b>Bilgisiz tahmin</b>: her maça ligin genel oranlarını (ev '
            f'%{round(o["oran"][0] * 100)}, beraberlik %{round(o["oran"][1] * 100)}, deplasman %{round(o["oran"][2] * 100)}) '
            f'vermek; model bundan %{fmt(iyilesme, 1)} daha iyi.</p>')

    async def yenile():
        d['kayit'] = karne.oku(G.depo.veri_klasoru)
        if not d['kayit']:
            durum.text = 'İlk kez hesaplanıyor (birkaç dakika sürebilir)…'
        else:
            ciz()
            durum.text = 'Yeni maçlar denetleniyor…'
        yeni = await run.io_bound(karne.guncelle, G.depo.veri_klasoru)
        if yeni or not d['kayit']:
            d['kayit'] = karne.oku(G.depo.veri_klasoru)
            ciz()
        durum.text = f'{len(d["kayit"])} tahmin' + (f' ({yeni} yeni)' if yeni else '')

    return yenile
