"""Puan durumu sekmesi; süren sezonda altında sezon simülasyonu."""
from nicegui import run, ui

from ..sezon import FIKSTUR_SONRAKI, SANS_ESIK, SON_SEZON, fikstur_zorlugu, hak_edilen_puan
from . import disa_aktar
from .ortak import FORM, e, fmt, form, takim_link, takim_logo, takim_tiklama, yuzde_uc

ID, AD = 'tablo', 'Puan durumu'
TEMBEL = True  # sezon simülasyonu ve xPts: yalnızca sekme açıkken (lig değişince gizliyken hesaplanmasın)


# ---------------------------------------------------------------- saf HTML / veri üreticiler (arayüz öğesine dokunmaz)
def _aktar_tablosu(S):
    """Puan durumu; süren sezonda simülasyon (hesaplandıysa) ve fikstür zorluğu sütunları da."""
    n = len(S.T)
    alt = 3 if n >= 16 else 2
    sim = {r['i']: r for r in S.sim} if S.sim else {}
    fz = {r['i']: r for r in fikstur_zorlugu(S)} if S.yil == SON_SEZON and S.U else {}
    basliklar = ['Sıra', 'Takım', 'O', 'G', 'B', 'M', 'AG', 'YG', 'AV', 'xG', 'xGA', 'P']
    if sim:
        basliklar += ['Beklenen puan', 'Şampiyonluk %', 'İlk 4 %', f'Son {alt} %']
    if fz:
        basliklar += [f'Sıradaki {FIKSTUR_SONRAKI} maçın zorluğu', 'Kalan maçların zorluğu', 'Kalan maçlardan beklenen puan']
    satirlar = []
    for k, r in enumerate(S.tablo):
        s = [k + 1, r['name'], r['O'], r['G'], r['B'], r['M'], r['AG'], r['YG'], r['AV'],
             round(r['xG'], 2) if S.xg_var else None, round(r['xGA'], 2) if S.xg_var else None, r['P']]
        if sim:
            dist = sim[r['i']]['dist']
            s += [round(sim[r['i']]['exp'], 1), round(dist[0] * 100, 1), round(sum(dist[:4]) * 100, 1),
                  round(sum(dist[n - alt:]) * 100, 1)]
        if fz:
            f = fz.get(r['i'])
            s += [round(f['zorluk5']), round(f['zorluk']), round(f['xp'], 1)] if f else [None, None, None]
        satirlar.append(s)
    return f'Puan durumu {S.lig} {S.yil}', basliklar, satirlar


def _sim_lead(S):
    return (f'Kalan {len(S.U)} maç, takım güçlerine göre 10.000 kez oynatıldı. Takım güçleri bu sezonun'
            + (f' ve önceki {S.n_onceki} sezonun sonuçlarından ve xG\'sinden (eski maçların ağırlığı zamanla azalır)'
               if S.n_onceki else ' sonuçlarından ve xG\'sinden')
            + ' hesaplanır' + (', kadro değerine göre hafifçe düzeltilir' if S.kadro_degeri else '')
            + '. Puan silme cezaları, hükmen maçlar ve ligin play-off ya da ikiye ayrılma kuralları '
              'hesaba katılmaz.')


def _degisim(yeni, eski):
    f = (yeni - eski) * 100
    if abs(f) < 0.5:
        return ''
    return f' <small style="color:{"var(--pitch-2)" if f > 0 else "var(--bad)"};font-weight:700">{"+" if f > 0 else "−"}{fmt(abs(f), 0)}</small>'


