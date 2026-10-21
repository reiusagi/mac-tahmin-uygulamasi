"""Oyuncular sekmesi: rol kartları, süzgeçler, sıralanabilir ve sayfalı oyuncu tablosu, bitiricilik grafiği.
Tablo Python tarafında süzülür, sıralanır ve sayfalanır; tarayıcıya yalnızca görünen sayfa gider."""
from nicegui import ui

from ..sezon import DETAY, POS, ROL, YAS_GRUPLARI, mevki_adi, sadelestir
from . import disa_aktar
from .ortak import KAYNAK, e, fmt, kucuk, sayi, tr_anahtar

ID, AD = 'oyuncular', 'Oyuncular'
TEMBEL = True  # rol kartları ve tablo: yalnızca sekme açıkken
# tablo sütunları: (oyuncu sözlüğündeki alan, başlık). Yeni sütun için buraya ekle; değer goster() ile biçimlenir.
SUTUNLAR = [('n', 'Oyuncu'), ('t', 'Takım'), ('pos', 'Mevki'), ('yas', 'Yaş'), ('rol', 'Rol'), ('mp', 'Maç'), ('min', 'Dk'),
            ('g', 'Gol'), ('xg', 'xG'), ('a', 'Asist'), ('xa', 'xA'), ('sh', 'Şut'), ('kp', 'Kilit pas'), ('yc', 'Sarı'),
            ('rc', 'Kırmızı')]
ORAN = {'g', 'xg', 'a', 'xa', 'sh', 'kp'}  # 90 dk başına çevrilebilenler
YAZI = {'n', 't', 'pos', 'rol'}
VARSAYILAN_SIRA = ('g', True)  # açılıştaki sıralama: gol, çoktan aza
GRUP_ADI = {'D': 'Tüm defans', 'M': 'Tüm orta saha', 'W': 'Tüm kanatlar'}


MEVKI_ADI = {'F': 'forvet', 'W': 'kanat', 'M': 'orta saha', 'D': 'defans'}


def _agirlik(x):
    return f'{"+" if x > 0 else "−"}{fmt(abs(x), 1).rstrip("0").rstrip(",")}'


def rol_aciklamasi(src, R):
    """Rollerin nasıl oluştuğunu anlatan bölüm; sezon.ROL'deki tanımlardan üretilir (rol eklenince kendiliğinden güncellenir)."""
    tanim = ROL[src]
    yedek = dict(R.get('yedek') or [])  # o sezon tutulmayıp yerine başka istatistik kullanılanlar
    adlar = [yedek.get(ad, ad) for _, ad in tanim['feats']]
    adimlar = [
        f'Bu ligde en az <b>{R["esik"]} dakika</b> oynamış saha oyuncuları alınır (kaleciler hariç; daha az sürede '
        '90 dakika başına değerler çok oynaktır).',
        f'Her oyuncunun şu istatistikleri 90 dakika başına çevrilir: {e(", ".join(adlar))}.',
        'Her değer, ligin o sezonki ortalamasından kaç standart sapma uzakta olduğuna çevrilir; böylece farklı ölçekteki '
        'istatistikler (şut ile pas sayısı gibi) eşit ağırlıkta olur.',
        f'Oyuncular, profilleri birbirine en çok benzeyenler aynı grupta olacak şekilde {len(tanim["roller"])} gruba ayrılır '
        '(k-means; 10 farklı başlangıç denenir, en tutarlısı seçilir).',
        'Her grubun ortalama profili aşağıdaki şablonlarla karşılaştırılır ve en iyi eşleşen rolün adını alır. Yani rolü '
        'belirleyen oyuncunun bütün profilidir; şablon yalnızca grubun etiketidir.',
        'Bir rol yalnızca tablodaki mevkilere açıktır; mevkisine uymayan gruba düşen oyuncu, profiline en yakın uygun gruba taşınır.',
        '"En iyiler": rolün + istatistiklerinde (standart değer × ağırlık) toplamı en yüksek, eşiğin 1,5 katından fazla oynamış '
        'üç oyuncu. Şablonunda + olmayan rolde en çok oynayanlar gösterilir. Karttaki oklar grubun ligden en çok ayrıştığı istatistiklerdir.',
    ]
    satirlar = []
    for ad, aciklama, w, mevkiler in tanim['roller']:
        arti = ', '.join(f'{e(adlar[f])} ({_agirlik(x)})' for f, x in sorted(enumerate(w), key=lambda t: -t[1]) if x > 0) or '–'
        eksi = ', '.join(f'{e(adlar[f])} ({_agirlik(x)})' for f, x in sorted(enumerate(w), key=lambda t: t[1]) if x < 0) or '–'
        satirlar.append(f'<tr><td><b>{e(ad)}</b><div class="cap" style="white-space:normal">{e(aciklama)}</div></td>'
                        f'<td style="white-space:normal">{arti}</td><td style="white-space:normal">{eksi}</td>'
                        f'<td>{", ".join(MEVKI_ADI[m] for m in mevkiler)}</td></tr>')
    return ('<ol class="lead" style="padding-left:20px;margin:6px 0 10px">' + ''.join(f'<li>{a}</li>' for a in adimlar) + '</ol>'
            + (f'<p class="cap">Bu sezon kaynakta {e(", ".join(f"{a} tutulmadığı için yerine {kucuk(b)}" for a, b in yedek.items()))} '
               'kullanılıyor.</p>' if yedek else '')
            + '<div class="kaydir"><table class="tb"><thead><tr><th>Rol</th><th>Yüksek olması beklenen (+)</th>'
              '<th>Düşük olması beklenen (−)</th><th>Açık olduğu mevkiler</th></tr></thead><tbody>'
            + ''.join(satirlar) + '</tbody></table></div>'
            + '<p class="cap">Sayılar şablondaki ağırlıklardır: +2 o rolü en çok belirleyen istatistik, −1 o rolde düşük '
              'olması beklenen istatistik. Roller lige ve sezona görelidir.</p>')


