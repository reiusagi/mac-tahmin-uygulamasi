"""Tahmin oyunu sekmesi: yaklaşan maçlara skor tahmini girilir, modelin o anki tahminiyle yarışılır. Puan: kesin skor 3,
doğru sonuç (ev / beraberlik / deplasman) 1. Maç başlayınca tahmin kilitlenir; bitince sonuç lig verisinden okunur ve
puanlanır. Tahminler app.storage.general['tahmin_oyunu']'nda (bütün ligler): {anahtar: {'lig', 'yil', 'tarih', 'ev',
'dep', 'baslama', 'sen': [ev, dep], 'model': [ev, dep], 'sonuc': [ev, dep] | None, 'mac_tarihi' (puanlanınca)}}."""
from datetime import date, datetime, timedelta, timezone
import logging

from nicegui import app, run, ui

from ..sezon import LIG_ADI, SON_SEZON
from . import disa_aktar
from .ortak import e, kisa_gun, takim_logo, yerel

logger = logging.getLogger(__name__)

ID, AD = 'oyun', 'Tahmin oyunu'
TEMBEL = True
KESIN, SONUC = 3, 1  # kesin skor ve doğru sonuç puanı
GOSTERILEN = 12  # yaklaşan maçlardan bu kadarı listelenir
ESLESME_GERI, ESLESME_ILERI = 2, 21  # oynanan maç, tahminin tarihinden en çok bu kadar gün önce / sonra olabilir (erteleme)


def puan(tahmin, sonuc):
    if not tahmin or not sonuc:
        return None
    if list(tahmin) == list(sonuc):
        return KESIN
    yon = lambda s: (s[0] > s[1]) - (s[0] < s[1])  # noqa: E731
    return SONUC if yon(tahmin) == yon(sonuc) else 0


def _gun(t):
    return date.fromisoformat(t[:10]).toordinal()


def sonuc_esle(bekleyen, oynanan, alinmis=()):
    """Sonucu bekleyen tahminleri oynanmış maçlarla eşler. Aynı çift sezonda 3-4 kez oynayabilir; bu yüzden yalnızca ad
    çiftine değil tarihe de bakılır: tahminin tarihinden en çok ESLESME_GERI gün önce, ESLESME_ILERI gün sonra (ertelemeler)
    oynanmış maç aday olur; en yakın tarihli seçilir ve bir maç en çok bir tahmine puan verir. Aday yoksa tahmin bekler.
    bekleyen: {anahtar: kayıt}; oynanan: [(tarih, ev, dep, ev golü, dep golü)]; alinmis: başka tahminlere zaten sonuç
    olmuş maçlar {(tarih, ev, dep)}. Döner: {anahtar: (maç tarihi, ev golü, dep golü)}."""
    adaylar = []
    for k, r in bekleyen.items():
        g0 = _gun(r['tarih'])
        for i, (d, ev, dep, hg, ag) in enumerate(oynanan):
            if (ev, dep) != (r['ev'], r['dep']) or (d, ev, dep) in alinmis:
                continue
            fark = _gun(d) - g0
            if -ESLESME_GERI <= fark <= ESLESME_ILERI:
                adaylar.append((abs(fark), r['tarih'], k, i))
    out, kullanilan = {}, set()
    for _, _, k, i in sorted(adaylar):  # en yakın tarih önce; eşitlikte anahtar sırası (belirli sonuç)
        if k not in out and i not in kullanilan:
            out[k] = (oynanan[i][0], oynanan[i][3], oynanan[i][4])
            kullanilan.add(i)
    return out


def yetim_kayitlar(kayitlar, yeni, kalan, oynanan):
    """Ertelenen maçın eski tarihli kaydı: anahtar tarihi içerdiğinden maç ertelenince yeni bir tahmin yeni anahtarla
    açılır, eskisi sonsuza dek "bekleyen" kalırdı. Yeni kaydın (lig, sezon, ev, dep) çiftiyle aynı, puanlanmamış, tarihi
    ESLESME_ILERI günden fazla uzak olmayan ve fikstürde (kalan: {(tarih, ev, dep)}) ya da oynananlarda karşılığı
    olmayan kayıtların anahtarları. Karşılığı olan kayıt gerçek bir maçın tahminidir, silinmez."""
    out = []
    for k, r in kayitlar.items():
        if r.get('sonuc') is not None or r['tarih'] == yeni['tarih']:
            continue
        if (r['lig'], r.get('yil', yeni.get('yil')), r['ev'], r['dep']) != (yeni['lig'], yeni.get('yil'), yeni['ev'], yeni['dep']):
            continue
        if abs(_gun(yeni['tarih']) - _gun(r['tarih'])) > ESLESME_ILERI or (r['tarih'], r['ev'], r['dep']) in kalan:
            continue
        if not sonuc_esle({k: r}, oynanan):
            out.append(k)
    return out