def _sim_html(depo, S, ozel):
    """Sezon sonu simülasyon tablosu. ozel: "ya şöyle olursa" simülasyonu (varsa) ve normal simülasyonla farkı gösterilir."""
    n = len(S.T)
    alt = 3 if n >= 16 else 2
    yer = {r['i']: k + 1 for k, r in enumerate(S.tablo)}
    yf = yuzde_uc
    satirlar = []
    temel = {r['i']: r for r in S.sim}
    for r in (ozel or S.sim):
        d = r['dist']
        t = temel[r['i']]['dist']
        en = d.index(max(d)) + 1
        dag = ''.join(f'<i title="{k + 1}. sıra: {fmt(p * 100, 1)}%" style="background:color-mix(in srgb,var(--pitch) '
                      f'{round(min(1, p * 2.5) * 100)}%,var(--line))"></i>' for k, p in enumerate(d))
        dg = (lambda a, b: _degisim(a, b)) if ozel else (lambda a, b: '')
        satirlar.append(f'<tr><td>{yer[r["i"]]}</td><td class="takim-hucre">{takim_logo(depo.takim_kimligi(S.lig, r["name"]))}'
                        f'{takim_link(r["name"], r["name"])}</td><td>{r["P"]}</td><td class="hi">{fmt(r["exp"], 1)}</td>'
                        f'<td>{yf(d[0])}{dg(d[0], t[0])}</td><td>{yf(sum(d[:4]))}{dg(sum(d[:4]), sum(t[:4]))}</td>'
                        f'<td>{yf(sum(d[n - alt:]))}{dg(sum(d[n - alt:]), sum(t[n - alt:]))}</td>'
                        f'<td><span class="dist" title="En olası sıra: {en}">{dag}</span></td></tr>')
    return ('<table class="tb"><thead><tr><th>#</th><th>Takım</th><th>P</th><th>Beklenen P</th><th>Şampiyon</th>'
            f'<th>İlk 4</th><th>Son {alt}</th><th>Sıra dağılımı</th></tr></thead><tbody>'
            + ''.join(satirlar) + '</tbody></table>')


def _sans_analizi(depo, S, hp):
    """Şanslı ve şanssız takımlar (gerçek puan − xPts en az SANS_ESIK) ve nedeni: hücumda xG'den fazla / az gol
    (bitiricilik ya da şans), savunmada verdiği xG'den az / çok gol yeme (kaleci ya da şans)."""
    def neden(r, sansli):
        hucum, savunma = r['AG'] - r['xG'], r['xGA'] - r['YG']  # artı: beklenenden iyi
        parca = []
        if (hucum >= 1.5) if sansli else (hucum <= -1.5):
            parca.append(f'xG\'sinden {fmt(abs(hucum), 1)} gol {"fazla attı" if sansli else "az attı"}')
        if (savunma >= 1.5) if sansli else (savunma <= -1.5):
            parca.append(f'verdiği xG\'den {fmt(abs(savunma), 1)} gol {"az yedi" if sansli else "fazla yedi"}')
        return ', '.join(parca) or ('dar farkla kazandığı maçlar' if sansli else 'dar farkla kaybettiği maçlar')

    def kutu(baslik, liste, sansli, renk):
        satirlar = ''.join(
            f'<div class="sans-satir"><span>{takim_logo(depo.takim_kimligi(S.lig, t))}{takim_link(t, t)}</span>'
            f'<b style="color:{renk}">{"+" if sansli else "−"}{fmt(abs(r["P"] - r["xP"]), 1)} puan</b>'
            f'<span class="cap">{e(neden(r, sansli))}</span></div>' for t, r in liste) or '<div class="cap">Yok.</div>'
        return f'<div class="sans-kutu"><div class="disp" style="font-weight:700">{baslik}</div>{satirlar}</div>'
    fark = sorted(hp.items(), key=lambda kv: kv[1]['P'] - kv[1]['xP'])
    sansli = [kv for kv in reversed(fark) if kv[1]['P'] - kv[1]['xP'] >= SANS_ESIK][:3]
    sanssiz = [kv for kv in fark if kv[1]['P'] - kv[1]['xP'] <= -SANS_ESIK][:3]
    return ('<div class="sans-izgara">' + kutu('Şanslı: düşüş riski', sansli, True, 'var(--bad)')
            + kutu('Şanssız: yükselmesi beklenir', sanssiz, False, 'var(--pitch-2)') + '</div>')