def kur(G):
    d = {'takim': '', 'mevki': '', 'rol': '', 'yas': '', 'ara': '', 'p90': False, 'ozel': '',
         'sirala': VARSAYILAN_SIRA[0], 'azalan': VARSAYILAN_SIRA[1], 'sayfa': 1, 'adet': 25, 'toplam': 0, 'grafik': []}

    with ui.column().classes('panel') as rol_panel:
        ui.html('<h3>Oyuncu rolleri</h3>', sanitize=False)
        rol_lead = ui.label().classes('lead')
        with ui.expansion('Roller nasıl belirleniyor?', icon='help_outline').classes('w-full').props('dense'):
            rol_aciklama = ui.html('', sanitize=False).classes('w-full')
        rol_izgara = ui.element('div').classes('w-full').style(
            'display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px')

    with ui.column().classes('panel') as ozel_panel:
        ui.html('<h3>Özel roller</h3>', sanitize=False)
        ui.label('Kümeleme rolünün üstüne, kurallarla verilen uzmanlıklar; bir oyuncu birden çok özel rol alabilir. Ölçütler '
                 'oyuncunun ligindeki saha oyuncularına göre (90 dakika başına yüzdelik). Pas, çalım ve top kazanma gibi '
                 'istatistiklerin olmadığı sezonlarda o roller hesaplanmaz. Karta tıklayınca tablo o role göre süzülür; '
                 'oyuncunun özel rolleri kartında yazar.').classes('cap')
        ozel_izgara = ui.element('div').classes('w-full').style(
            'display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px')

    with ui.column().classes('panel'):
        lead = ui.label().classes('lead')
        with ui.row().classes('w-full items-end gap-3'):
            ara = ui.input('Oyuncu ara', placeholder='İsim yaz').props('outlined dense clearable').style('min-width:200px').classes('grow')
            takim = ui.select({'': 'Tüm takımlar'}, value='', label='Takım').props('outlined dense options-dense').style('min-width:180px')
            mevki = ui.select({'': 'Tüm mevkiler'}, value='', label='Mevki').props('outlined dense options-dense').style('min-width:170px')
            yas = ui.select({'': 'Tüm yaşlar', 'U18': 'U18 (18 altı)', 'U21': 'U21 (21 altı)', 'U23': 'U23 (23 altı)',
                             '23-29': '23–29', '30+': '30 ve üstü'}, value='', label='Yaş').props('outlined dense options-dense').style('min-width:140px')
            rol = ui.select({'': 'Tüm roller'}, value='', label='Rol').props('outlined dense options-dense').style('min-width:190px')
            p90 = ui.checkbox('90 dk başına')
            ui.space()
            temizle = ui.button('Süzgeçleri temizle', icon='filter_alt_off', on_click=lambda: suzgecleri_temizle()).props(
                'flat dense no-caps')
            varsayilan = ui.button('Varsayılan sıralama', icon='sort', on_click=lambda: varsayilana_don()).props(
                'flat dense no-caps').tooltip('Gole göre, çoktan aza')
            disa_aktar.dugme('Excel\'e aktar', lambda: aktar())
        # yazı sütunları alt satıra kayabilir: tablo yana kaydırmadan sığsın
        tablo = ui.table(columns=[{'name': k, 'label': ad, 'field': k, 'sortable': True, 'align': 'left' if k in YAZI else 'right',
                                   **({'classes': 'sar'} if k in YAZI else {})}
                                  for k, ad in SUTUNLAR],
                         rows=[], row_key='idx',
                         pagination={'sortBy': VARSAYILAN_SIRA[0], 'descending': VARSAYILAN_SIRA[1], 'page': 1, 'rowsPerPage': 25, 'rowsNumber': 0}
                         ).props('flat dense :rows-per-page-options="[25,50,100]" rows-per-page-label="Sayfa başına"').classes(
            'w-full oyuncu-tablo')
        sayac = ui.label().classes('cap')

    with ui.column().classes('panel'):
        ui.html('<h3>Bitiricilik: atılan gol ve beklenen gol</h3>', sanitize=False)
        ui.label('Kesikli çizginin üstündekiler pozisyonlarının değerinden fazla gol attı. En az 10 şut çeken oyuncular, '
                 'yukarıdaki süzgeçlere göre. Noktaya tıklayınca oyuncu kartı açılır.').classes('lead')
        grafik = ui.echart({
            'animation': False, 'tooltip': {'trigger': 'item'},
            'grid': {'left': 50, 'right': 20, 'top': 16, 'bottom': 50},
            'xAxis': {'type': 'value', 'name': 'Beklenen gol (xG)', 'nameLocation': 'middle', 'nameGap': 28, 'min': 0},
            'yAxis': {'type': 'value', 'name': 'Atılan gol', 'nameLocation': 'middle', 'nameGap': 32, 'min': 0},
            'series': [{'type': 'scatter', 'symbolSize': 8, 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                       {'type': 'line', 'data': [], 'showSymbol': False, 'silent': True,
                        'lineStyle': {'type': 'dashed', 'color': '#8a9088', 'width': 1.5}}],
        }, on_point_click=lambda ev: _nokta(ev)).classes('w-full').style('height:420px')

    def _nokta(ev):
        if ev.series_index == 0 and 0 <= ev.data_index < len(d['grafik']):
            G.oyuncu_ac(d['grafik'][ev.data_index])

    def deger(p, k):
        if k == 'pos':
            return mevki_adi(p)
        v = p.get(k)
        if v is None:
            return None
        return v / p['min'] * 90 if d['p90'] and k in ORAN else v

    def goster(p, k):
        if k == 'n':
            return p['n']
        if k == 't':  # güncel kulüp: sezon içinde ayrıldıysa yenisi (önceki kulübü yanında)
            ayr = p.get('ayrildi')
            if not ayr:
                return p['t']
            return f'{ayr[0]} (← {p["t"]})' if ayr[0] else f'{p["t"]} (ayrıldı)'
        if k == 'pos':
            ad = mevki_adi(p)
            return ad + '*' if p.get('pos_tahmin') else ad
        if k == 'rol':  # özel roller (★) oyuncu kartında
            return p.get('rol') or f'– ({G.S.rol_nedeni(p)})'
        v = deger(p, k)
        if v is None:
            return '–'
        if d['p90'] and k in ORAN:
            return fmt(v, 2)
        if k in ('xg', 'xa'):
            return fmt(v, 1)
        if k == 'min':
            return sayi(v)
        return v

    def suzulmus():
        S = G.S
        q = sadelestir(d['ara'].strip()) if d['ara'] else ''
        yg = YAS_GRUPLARI.get(d['yas'])
        m = d['mevki']

        def mevki_uyar(p):
            if not m:
                return True
            if m in DETAY:
                return p.get('detay') == m and DETAY[m][0] == p['pos']
            return p['pos'] == m
        return [p for p in S.PLY
                if (not d['takim'] or d['takim'] in p['t'].split(' / ')) and mevki_uyar(p)
                and (not d['rol'] or p.get('rol') == d['rol'])
                and (not d['ozel'] or d['ozel'] in (p.get('ozel') or []))
                and (not yg or (p.get('yas') is not None and yg[0] <= p['yas'] <= yg[1]))
                and (not q or q in sadelestir(p['n']))]

    def ciz():
        S = G.S
        hepsi = suzulmus()
        yari = round(S.min_esik / 2)
        satirlar = [p for p in hepsi if not d['p90'] or p['min'] >= yari]
        k = d['sirala']
        # boş değerler (rolü ya da yaşı olmayanlar) yön ne olursa olsun en sonda
        dolu = [p for p in satirlar if deger(p, k) not in (None, '')]
        bos = [p for p in satirlar if deger(p, k) in (None, '')]
        if k in YAZI:
            dolu.sort(key=lambda p: tr_anahtar(deger(p, k)), reverse=d['azalan'])
        else:
            dolu.sort(key=lambda p: (deger(p, k), p['xg']), reverse=d['azalan'])
        satirlar = dolu + bos
        d['son'] = satirlar  # dışa aktarma: süzülmüş ve sıralanmış bütün satırlar (yalnızca görünen sayfa değil)
        sayfa_sayisi = max(1, -(-len(satirlar) // d['adet']))
        d['sayfa'] = min(max(1, d['sayfa']), sayfa_sayisi)
        bas = (d['sayfa'] - 1) * d['adet']
        gorunen = satirlar[bas:bas + d['adet']]
        tablo.rows = [{'idx': p['idx'], **{k2: goster(p, k2) for k2, _ in SUTUNLAR}} for p in gorunen]
        d['toplam'] = len(satirlar)
        tablo.pagination = sayfalama()
        tablo.update()
        sayac.text = (f'{len(satirlar)} oyuncu' + (f' (en az {yari} dakika oynayanlar)' if d['p90'] else '')
                      + '. Yıldızlı mevki: kaynak tek bir mevki vermediği için istatistiklerden seçildi.'
                      + (f' Rol, en az {S.roller["esik"]} dakika oynamış saha oyuncularına verilir (daha az sürede 90 dakika '
                         'başına değerler güvenilir değildir); kaleciler için rol tanımlı değildir.' if S.roller else ''))
        varsayilan.set_enabled((d['sirala'], d['azalan']) != VARSAYILAN_SIRA)
        temizle.set_visibility(any(d[k2] for k2 in ('ara', 'takim', 'mevki', 'yas', 'rol', 'p90', 'ozel')))
        # bitiricilik grafiği
        noktalar = [p for p in hepsi if (p['sh'] or 0) >= 10 or (p['sh'] is None and p['xg'] >= 1.5)]
        d['grafik'] = [p['idx'] for p in noktalar]
        ust = max([5] + [max(p['xg'], p['g']) for p in noktalar])
        grafik.options['series'][0]['data'] = [{'name': f'{p["n"]} ({p["t"]})', 'value': [round(p['xg'], 2), p['g']]} for p in noktalar]
        grafik.options['series'][1]['data'] = [[0, 0], [int(ust) + 1, int(ust) + 1]]
        grafik.update()

    def aktar():
        """Tablonun süzülmüş ve sıralanmış hâli (bütün sayfalar) ve özel roller."""
        S = G.S
        basliklar = [ad + (' (90 dk)' if d['p90'] and k in ORAN else '') for k, ad in SUTUNLAR] + ['Özel roller']
        satirlar = [[goster(p, k) if k in YAZI else deger(p, k) for k, _ in SUTUNLAR] + [', '.join(p.get('ozel') or [])]
                    for p in d.get('son') or []]
        return f'Oyuncular {S.lig} {S.yil}', basliklar, satirlar

    def istek(ev):
        """Tablodan gelen istek: ya sayfa değişti ya da bir sütun başlığına tıklandı. Sıralama yönünü tablonun kendi
        döngüsüne (artan → azalan → sırasız) bırakmadan burada çeviririz: aynı başlığa her tıklama yönü değiştirir."""
        pg = ev.args.get('pagination', {})
        if pg.get('sortBy') == d['sirala'] and bool(pg.get('descending')) == d['azalan']:  # sıralama aynı: sayfa değişti
            d['sayfa'], d['adet'] = pg.get('page', 1), pg.get('rowsPerPage') or 25
        else:  # bir başlığa tıklandı (tablo sayfayı da 1'e almış olabilir)
            yeni = pg.get('sortBy') or d['sirala']
            if yeni == d['sirala']:
                d['azalan'] = not d['azalan']
            else:  # yeni sütun: sayılar büyükten küçüğe, yazılar A'dan Z'ye
                d['sirala'], d['azalan'] = yeni, yeni not in YAZI
            d['sayfa'] = 1
        ciz()

    def sayfalama():
        return {'sortBy': d['sirala'], 'descending': d['azalan'], 'page': d['sayfa'], 'rowsPerPage': d['adet'],
                'rowsNumber': d['toplam']}

    def tablo_bildirdi(ev):
        """Tarayıcıdaki tablo açılırken kendi boş sayfalama durumunu ('toplam 0') bildirir ve NiceGUI bunu sunucudaki
        değerin üstüne yazar. Sıralama ve sayfalama Python'da tutulduğu için doğru değer geri yüklenir."""
        if ev.value != sayfalama():
            tablo.pagination = sayfalama()
            tablo.update()

    def varsayilana_don():
        d['sirala'], d['azalan'] = VARSAYILAN_SIRA
        d['sayfa'] = 1
        ciz()

    def suzgecleri_temizle():
        d['ara'] = ''
        ara.set_value('')
        if d['ozel']:
            d['ozel'] = ''
            ozel_ciz()
            ciz()
        for s in (takim, mevki, yas, rol):
            s.set_value('')  # her biri kendi değişiklik olayıyla tabloyu yeniler
        p90.set_value(False)

    tablo.on('request', istek)
    tablo.on_pagination_change(tablo_bildirdi)
    tablo.on('rowClick', lambda ev: G.oyuncu_ac(ev.args[1]['idx']))

    def suzgec(alan):
        def f(ev):
            d[alan] = ev.value if ev.value is not None else ''
            d['sayfa'] = 1
            ciz()
            if alan == 'rol':
                roller_ciz()
        return f

    ara.on_value_change(suzgec('ara'))
    takim.on_value_change(suzgec('takim'))
    mevki.on_value_change(suzgec('mevki'))
    yas.on_value_change(suzgec('yas'))
    rol.on_value_change(suzgec('rol'))
    p90.on_value_change(suzgec('p90'))

    def rol_tikla(ad):
        rol.value = '' if d['rol'] == ad else ad  # aynı karta tekrar tıklamak süzgeci kaldırır

    def ozel_tikla(ad):
        d['ozel'] = '' if d['ozel'] == ad else ad  # aynı karta tekrar tıklamak süzgeci kaldırır
        d['sayfa'] = 1
        ozel_ciz()
        ciz()

    def ozel_ciz():
        """Özel rol kartları (sezon.ozel_roller): ad, açıklama, oyuncu sayısı ve en çok oynayan üçü."""
        ozel_liste = getattr(G.S, 'ozel', None) or []
        ozel_panel.set_visibility(bool(ozel_liste))
        ozel_izgara.clear()
        with ozel_izgara:
            for r in ozel_liste:
                kart = ui.element('div').classes('rol' + (' sec' if d['ozel'] == r['ad'] else ''))
                kart.on('click', lambda _, ad=r['ad']: ozel_tikla(ad))
                with kart:
                    ui.html(f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
                            f'<span class="ad">★ {e(r["ad"])}</span><span class="cap">{len(r["oyuncular"])} oyuncu</span></div>'
                            f'<div class="cap" style="margin:4px 0">{e(r["aciklama"])}</div>', sanitize=False)
                    with ui.row().classes('items-baseline gap-1 text-sm').style('margin-top:4px'):
                        ui.label('En çok oynayanlar:').classes('cap')
                        for p in r['oyuncular'][:3]:
                            ui.button(p['n']).props('flat dense no-caps size=sm').classes('link').on(
                                'click.stop', lambda _, i=p['idx']: G.oyuncu_ac(i))

    def roller_ciz():
        S = G.S
        R = S.roller
        rol_panel.set_visibility(bool(R))
        if not R:
            return
        rol_lead.text = (f'Bu ligde en az {R["esik"]} dakika oynayan {R["n"]} saha oyuncusu, 90 dakika başına istatistik '
                         f'profillerine göre {len(R["roller"])} kümeye ayrıldı (k-means). Rol adları kümelerin profiline göre '
                         'verilir ve her rol yalnızca uygun mevkilere açıktır (ör. Stoper yalnızca defans oyuncularına). '
                         '"En iyiler", rolü tanımlayan istatistiklerde en yüksek değerlere sahip oyunculardır. '
                         'Karta tıklayınca tablo o role göre süzülür.'
                         + (f' Bu sezon için kaynakta {", ".join(f"{a} yerine {kucuk(b)}" for a, b in R["yedek"])} kullanıldı '
                            f'({" ve ".join(a for a, _ in R["yedek"])} verisi yok).' if R.get('yedek') else ''))
        rol_aciklama.content = rol_aciklamasi(S.src, R)
        rol_izgara.clear()
        with rol_izgara:
            for r in R['roller']:
                kart = ui.element('div').classes('rol' + (' sec' if d['rol'] == r['ad'] else ''))
                kart.on('click', lambda _, ad=r['ad']: rol_tikla(ad))
                with kart:
                    ui.html(f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
                            f'<span class="ad">{e(r["ad"])}</span><span class="cap">{r["n"]} oyuncu</span></div>'
                            f'<div class="cap" style="margin:4px 0">{e(r["aciklama"])}</div>'
                            + ''.join(f'<span class="chip">{e(ad)} {"↑" if yuksek else "↓"}</span>' for ad, yuksek in r['one']),
                            sanitize=False)
                    with ui.row().classes('items-baseline gap-1 text-sm').style('margin-top:6px'):
                        ui.label('En çok oynayanlar:' if r['sure'] else 'En iyiler:').classes('cap')
                        for p in r['en_iyi']:
                            # click.stop: ada tıklamak kartın süzgecini değiştirmesin
                            ui.button(p['n']).props('flat dense no-caps size=sm').classes('link').on(
                                'click.stop', lambda _, i=p['idx']: G.oyuncu_ac(i))

    def yenile():
        S = G.S
        lead.text = (f'{KAYNAK[S.src][0]} kaynaklı {len(S.PLY)} oyuncunun sezon istatistikleri. xG, çekilen şutların kalitesine göre '
                     'beklenen gol sayısıdır; xA aynı ölçünün asist karşılığıdır. Sıralamak için sütun başlığına, oyuncu kartını '
                     'açmak için satıra tıkla.')
        d.update(takim='', mevki='', rol='', yas='', ozel='', sayfa=1)
        takim.options = {'': 'Tüm takımlar', **{t: t for t in sorted(S.T, key=tr_anahtar)}}
        poz = {p['pos'] for p in S.PLY}
        det = {p.get('detay') for p in S.PLY if p.get('detay') and DETAY.get(p['detay'], ('',))[0] == p['pos']}
        sec = {'': 'Tüm mevkiler'}
        for k in ('G', 'D', 'M', 'W', 'F', 'S', 'U'):
            if k not in poz:
                continue
            alt = [x for x in DETAY if DETAY[x][0] == k and x in det]
            if len(alt) < 2:
                sec[k] = POS[k]
            else:
                sec[k] = GRUP_ADI.get(k, POS[k])
                for x in alt:
                    sec[x] = ' ' + DETAY[x][1]
        mevki.options = sec
        rol.options = {'': 'Tüm roller', **({r['ad']: r['ad'] for r in S.roller['roller']} if S.roller else {})}
        for s in (takim, mevki, rol, yas):
            s.set_value('')
            s.update()
        rol.set_enabled(bool(S.roller))
        yas.set_enabled(any(p.get('yas') is not None for p in S.PLY))
        roller_ciz()
        ozel_ciz()
        ciz()

    return yenile