def model_skoru(t):
    """Modelin skor tahmini: en olası sonucun (ev / beraberlik / deplasman) içindeki en olası skor (yalnızca en olası
    skoru almak modeli hep 1-1 dedirtir)."""
    p = t['p']
    yon = p.index(max(p))
    hucre = [c for c in t['hucreler'] if (0 if c[0] > c[1] else 1 if c[0] == c[1] else 2) == yon]
    i, j, _ = max(hucre, key=lambda c: c[2])
    return [i, j]


def kur(G):
    with ui.column().classes('panel'):
        ui.html('<h3>Tahmin oyunu</h3>', sanitize=False)
        ui.label(f'Yaklaşan maçlara skor tahminini gir, modelle yarış. Kesin skor {KESIN} puan, doğru sonuç (ev, beraberlik, '
                 f'deplasman) {SONUC} puan. Tahmini kaydettiğin anda modelin tahmini de kaydedilir; maç başlayınca '
                 'tahmin kilitlenir, bitince puanlanır. Tahminler bütün liglerde birikir.').classes('lead')
        skor = ui.html('', sanitize=False).classes('w-full')
        hafta = ui.html('', sanitize=False).classes('w-full kaydir')
    with ui.column().classes('panel'):
        baslik = ui.html('<h3>Yaklaşan maçlar</h3>', sanitize=False)
        liste = ui.column().classes('w-full gap-1')
    with ui.column().classes('panel') as ist_panel:
        ui.html('<h3>İstatistiklerim</h3>', sanitize=False)
        ist = ui.html('', sanitize=False).classes('w-full kaydir')
        ist_grafik = ui.echart({
            'animation': False, 'tooltip': {'trigger': 'axis'}, 'legend': {'bottom': 0},
            'grid': {'left': 40, 'right': 16, 'top': 14, 'bottom': 50},
            'xAxis': {'type': 'category', 'data': []}, 'yAxis': {'type': 'value', 'name': 'Puan'},
            'series': [{'name': 'Senin toplamın', 'type': 'line', 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                       {'name': 'Modelin toplamı', 'type': 'line', 'itemStyle': {'color': '#35598a'}, 'data': []},
                       {'name': 'Fark (sen − model)', 'type': 'bar', 'itemStyle': {'color': 'rgba(201,150,15,.6)'}, 'data': []}],
        }).classes('w-full').style('height:260px')
        ui.label('Grafik: haftalar boyunca toplam puanlar ve aradaki fark (biten tahminler).').classes('cap')
    ist_panel.set_visibility(False)
    with ui.column().classes('panel'):
        with ui.row().classes('w-full items-center'):
            ui.html('<h3>Tahminlerim</h3>', sanitize=False)
            ui.space()
            disa_aktar.dugme('Excel\'e aktar', lambda: aktar(), 'Bütün tahminlerin (senin, modelin, sonuç ve puanlar) '
                             'İndirilenler\\MacTahmin klasörüne CSV olarak')
        gecmis = ui.html('', sanitize=False).classes('w-full kaydir')

    def aktar():
        basliklar = ['Tarih', 'Lig', 'Ev sahibi', 'Deplasman', 'Senin tahminin', 'Modelin tahmini', 'Sonuç', 'Senin puanın',
                     'Modelin puanı']
        skor = lambda s: f'{s[0]} – {s[1]}' if s else None  # noqa: E731  (boşluklu: Excel "1-2"yi tarih sanmasın)
        satirlar = [[f'{r["tarih"][8:10]}.{r["tarih"][5:7]}.{r["tarih"][:4]}', LIG_ADI.get(r['lig'], r['lig']), r['ev'], r['dep'],
                     skor(r['sen']), skor(r['model']), skor(r.get('sonuc')), puan(r['sen'], r.get('sonuc')),
                     puan(r['model'], r.get('sonuc'))]
                    for r in sorted(kayitlar().values(), key=lambda r: r.get('baslama') or r['tarih'])]
        return 'Tahmin oyunu', basliklar, satirlar

    def kayitlar():
        return dict(app.storage.general.get('tahmin_oyunu', {}))

    def kaydet(k, kayit, sil=()):
        tum = kayitlar()
        for y in sil:
            tum.pop(y, None)
        tum[k] = kayit
        app.storage.general['tahmin_oyunu'] = tum

    def anahtar(S, m):
        return f'{S.lig}|{m.d}|{S.T[m.h]}|{S.T[m.a]}'

    def tahmin_kaydet(S, m, baslama, ev_k, dep_k):
        if baslama and datetime.now(timezone.utc).isoformat() >= baslama:
            ui.notify('Maç başladı; tahmin kilitli.', type='warning')
            return
        try:
            sen = [int(ev_k.value), int(dep_k.value)]
        except (TypeError, ValueError):
            ui.notify('İki skoru da gir.')
            return
        k = anahtar(S, m)
        tum = kayitlar()
        yeni = {'lig': S.lig, 'yil': S.yil, 'tarih': m.d, 'ev': S.T[m.h], 'dep': S.T[m.a]}
        # maç ertelendiyse eski tarihli kaydı kalmasın (yoksa hep bekler); modelin ilk tahmini ondan alınır
        yetim = yetim_kayitlar(tum, yeni, {(u.d, S.T[u.h], S.T[u.a]) for u in S.U},
                               [(x.d, S.T[x.h], S.T[x.a], x.hg, x.ag) for x in S.M])
        eski = tum.get(k) or next((tum[y] for y in yetim if tum[y].get('model')), None)
        model = (eski or {}).get('model') or model_skoru(S.tahmin(m.h, m.a))  # modelin ilk tahmini sabit kalır
        kaydet(k, {**yeni, 'baslama': baslama, 'sen': sen, 'model': model, 'sonuc': None}, yetim)
        ui.notify(f'Kaydedildi: {S.T[m.h]} {sen[0]} – {sen[1]} {S.T[m.a]} (model: {model[0]} – {model[1]})', type='positive')
        liste_ciz()
        ozet_ciz()

    def tahmin_iptal(k, baslama):
        """Kaydedilmiş tahmini siler (maç başlamadıysa); modelin o maçtaki tahmini de silinir."""
        if baslama and datetime.now(timezone.utc).isoformat() >= baslama:
            ui.notify('Maç başladı; tahmin kilitli.', type='warning')
            return
        tum = kayitlar()
        if tum.pop(k, None) is None:
            return
        app.storage.general['tahmin_oyunu'] = tum
        ui.notify('Tahmin iptal edildi.')
        liste_ciz()
        ozet_ciz()

    def liste_ciz():
        S = G.S
        liste.clear()
        if S.yil != SON_SEZON or not S.U:
            baslik.content = '<h3>Yaklaşan maçlar</h3>'
            with liste:
                ui.label('Tahmin için süren sezonu ve maçı kalmış bir lig seç.').classes('cap')
            return
        baslik.content = f'<h3>Yaklaşan maçlar · {e(LIG_ADI.get(S.lig, S.lig))}</h3>'
        tum = kayitlar()
        simdi = datetime.now(timezone.utc).isoformat()
        maclar = [(m, r[3] if len(r) > 3 else None) for m, r in zip(S.U, S.raw['u'])]
        maclar = sorted((x for x in maclar if not x[1] or x[1] > simdi), key=lambda x: (x[1] or x[0].d))[:GOSTERILEN]
        with liste:
            for m, baslama in maclar:
                k = anahtar(S, m)
                kayit = tum.get(k)
                z = yerel(baslama) if baslama else None
                with ui.row().classes('w-full items-center gap-2 oyun-satir'):
                    ui.label(f'{kisa_gun(z.date())} {z:%H:%M}' if z else kisa_gun(m.d)).classes('cap').style('width:96px')
                    ui.html(f'<span class="oyun-takim sag">{e(S.T[m.h])}{takim_logo(G.depo.takim_kimligi(S.lig, S.T[m.h]))}</span>',
                            sanitize=False).style('flex:1;text-align:right')
                    ev_k = ui.number(value=(kayit or {}).get('sen', [None])[0], min=0, max=15, step=1, format='%d').props(
                        'outlined dense').style('width:62px')
                    ui.label('–')
                    dep_k = ui.number(value=(kayit or {}).get('sen', [None, None])[1], min=0, max=15, step=1, format='%d').props(
                        'outlined dense').style('width:62px')
                    ui.html(f'<span class="oyun-takim">{takim_logo(G.depo.takim_kimligi(S.lig, S.T[m.a]))}{e(S.T[m.a])}</span>',
                            sanitize=False).style('flex:1')
                    ui.button('Kaydet' if not kayit else 'Güncelle', icon='check',
                              on_click=lambda _, m=m, b=baslama, ek=ev_k, dk=dep_k: tahmin_kaydet(S, m, b, ek, dk)).props(
                        'unelevated dense no-caps color=primary')
                    ui.button('İptal', icon='close', on_click=lambda _, k=k, b=baslama: tahmin_iptal(k, b)).props(
                        'flat dense no-caps color=negative').set_visibility(bool(kayit))
                    ui.label(f'model: {kayit["model"][0]} – {kayit["model"][1]}' if kayit else '').classes('cap').style('width:80px')

    async def sonuclari_isle():
        """Başlama zamanı geçmiş, sonucu bilinmeyen tahminleri lig verisinden puanlar (sonuc_esle: tarihe de bakar)."""
        tum = kayitlar()
        simdi = datetime.now(timezone.utc).isoformat()
        bekleyen = {}
        for k, r in tum.items():
            if r.get('sonuc') is None and (r.get('baslama') or r['tarih']) <= simdi:
                bekleyen.setdefault((r['lig'], r.get('yil') or SON_SEZON), {})[k] = r
        degisti = False
        for (lig, yil), bek in bekleyen.items():
            try:
                S = await run.io_bound(G.depo.sezon, lig, yil)
            except Exception:
                logger.debug('sezon kurulamadı: %s %s', lig, yil, exc_info=True)
                continue
            oynanan = [(m.d, S.T[m.h], S.T[m.a], m.hg, m.ag) for m in S.M]
            alinmis = {(r.get('mac_tarihi') or r['tarih'], r['ev'], r['dep']) for r in tum.values()
                       if r.get('sonuc') is not None and r['lig'] == lig}
            for k, (tarih, hg, ag) in sonuc_esle(bek, oynanan, alinmis).items():
                tum[k]['sonuc'] = [hg, ag]
                tum[k]['mac_tarihi'] = tarih
                degisti = True
        if degisti:
            app.storage.general['tahmin_oyunu'] = tum

    def istatistik_ciz(biten, haftalar):
        """Lig lig puanlar ve doğru sonuç oranı (sen ve model), en çok verdiğin skorlar, haftalık toplam puan grafiği."""
        ist_panel.set_visibility(bool(biten))
        if not biten:
            return
        ligler = {}
        for r in biten:
            x = ligler.setdefault(r['lig'], [0, 0, 0, 0, 0])  # maç, senin puan, model puanı, senin doğru sonuç, modelin
            ps, pm = puan(r['sen'], r['sonuc']), puan(r['model'], r['sonuc'])
            x[0] += 1
            x[1] += ps
            x[2] += pm
            x[3] += ps > 0
            x[4] += pm > 0
        oran = lambda a, n: f'%{round(a / n * 100)}'  # noqa: E731
        lig_tablo = ''.join(
            f'<tr><td>{e(LIG_ADI.get(l, l))}</td><td>{x[0]}</td><td class="hi">{x[1]}</td><td class="hi">{x[2]}</td>'
            f'<td>{oran(x[3], x[0])}</td><td>{oran(x[4], x[0])}</td></tr>'
            for l, x in sorted(ligler.items(), key=lambda kv: -kv[1][0]))
        skorlar = {}
        for r in biten:
            s = skorlar.setdefault(tuple(r['sen']), [0, 0])
            s[0] += 1
            s[1] += list(r['sen']) == list(r['sonuc'])
        sik = sorted(skorlar.items(), key=lambda kv: -kv[1][0])[:5]
        ist.content = (
            '<table class="tb"><thead><tr><th>Lig</th><th>Maç</th><th>Senin puan</th><th>Model puanı</th>'
            '<th>Senin doğru sonuç</th><th>Modelin doğru sonuç</th></tr></thead><tbody>' + lig_tablo + '</tbody></table>'
            '<div class="lead" style="margin-top:8px">En çok verdiğin skorlar: '
            + ', '.join(f'{s[0]} – {s[1]} ({n} kez, {t} tuttu)' for s, (n, t) in sik) + '.</div>')
        toplam_s = toplam_m = 0
        x, ys, ym, fark = [], [], [], []
        for g, h in sorted(haftalar.items()):
            toplam_s += h[0]
            toplam_m += h[1]
            x.append(kisa_gun(g))
            ys.append(toplam_s)
            ym.append(toplam_m)
            fark.append(toplam_s - toplam_m)
        ist_grafik.options['xAxis']['data'] = x
        for s, veri in zip(ist_grafik.options['series'], (ys, ym, fark)):
            s['data'] = veri
        ist_grafik.update()

    def ozet_ciz():
        tum = kayitlar()
        biten = [r for r in tum.values() if r.get('sonuc')]
        sen = sum(puan(r['sen'], r['sonuc']) for r in biten)
        model = sum(puan(r['model'], r['sonuc']) for r in biten)
        bekleyen = len(tum) - len(biten)
        durum = ('Henüz biten tahmin yok.' if not biten else
                 'Önde sensin!' if sen > model else 'Model önde.' if model > sen else 'Berabersiniz.')
        skor.content = ('<div class="tiles" style="grid-template-columns:repeat(4,1fr)">'
                        f'<div class="tile"><span class="num">{sen}</span><small>Senin puanın</small></div>'
                        f'<div class="tile"><span class="num">{model}</span><small>Modelin puanı</small></div>'
                        f'<div class="tile"><span class="num">{len(biten)}</span><small>Biten tahmin</small></div>'
                        f'<div class="tile"><span class="num">{bekleyen}</span><small>Bekleyen</small></div></div>'
                        f'<div class="lead" style="margin-top:6px">{durum} Kesin skor: sen '
                        f'{sum(1 for r in biten if puan(r["sen"], r["sonuc"]) == KESIN)}, model '
                        f'{sum(1 for r in biten if puan(r["model"], r["sonuc"]) == KESIN)}.</div>')
        # haftalık yarış: biten tahminler maç haftasına (Pazartesi başlangıçlı) göre
        haftalar = {}
        for r in biten:
            g = date.fromisoformat(r['tarih'])
            h = haftalar.setdefault(g - timedelta(days=g.weekday()), [0, 0, 0])
            h[0] += puan(r['sen'], r['sonuc'])
            h[1] += puan(r['model'], r['sonuc'])
            h[2] += 1
        kazanilan = [sum(1 for h in haftalar.values() if h[0] > h[1]), sum(1 for h in haftalar.values() if h[1] > h[0])]
        hafta.content = ('' if not haftalar else
                         f'<div class="lead">Haftalık yarış: sen {kazanilan[0]} hafta, model {kazanilan[1]} hafta kazandı.</div>'
                         '<table class="tb"><thead><tr><th>Hafta</th><th>Maç</th><th>Senin</th><th>Model</th><th></th></tr></thead><tbody>'
                         + ''.join(f'<tr><td>{kisa_gun(g)} haftası</td><td>{h[2]}</td><td class="hi">{h[0]}</td><td class="hi">{h[1]}</td>'
                                   f'<td class="cap">{"sen" if h[0] > h[1] else "model" if h[1] > h[0] else "berabere"}</td></tr>'
                                   for g, h in sorted(haftalar.items(), reverse=True)) + '</tbody></table>')
        istatistik_ciz(biten, haftalar)
        satirlar = []
        for r in sorted(tum.values(), key=lambda r: r.get('baslama') or r['tarih'], reverse=True)[:80]:
            sonuc = r.get('sonuc')
            ps, pm = puan(r['sen'], sonuc), puan(r['model'], sonuc)
            renk = lambda x: '' if x is None else ('var(--pitch-2)' if x == KESIN else 'var(--lamp)' if x else 'var(--bad)')  # noqa: E731
            sonuc_yazi = f'{sonuc[0]} – {sonuc[1]}' if sonuc else '–'
            satirlar.append(
                f'<tr><td class="cap">{r["tarih"][8:10]}.{r["tarih"][5:7]}</td><td class="cap">{e(LIG_ADI.get(r["lig"], r["lig"]))}</td>'
                f'<td style="text-align:right">{e(r["ev"])}</td><td class="hi" style="text-align:center">{sonuc_yazi}</td>'
                f'<td>{e(r["dep"])}</td><td>{r["sen"][0]} – {r["sen"][1]}</td>'
                f'<td style="color:{renk(ps)};font-weight:700">{"" if ps is None else ps}</td>'
                f'<td>{r["model"][0]} – {r["model"][1]}</td><td style="color:{renk(pm)};font-weight:700">{"" if pm is None else pm}</td></tr>')
        gecmis.content = ('<table class="tb"><thead><tr><th>Tarih</th><th>Lig</th><th style="text-align:right">Ev</th>'
                          '<th>Sonuç</th><th>Deplasman</th><th>Senin</th><th>P</th><th>Model</th><th>P</th></tr></thead><tbody>'
                          + ''.join(satirlar) + '</tbody></table>') if satirlar else '<p class="cap">Henüz tahmin girmedin.</p>'

    async def yenile():
        liste_ciz()
        await sonuclari_isle()
        ozet_ciz()

    return yenile