FIKSTUR_NOTU = ('Sıradaki {} maçı en zor olandan en kolaya. Zorluk yalnızca rakiplerin gücüdür (takımın '
                'kendi gücü karışmaz): rakibin Elo puanı, rakip ev sahibiyse ev avantajı eklenerek, ortalaması; çubuk '
                'ligdeki en kolay ve en zor fikstüre göre. Rakip kutuları: adının ilk harfleri, E ev / D deplasman; '
                'renk takımın o maçı kazanma olasılığı (yeşil %50 ve üstü, kırmızı %25 ve altı). Bütün kalan maçlar: '
                'aynı ölçü sezonun geri kalanı için (parantezde en zordan sırası; sezon başında farklar küçüktür). '
                'Beklenen puan: modelin kalan maçlardan beklediği toplam (burada takımın kendi gücü de var).')


def _fikstur_html(depo, S):
    """Kalan maçların zorluğu (sezon.fikstur_zorlugu): rakiplerin ortalama gücü ve sıradaki maçlar."""
    fz = fikstur_zorlugu(S)
    en_zor, en_kolay = fz[0]['zorluk5'], fz[-1]['zorluk5']
    aralik = (en_zor - en_kolay) or 1
    yer = {r['i']: k + 1 for k, r in enumerate(S.tablo)}
    tum_sira = {r['i']: k + 1 for k, r in enumerate(sorted(fz, key=lambda r: -r['zorluk']))}
    satirlar = []
    for k, r in enumerate(fz):
        t = S.T[r['i']]
        olcek = (r['zorluk5'] - en_kolay) / aralik * 100
        cipler = ''.join(
            f'<span class="fk-cip {"k" if pk >= .5 else "z" if pk <= .25 else "o"}" title="{e(S.T[rk])} '
            f'({"ev" if ev else "deplasman"}) · kazanma olasılığı {yuzde_uc(pk)}">{e(S.T[rk][:3].upper())} '
            f'<small>{"E" if ev else "D"}</small></span>' for rk, ev, _, pk in r['sonraki'])
        satirlar.append(
            f'<tr><td>{k + 1}</td><td class="takim-hucre">{takim_logo(depo.takim_kimligi(S.lig, t))}{takim_link(t, t)}</td>'
            f'<td class="cap">{yer.get(r["i"], "–")}.</td><td>{r["kalan"]}</td>'
            f'<td><div class="sc-bar" style="width:120px;display:inline-block;vertical-align:middle"><i style="width:'
            f'{max(4, round(olcek))}%;background:{"var(--bad)" if olcek >= 66 else "var(--lamp)" if olcek >= 33 else "var(--pitch-2)"}">'
            f'</i></div> <span class="cap">{round(r["zorluk5"])}</span></td><td>{cipler}</td>'
            f'<td>{round(r["zorluk"])} <span class="cap">({tum_sira[r["i"]]}.)</span></td>'
            f'<td class="hi">{fmt(r["xp"], 1)}</td></tr>')
    return ('<table class="tb"><thead><tr><th>#</th><th>Takım</th><th>Sıra</th><th>Kalan</th>'
            f'<th>Sıradaki {FIKSTUR_SONRAKI} maçın zorluğu</th><th>Sıradaki maçlar</th>'
            '<th>Bütün kalan maçlar</th><th>Beklenen puan</th></tr></thead>'
            '<tbody>' + ''.join(satirlar) + '</tbody></table>')


def _xp_html(depo, S, hp):
    """Hak edilen puan tablosu (sezon.hak_edilen_puan): xPts'e göre sıralı, gerçek puanla farkı."""
    gercek_sira = {r['name']: k + 1 for k, r in enumerate(S.tablo)}
    sirali = sorted(hp.items(), key=lambda kv: -kv[1]['xP'])
    satirlar = []
    for k, (t, r) in enumerate(sirali):
        fark = r['P'] - r['xP']
        yorum = ('şanslı' if fark >= SANS_ESIK else 'şanssız' if fark <= -SANS_ESIK else '')
        satirlar.append(
            f'<tr><td>{k + 1}</td><td class="takim-hucre">{takim_logo(depo.takim_kimligi(S.lig, t))}{takim_link(t, t)}</td>'
            f'<td>{r["mac"]}</td><td>{r["P"]}</td><td class="pts">{fmt(r["xP"], 1)}</td>'
            f'<td style="color:{"var(--pitch-2)" if fark > 0 else "var(--bad)"};font-weight:700">{"+" if fark > 0 else ""}'
            f'{fmt(fark, 1)}</td><td class="cap">{yorum}</td><td>{fmt(r["xG"], 1)}</td><td>{fmt(r["xGA"], 1)}</td>'
            f'<td class="cap">{gercek_sira.get(t, "–")}</td></tr>')
    return ('<table class="tb"><thead><tr><th>#</th><th>Takım</th><th>Maç</th><th>Puan</th><th>xPts</th>'
            '<th>Fark</th><th></th><th>xG</th><th>xGA</th><th>Gerçek sıra</th></tr></thead><tbody>'
            + ''.join(satirlar) + '</tbody></table>')


def _xp_notu(maclar, kaynak):
    sut_mac = sum(1 for m in maclar if len(m) > 7 and m[7] is not None and m[8] is not None)
    return ('Her maç, iki takımın o maçta ürettiği xG ile yeniden oynatıldığında takımın ortalama alacağı puan '
            '(3 × kazanma + 1 × beraberlik olasılığı). Şutları bilinen maçlarda hesap şut şut: her şut kendi '
            'xG\'siyle gol olur ya da olmaz (0,9\'luk tek net pozisyon ile 0,1\'lik dokuz uzak şutun toplamı aynı, '
            'gol olasılıkları farklıdır); bilinmeyenlerde toplam xG\'den. Fark: gerçek puan − xPts; en az '
            f'{fmt(SANS_ESIK, 0)} puan artı "şanslı" (ürettiğinden fazla puan toplamış), eksi "şanssız". Şanslı '
            'takımlar genelde sezonun devamında düşer, şanssızlar yükselir. '
            + (f'{len(maclar)} maçın xG\'sinden (indirilmiş maç sayfaları; tablodaki maç sayısından az olabilir)'
               if kaynak == 'mac' else f'{len(maclar)} maçın xG\'sinden')
            + (f', {sut_mac} tanesi şut şut.' if sut_mac else '.'))


def _lead_metni(S):
    return (f'{len(S.M)} maçın sonucundan hesaplandı' + (f', {len(S.U)} maç oynanmadı' if S.U else '')
            + '. Takım sayfası için takımın adına tıkla'
            + '. xG ve xGA, takımın ürettiği ve rakibe verdiği beklenen gol toplamıdır. Puan silme cezaları dahil değildir.'
            + (f' Hükmen sonuçlanan veya iptal edilen {S.skip} maç hesaba katılmadı.' if S.skip else ''))


def _puan_tablosu_html(depo, S):
    fm = form(S)
    nT = len(S.tablo)
    xv = (lambda v: fmt(v, 1)) if S.xg_var else (lambda v: '–')
    satirlar = []
    for i, r in enumerate(S.tablo):
        sinif = ' '.join(c for c in ('champ' if i == 0 else '', 'cl' if i < 4 else '', 'rel' if i >= nT - 3 else '') if c)
        f = ''.join(f'<i class="{x}" title="{FORM[x][1]}">{FORM[x][0]}</i>' for x in fm[r['i']])
        satirlar.append(f'<tr class="{sinif}"><td>{i + 1}</td><td class="takim-hucre">'
                        f'{takim_logo(depo.takim_kimligi(S.lig, r["name"]))}{takim_link(r["name"], r["name"])}</td><td>{r["O"]}</td><td>{r["G"]}</td>'
                        f'<td>{r["B"]}</td><td>{r["M"]}</td><td>{r["AG"]}</td><td>{r["YG"]}</td>'
                        f'<td>{"+" if r["AV"] > 0 else ""}{r["AV"]}</td><td>{xv(r["xG"])}</td><td>{xv(r["xGA"])}</td>'
                        f'<td class="pts">{r["P"]}</td><td><span class="form">{f}</span></td></tr>')
    return ('<table class="tb"><thead><tr><th>#</th><th>Takım</th><th>O</th><th>G</th><th>B</th><th>M</th><th>AG</th>'
            '<th>YG</th><th>AV</th><th>xG</th><th>xGA</th><th>P</th><th>Form</th></tr></thead><tbody>'
            + ''.join(satirlar) + '</tbody></table>')


def _krallik_html(depo, S, adet=10):
    """Ligin gol ve asist krallığı (ilk 10): eşitlikte daha az dakikada yapan önde. Oyuncuya tıklayınca kartı."""
    def tablo_(baslik, anahtar, ikinci, ikinci_ad, ucuncu, ucuncu_ad):
        sirali = sorted((p for p in S.PLY if p[anahtar] and p[anahtar] > 0), key=lambda p: (-p[anahtar], p['min']))[:adet]
        satirlar = []
        for k, p in enumerate(sirali):
            takim_ad = p['t'].split(' / ')[-1]
            ayr = f' <span class="cap">→ {e(p["ayrildi"][0] or "ayrıldı")}</span>' if p.get('ayrildi') else ''
            satirlar.append(
                f'<tr><td>{k + 1}</td><td><span class="link" data-idx="{e(p["idx"])}">{e(p["n"])}</span>{ayr}</td>'
                f'<td class="takim-hucre">{takim_logo(depo.takim_kimligi(S.lig, takim_ad))}{takim_link(takim_ad, takim_ad)}</td>'
                f'<td class="pts">{p[anahtar]}</td><td>{ikinci(p)}</td><td>{ucuncu(p)}</td></tr>')
        return (f'<div><div class="disp" style="font-size:1.1rem;font-weight:700">{baslik}</div>'
                f'<table class="tb krallik-tablo"><thead><tr><th>#</th><th>Oyuncu</th><th>Takım</th><th>{baslik.split()[0]}</th>'
                f'<th>{ikinci_ad}</th><th>{ucuncu_ad}</th></tr></thead><tbody>' + ''.join(satirlar)
                + '</tbody></table></div>' if satirlar else f'<div class="cap">{baslik}: henüz yok.</div>')
    xg_var = any(p['xg'] for p in S.PLY)
    return '<div class="krallik">' + tablo_(
        'Gol krallığı', 'g', (lambda p: fmt(p['xg'], 1)) if xg_var else (lambda p: '–'), 'xG',
        lambda p: f'{round(p["min"] / p["g"])} dk' if p['g'] else '–', 'Gol başına') + tablo_(
        'Asist krallığı', 'a', (lambda p: fmt(p['xa'], 1)) if xg_var else (lambda p: '–'), 'xA',
        lambda p: str(p['kp'] if p['kp'] is not None else '–'), 'Kilit pas') + '</div>'


KRALLIK_NOTU = ('Ligde bu sezon; eşitlikte daha az dakikada yapan önde. xG / xA: beklenen gol ve asist '
                '(oyuncunun pozisyon kalitesi). Oyuncuya tıklayınca kartı, takıma tıklayınca takım sayfası açılır.')


def _ys_iskeleti(ekle, kaldir_hepsi):
    """"Ya şöyle olursa?" bölümü: maç seçimi, skor, sabitle / hepsini kaldır düğmeleri ve sabitlenenler.
    Döner: ys_mac, ys_ev, ys_dep, ys_temizle, ys_liste."""
    with ui.expansion('Ya şöyle olursa? Maç sonucu sabitle', icon='science').classes('w-full').props('dense'):
        ui.label('Oynanmamış bir maça bir skor ver; simülasyon o maç hep o skorla bitecek şekilde yeniden oynatılır ve '
                 'tabloda değişim gösterilir. Birden çok maç sabitlenebilir.').classes('cap')
        with ui.row().classes('w-full items-end gap-2'):
            ys_mac = ui.select({}, label='Maç', with_input=True).props('outlined dense options-dense').style('min-width:300px')
            ys_ev = ui.number('Ev', value=1, min=0, max=9, step=1, format='%d').props('outlined dense').style('width:80px')
            ys_dep = ui.number('Dep.', value=0, min=0, max=9, step=1, format='%d').props('outlined dense').style('width:80px')
            ui.button('Sabitle', icon='push_pin', on_click=ekle).props('unelevated dense no-caps color=primary')
            ys_temizle = ui.button('Hepsini kaldır', icon='close', on_click=kaldir_hepsi).props('flat dense no-caps')
        ys_liste = ui.row().classes('w-full gap-2')
    return ys_mac, ys_ev, ys_dep, ys_temizle, ys_liste


def kur(G):
    with ui.column().classes('panel'):
        with ui.row().classes('w-full items-center'):
            ui.html('<h3>Puan durumu</h3>', sanitize=False)
            ui.space()
            disa_aktar.dugme('Excel\'e aktar', lambda: _aktar_tablosu(G.S), 'Puan durumu (süren sezonda simülasyon olasılıkları ve '
                             'fikstür zorluğuyla) İndirilenler\\MacTahmin klasörüne CSV olarak')
        lead = ui.label().classes('lead')
        tablo = takim_tiklama(ui.html('', sanitize=False).classes('kaydir'), G)
    with ui.column().classes('panel') as xp_panel:
        ui.html('<h3>Hak edilen puan (xPts) ve şans analizi</h3>', sanitize=False)
        sans = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
        xp_not = ui.label().classes('cap')
        xp_tablo = takim_tiklama(ui.html('', sanitize=False).classes('kaydir'), G)
    with ui.column().classes('panel') as fk_panel:
        ui.html('<h3>Fikstür zorluğu</h3>', sanitize=False)
        fk_not = ui.label().classes('cap')
        fk_tablo = takim_tiklama(ui.html('', sanitize=False).classes('kaydir'), G)
    with ui.column().classes('panel'):
        ui.html('<h3>Gol ve asist krallığı</h3>', sanitize=False)
        krallik_not = ui.label().classes('cap')
        krallik = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), G)
        krallik.on('click', lambda ev: G.oyuncu_ac(int(ev.args)) if str(ev.args or '').isdigit() else None,
                   js_handler='(e) => { const t = e.target.closest("[data-idx]"); if (t) emit(t.dataset.idx); }')
    with ui.column().classes('panel') as sim_panel:
        ui.html('<h3>Sezon sonu simülasyonu</h3>', sanitize=False)
        sim_lead = ui.label().classes('lead')
        ys_mac, ys_ev, ys_dep, ys_temizle, ys_liste = _ys_iskeleti(lambda: ys_ekle(), lambda: ys_kaldir(None))
        sim_tablo = takim_tiklama(ui.html('', sanitize=False).classes('kaydir'), G)
    ys = {'sabit': {}, 'sim': None, 'S': None}

    def ys_ekle():
        if ys_mac.value is None:
            ui.notify('Önce bir maç seç.')
            return
        h, a = (int(x) for x in str(ys_mac.value).split('-'))
        ys['sabit'][(h, a)] = (int(ys_ev.value or 0), int(ys_dep.value or 0))
        ys['sim'] = None
        G.arka_plan(sim_ciz())

    def ys_kaldir(anahtar):
        if anahtar is None:
            ys['sabit'].clear()
        else:
            ys['sabit'].pop(anahtar, None)
        ys['sim'] = None
        G.arka_plan(sim_ciz())

    def ys_liste_ciz(S):
        ys_liste.clear()
        with ys_liste:
            for (h, a), (hg, ag) in ys['sabit'].items():
                ui.button(f'{S.T[h]} {hg} – {ag} {S.T[a]}', icon='close', on_click=lambda _, k=(h, a): ys_kaldir(k)).props(
                    'outline dense no-caps size=sm color=primary')
        ys_temizle.set_visibility(bool(ys['sabit']))

    async def sim_ciz():
        S = G.S
        aktif = S.yil == SON_SEZON and len(S.U) > 0
        sim_panel.set_visibility(aktif)
        if not aktif:
            return
        if ys['S'] is not S:  # başka lig / sezon: sabitlenen sonuçlar sıfırlanır, maç listesi yenilenir
            ys.update(S=S, sim=None)
            ys['sabit'].clear()
            ys_mac.set_options({f'{m.h}-{m.a}': f'{m.d[8:10]}.{m.d[5:7]} · {S.T[m.h]} – {S.T[m.a]}' for m in S.U}, value=None)
        ys_liste_ciz(S)
        if S.sim is None:
            sim_lead.text = 'Simülasyon hesaplanıyor…'
            sim_tablo.content = ''
            S.sim = await run.io_bound(S.simulasyon)
            ys['sim'] = None  # temel simülasyon yenilendi: "ya şöyle olursa" da yeniden hesaplansın
            if G.S is not S:  # bu sırada başka sezona geçildiyse
                return
        if ys['sabit'] and ys['sim'] is None:
            sim_lead.text = 'Sabitlenen sonuçlarla yeniden hesaplanıyor…'
            ys['sim'] = await run.io_bound(S.simulasyon, 10000, dict(ys['sabit']))
            if G.S is not S:
                return
        sim_lead.text = _sim_lead(S)
        ozel = ys['sim'] if ys['sabit'] else None  # "ya şöyle olursa" sonucu (varsa) ve normal simülasyonla farkı
        if ozel:
            sim_lead.text += (f' "Ya şöyle olursa": {len(ys["sabit"])} maçın sonucu sabitlendi; küçük renkli sayılar normal '
                              'simülasyona göre değişim (yüzde puanı).')
        sim_tablo.content = _sim_html(G.depo, S, ozel)

    def fikstur_ciz(S):
        aktif = S.yil == SON_SEZON and len(S.U) > 0
        fk_panel.set_visibility(aktif)
        if not aktif:
            return
        fk_tablo.content = _fikstur_html(G.depo, S)
        fk_not.text = FIKSTUR_NOTU.format(FIKSTUR_SONRAKI)

    async def xp_ciz(S):
        maclar, kaynak = await run.io_bound(G.depo.xg_maclari, S)
        if G.S is not S:
            return
        if not maclar:
            xp_panel.set_visibility(False)
            return
        xp_panel.set_visibility(True)
        hp = hak_edilen_puan([m[1:] for m in maclar])
        sans.content = _sans_analizi(G.depo, S, hp)
        xp_tablo.content = _xp_html(G.depo, S, hp)
        xp_not.text = _xp_notu(maclar, kaynak)

    def yenile():
        S = G.S
        lead.text = _lead_metni(S)
        tablo.content = _puan_tablosu_html(G.depo, S)
        krallik.content = _krallik_html(G.depo, S)
        krallik_not.text = KRALLIK_NOTU
        G.arka_plan(sim_ciz())
        G.arka_plan(xp_ciz(S))
        fikstur_ciz(S)

    return yenile
