"""Oyuncu kartının saf metin, HTML ve grafik seçenekleri üreticileri (arayüz öğesine dokunmaz): özet, mevkidaşlara göre
yüzdelikler, ayrıntılar, şut haritası, sezon / kulvar tabloları, son maçlar ve benzer oyuncu süzgeci. Pencere: oyuncu_karti.py."""
from .. import lig_maclari
from ..bicim import para as _para
from ..logo import logo_html, takim_logo_url
from ..mac_ozeti import fiziksel_yazi
from ..sezon import (BUYUK_MAC, EK, HAVA_HAKIMI, OZEL_ROLLER, POS, SON_SEZON, TAKVIM_YILI, mevki_adi, sezon_etiketi, yas_hesap,
                     yas_metni)
from .ortak import e, fmt, ilk_kucuk, kucuk, lig_bilgi, sayi, takim_link, yuzde

# "Ayrıntılar"da toplamın yanına 90 dakika başına değeri de yazılan istatistikler: sezon toplamı olan ek istatistikler
# (top çalma, uzaklaştırma, kurtarış…) ve şut, kilit pas. Maç sayısı gibi 90 dakikaya çevrilmesi anlamsız olanlar hariç.
DOKSAN = {ad for ad, tur in EK.values() if tur == 't'} - {'Gol yemeden maç'} | {'Şut', 'Kilit pas'}
BENZER_ADET = 8
GELISIM_TREND_DK = 900  # gelişim eğilimi (yükselişte / düşüşte) yalnızca en az bu kadar oynanan sezonlardan
SUT_RENK = {'Goal': '#2f7a57', 'AttemptSaved': '#35598a', 'Post': '#c9960f', 'Miss': '#8a9088'}
SUT_AD = {'Goal': 'Gol', 'AttemptSaved': 'İsabetli (kurtarıldı)', 'Post': 'Direk', 'Miss': 'İsabetsiz'}
DURUM_AD = {'RegularPlay': 'açık oyun', 'FastBreak': 'hızlı hücum', 'SetPiece': 'duran top', 'FromCorner': 'korner',
            'Penalty': 'penaltı', 'FreeKick': 'serbest vuruş', 'ThrowInSetPiece': 'taç'}
KULVAR_NOTU = ('Kaynak: FotMob. Her sezonda takımla oynadığı bütün kulvarlar (lig, yerel kupa, Avrupa kupaları…) ve '
               'toplamı; uygulamada olmayan ligler dahil. Puan: FotMob maç puanı ortalaması. Dakika ve xG için '
               '"Lig ayrıntısı"na geç.')


def sut_haritasi(sutlar):
    """Rakip yarı saha (kale üstte) üzerinde şutlar: FotMob x 0-105 (rakip kale 105), y 0-68 → SVG (y, 105 − x)."""
    cizgi = 'fill="none" stroke="currentColor" stroke-opacity=".35" stroke-width=".35"'
    saha = (f'<rect x="0" y="0" width="68" height="52.5" {cizgi}/>'
            f'<rect x="13.84" y="0" width="40.32" height="16.5" {cizgi}/>'
            f'<rect x="24.84" y="0" width="18.32" height="5.5" {cizgi}/>'
            f'<path d="M 26.7 16.5 A 9.15 9.15 0 0 0 41.3 16.5" {cizgi}/>'
            f'<circle cx="34" cy="11" r=".4" fill="currentColor" fill-opacity=".4"/>'
            f'<path d="M 24.85 52.5 A 9.15 9.15 0 0 1 43.15 52.5" {cizgi}/>'
            '<rect x="30.34" y="-1.2" width="7.32" height="1.2" fill="currentColor" fill-opacity=".45"/>')
    noktalar = []
    for s in sorted(sutlar, key=lambda s: s['sonuc'] == 'Goal'):  # goller üstte
        r = 0.7 + 3.2 * max(s['xg'] or 0, 0) ** 0.5
        renk = SUT_RENK.get(s['sonuc'], '#8a9088')
        dolu = s['sonuc'] in ('Goal', 'AttemptSaved', 'Post')
        baslik = (f'{s["dk"]}. dk · {s.get("rakip") or ""} · {SUT_AD.get(s["sonuc"], s["sonuc"])} · xG {fmt(s["xg"] or 0, 2)}'
                  f' · {DURUM_AD.get(s["durum"], s["durum"] or "")}')
        noktalar.append(f'<circle cx="{s["y"]:.2f}" cy="{105 - s["x"]:.2f}" r="{r:.2f}" fill="{renk}" '
                        f'fill-opacity="{.8 if dolu else .25}" stroke="{renk}" stroke-width=".35"><title>{e(baslik)}</title></circle>')
    return (f'<svg viewBox="-1 -2 70 55" style="width:100%;max-width:340px;color:var(--ink);background:var(--panel-2);'
            f'border-radius:8px">{saha}{"".join(noktalar)}</svg>')


# ---------------------------------------------------------------- saf metin / HTML üreticiler (arayüz öğesine dokunmaz)
def meta_metni(p, S):
    """Başlık altındaki satır: takım · mevki · yaş · rol · uyruk · lig ve sezon."""
    lg = lig_bilgi(S.lig)
    mevki = mevki_adi(p)
    if p.get('pos_tahmin') == 'coklu':
        mevki += f' ({" ve ".join(kucuk(POS[x]) for x in p["adaylar"])} oynadı; ana mevki istatistiklere göre)'
    elif p.get('pos_tahmin'):
        mevki += ' (istatistiklere göre tahmini)'
    neden = S.rol_nedeni(p)
    if p.get('rol'):
        rol_metni = f'Rol: {p["rol"]}'
    elif neden == 'az süre':
        rol_metni = f'Rol yok (az süre: en az {S.roller["esik"]} dk gerekir)'
    elif neden == 'kaleci':
        rol_metni = ''  # kaleciler için rol tanımlı değil; mevki zaten "Kaleci"
    else:
        rol_metni = f'Rol yok ({neden})'
    ayr = p.get('ayrildi')
    if ayr and ayr[0]:
        tarih = f', {ayr[1][8:10]}.{ayr[1][5:7]}.{ayr[1][:4]} transfer' if ayr[1] else ''
        takim = f'{ayr[0]} (önceki kulübü {p["t"]}{tarih}; bu sezonki istatistikleri {p["t"]} formasıyla)'
    elif ayr:
        takim = f'{p["t"]} (takımdan ayrıldı; bu sezonki istatistikleri {p["t"]} formasıyla)'
    else:
        takim = p['t']
    return ' · '.join(x for x in (takim, mevki, yas_metni(p.get('yas'), S.yil), rol_metni, p['cc'],
                                  f'{lg[1]} {sezon_etiketi(S.yil, S.lig)}') if x)


def ozel_html(p):
    aciklama = {ad_: ac for ad_, ac, _ in OZEL_ROLLER}
    aciklama[HAVA_HAKIMI[0]] = HAVA_HAKIMI[1]
    aciklama[BUYUK_MAC[0]] = BUYUK_MAC[1]
    return ''.join(f'<span class="ozel-rol" title="{e(aciklama.get(r, ""))}">★ {e(r)}</span>' for r in p.get('ozel') or [])


def rozet_html(p, k):
    rt = k['puan']
    return (f'<div class="disp" style="font-size:2rem;font-weight:700;color:var(--pitch)">{fmt(rt) if rt is not None else p["g"] + p["a"]}</div>'
            f'<div class="cap">{"FotMob puanı" if rt is not None else "gol + asist"}</div>')


def kutular_html(p):
    return '<div class="tiles">' + ''.join(
        f'<div class="tile"><span class="num">{v}</span><small>{l}</small></div>'
        for l, v in (('Maç', p['mp']), ('Dakika', sayi(p['min'])), ('Gol', p['g']), ('Asist', p['a']),
                     ('xG', fmt(p['xg'], 1)), ('xA', fmt(p['xa'], 1)))) + '</div>'


def yuzdelik_bilgi(k, p, S):
    """(mevkidaşlara göre çubukların HTML'i, altındaki not)."""
    if not k['yuzdelik']:
        return '', 'Bu oyuncu için karşılaştırma yapılacak veri yok.'
    icerik = ''.join(
        f'<div class="pctrow"><span>{e(l)} <small>{fmt(v)}</small></span><div class="track"><i style="width:{max(pc, 2)}%;'
        f'background:{"var(--pitch)" if pc >= 67 else "var(--lamp)" if pc >= 34 else "var(--draw)"}"></i></div>'
        f'<span class="pv">{pc}</span></div>' for l, v, pc in k['yuzdelik'])
    gk = p['pos'] == 'G'
    grup = 'kaleci' if gk else 'saha oyuncusu' if p['pos'] in ('S', 'U') else f'{kucuk(POS[p["pos"]])} oyuncusu'
    return icerik, (f'Değerler 90 dakika başına (oranlar olduğu gibi). Sağdaki sayı yüzdelik dilim: ligde en az {S.min_esik} '
                    f'dakika oynayan {k["es_sayisi"]} {grup} arasında yüzde kaçının önünde olduğu (99: neredeyse '
                    'hepsinden iyi, 50: ortada).'
                    + (' Bu oyuncu az süre aldığı için oranlar yanıltıcı olabilir.' if k['az_sure'] else ''))


def ayrinti_html(k, p):
    satirlar = []
    for etiket, v in k['detay']:
        if v is None:
            continue
        ham = v  # biçimlendirmeden önceki sayı (90 dk başına değer bundan hesaplanır)
        if etiket == 'Gol − xG':
            v = ('+' if v > 0 else '') + fmt(v, 1)
        elif etiket == 'Gol katkısı sıklığı (dk)':
            etiket, v = 'Gol katkısı sıklığı', f'{v} dakikada bir'
        elif etiket == 'Takım gollerindeki payı':
            v = yuzde(v)
        elif etiket == 'Şut başına gol':
            v = fmt(v)
        elif isinstance(v, float):
            tur = next((t for ad_, t in EK.values() if ad_ == etiket), 't')
            v = fmt(v, 2) if tur == 'r' or not v.is_integer() else int(v)
        ek = ''
        if etiket in DOKSAN and p['min'] > 0 and isinstance(ham, (int, float)) and ham:
            ek = f' <small class="cap">(90 dk\'da {fmt(ham / p["min"] * 90, 2 if abs(ham / p["min"] * 90) < 1 else 1)})</small>'
        satirlar.append(f'<dt>{e(etiket)}</dt><dd>{e(v)}{ek}</dd>')
    return '<dl class="kv">' + ''.join(satirlar) + '</dl>'


def istikrar_html(v):
    return (
        f'<div class="cap"><b>Maçtan maça istikrar:</b> {e(lig_maclari.istikrar_yazisi(v))}. Bu sezon ligde en az '
        f'{lig_maclari.ISTIKRAR_MIN_DK} dakika oynadığı maçlardaki FotMob puanlarının ne kadar dalgalandığı; yüzdelik, '
        f'ligdeki oyuncuların (kalecilerde kalecilerin) yüzde kaçından daha istikrarlı olduğu. Kötü maç: '
        f'{fmt(lig_maclari.ISTIKRAR_KOTU, 1)} altı.</div>' if v else
        f'<div class="cap"><b>Maçtan maça istikrar:</b> hesaplamak için bu sezon ligde en az '
        f'{lig_maclari.ISTIKRAR_MIN_MAC} maç ({lig_maclari.ISTIKRAR_MIN_DK}+ dakika) gerekiyor.</div>')


def sut_notu(sutlar):
    gol = sum(1 for s in sutlar if s['sonuc'] == 'Goal' and not s['kk'])
    isabet = sum(1 for s in sutlar if s['sonuc'] in ('Goal', 'AttemptSaved'))
    xg = sum(s['xg'] or 0 for s in sutlar)
    ceza = sum(1 for s in sutlar if s['x'] >= 88.5 and 13.84 <= s['y'] <= 54.16)
    return (f'{len(sutlar)} şut, {isabet} isabetli, {gol} gol · toplam xG {fmt(xg, 1)} '
            f'(şut başına {fmt(xg / len(sutlar), 2)}) · %{round(ceza / len(sutlar) * 100)} ceza sahası içinden. '
            'Daire büyüklüğü xG; yeşil gol, mavi isabetli, sarı direk, gri isabetsiz.')


def deger_isaretleri(degerler):
    """Takım değişiklikleri: yeni takımın ilk ayına işaret (en çok son 6)."""
    isaret = [{'coord': [t, round(v / 1e6, 2)], 'value': tk[:10]}
              for k, (t, v, tk) in enumerate(degerler) if k and tk != degerler[k - 1][2]]
    return isaret[-6:]


def deger_notu(degerler):
    en = max(degerler, key=lambda x: x[1])
    return (f'Şu an {_para(degerler[-1][1])}; en yüksek {_para(en[1])} ({en[0][5:7]}.{en[0][:4]}). '
            f'Aylık, FotMob\'un değer tahmini (SciSports); işaretler takım değişikliği.')


def fiziksel_html(o, havuz):
    def sira(k):
        if o['dk'] < lig_maclari.FIZIKSEL_MIN_DK or len(havuz) < 10:
            return ''
        alt = sum(1 for x in havuz if x[k] < o[k])
        return f'<small style="display:block">ligde yüzdelik: {round(alt / len(havuz) * 100)}</small>'
    return '<div class="tiles">' + ''.join(
        f'<div class="tile"><span class="num">{v}</span><small>{a}</small>{s}</div>' for a, v, s in (
            ('En yüksek hız', fiziksel_yazi('hiz', o['hiz']), sira('hiz')),
            ('Koşu (90 dk)', fiziksel_yazi('mesafe', o['mesafe90']), sira('mesafe90')),
            ('Sprint (90 dk)', fmt(o['sprint90'], 1), sira('sprint90')),
            ('Toplam koşu', fiziksel_yazi('mesafe', o['mesafe']), ''),
            ('Toplam sprint', str(o['sprint']), ''),
            ('Sprint mesafesi', fiziksel_yazi('sprint_m', o['sprint_m']), ''))) + '</div>'


def fiziksel_notu(o, havuz):
    return (f'{o["mac"]} maç, {sayi(o["dk"])} dakika. Kaynak FotMob (şimdilik yalnızca Premier League\'de var). '
            f'Kıyas: ligde en az {lig_maclari.FIZIKSEL_MIN_DK} dakika oynamış {len(havuz)} oyuncu. Sprint: '
            'yüksek hızdaki koşular; en yüksek hız sezonun tek maçındaki en iyisi.')


def _kilometre_taslari(sezonlar):
    """Kariyer toplamları (kulüp ve milli takım) ve yaklaşan yuvarlak sayılar: '100. kulüp golüne 3 gol kaldı'."""
    esikler = [10, 25, 50, 75, 100, 150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900, 1000]
    toplam, son_yil = {}, {}
    for s in sezonlar:
        t = toplam.setdefault(s['grup'], {'mac': 0, 'gol': 0, 'asist': 0})
        for k in t:
            t[k] += s[k]
        yil = s['sezon'][:4]
        if yil.isdigit():
            son_yil[s['grup']] = max(son_yil.get(s['grup'], 0), int(yil))
    notlar = []
    for grup, t in toplam.items():
        # yaklaşan sayı yalnızca hâlâ oynayana: kulüpte son iki sezon, milli takımda son üç yıl içinde oynamış
        if son_yil.get(grup, 0) < SON_SEZON - (1 if grup == 'Kulüp' else 2):
            continue
        onek = 'kulüp' if grup == 'Kulüp' else 'milli takım'
        for k, ad, yakin in (('mac', 'maçına', 10), ('gol', 'golüne', 5), ('asist', 'asistine', 5)):
            sonraki = next((x for x in esikler if x > t[k]), None)
            if sonraki and t[k] >= 5 and sonraki - t[k] <= yakin:
                kalan = sonraki - t[k]
                birim = {'mac': 'maç', 'gol': 'gol', 'asist': 'asist'}[k]
                notlar.append(f'{sonraki}. {onek} {ad} {kalan} {birim} kaldı')
    ozet = ' · '.join(f'{"Kulüp" if g == "Kulüp" else "Milli takım"}: {t["mac"]} maç, {t["gol"]} gol, {t["asist"]} asist'
                      for g, t in toplam.items())
    return (f'<div class="kariyer-ozet"><b>Kariyer</b> · {e(ozet)}'
            + (''.join(f'<div class="kilometre">🎯 {e(n)}</div>' for n in notlar)) + '</div>')


def _kulvar_puan(x):
    if not x:
        return '–'
    renk = 'var(--pitch-2)' if x >= 7.5 else 'var(--lamp)' if x >= 6.5 else 'var(--bad)'
    return f'<span style="font-weight:700;color:{renk}">{fmt(x, 2)}</span>'


def kulvar_html(sezonlar):
    """FotMob kariyeri: sezon sezon, takım takım toplam ve altında kulvar kulvar (lig, kupa, Avrupa…)."""
    puan = _kulvar_puan
    satirlar, grup0 = [], None
    for s in sezonlar:
        if s['grup'] != grup0:
            grup0 = s['grup']
            satirlar.append(f'<tr class="kr-grup"><td colspan="6">{"Kulüp kariyeri" if grup0 == "Kulüp" else "Milli takım"}</td></tr>')
        logo = logo_html(takim_logo_url(s['takim_id']), bos='')
        logo = logo + ' ' if logo else ''
        takim_ad = takim_link(s['takim'], s['takim_id']) if s['takim_id'] and s['grup'] == 'Kulüp' else e(s['takim'])
        # tek kulvar: alt satır toplamı tekrarlamasın, kulvarın adı takımın yanına yazılır
        tek_kulvar = f' <span class="cap">· {e(s["turnuvalar"][0]["ad"])}</span>' if len(s['turnuvalar']) == 1 else ''
        kiralik = ' <span class="cap">(kiralık)</span>' if s['kiralik'] else ''
        satirlar.append(f'<tr class="kr-sezon"><td>{e(s["sezon"])}</td><td>{logo}{takim_ad}{kiralik}{tek_kulvar}</td>'
                        f'<td>{s["mac"]}</td><td>{s["gol"]}</td><td>{s["asist"]}</td><td>{puan(s["puan"])}</td></tr>')
        if len(s['turnuvalar']) > 1:
            for t in s['turnuvalar']:
                satirlar.append(f'<tr class="kr-kulvar"><td></td><td>{e(t["ad"])}{" (hazırlık)" if t["hazirlik"] else ""}</td>'
                                f'<td>{t["mac"]}</td><td>{t["gol"]}</td><td>{t["asist"]}</td><td>{puan(t["puan"])}</td></tr>')
    return (_kilometre_taslari(sezonlar)
            + '<table class="tb kariyer-tablo"><thead><tr><th>Sezon</th><th>Takım / kulvar</th><th>Maç</th><th>Gol</th>'
            '<th>Asist</th><th>Puan</th></tr></thead><tbody>' + ''.join(satirlar) + '</tbody></table>')


def son_maclar_notu(maclar):
    puanlar = [m['puan'] for m in maclar if m['puan']]
    # form endeksi (uygulamanın hesabı): son 5 maçın puan ortalaması, son 25 maçın ortalamasıyla karşılaştırılır
    son5 = [m['puan'] for m in maclar if m['puan'] and m['dk'] >= 20][-5:]
    form = ''
    if len(son5) >= 3 and puanlar:
        f5, genel = sum(son5) / len(son5), sum(puanlar) / len(puanlar)
        durum = 'formda ↑' if f5 - genel >= 0.25 else 'düşüşte ↓' if f5 - genel <= -0.25 else 'normal'
        form = f' Form: son {len(son5)} maç ortalaması {fmt(f5)} (genel {fmt(genel)}) → {durum}.'
    return (f'Son {len(maclar)} maç (bütün kulvarlar ve milli takım): {sum(m["gol"] for m in maclar)} gol, '
            f'{sum(m["asist"] for m in maclar)} asist, {sum(m["dk"] for m in maclar)} dakika'
            + (f', ortalama FotMob puanı {fmt(sum(puanlar) / len(puanlar))}' if puanlar else '') + '.' + form
            + ' Puanlar FotMob\'un, form uygulamanın hesabı (fark en az ±0,25 puansa).')


def son_maclar_html(maclar):
    satirlar = []
    for m in reversed(maclar):
        biz, onlar = (m['skor'][0], m['skor'][1]) if m['ev'] else (m['skor'][1], m['skor'][0])
        sonuc = '' if biz is None else 'G' if biz > onlar else 'B' if biz == onlar else 'M'
        puan = m['puan']
        renk = '' if not puan else 'var(--pitch-2)' if puan >= 7.5 else 'var(--lamp)' if puan >= 6.5 else 'var(--bad)'
        satirlar.append(
            f'<tr><td class="cap">{m["zaman"][8:10]}.{m["zaman"][5:7]}.{m["zaman"][:4]}</td><td class="cap">{e(m["turnuva"])}</td>'
            f'<td>{e(m["takim"])} – {e(m["rakip"])} <span class="cap">({"ev" if m["ev"] else "dep."})</span></td>'
            f'<td>{"" if biz is None else f"{biz}–{onlar}"} <span class="form">{f"<i class={sonuc}>{sonuc}</i>" if sonuc else ""}</span></td>'
            f'<td>{m["dk"]}\'</td><td>{m["gol"] or ""}</td><td>{m["asist"] or ""}</td>'
            f'<td style="font-weight:700;color:{renk}">{fmt(puan, 1) if puan else "–"}</td></tr>')
    return ('<table class="tb"><thead><tr><th>Tarih</th><th>Turnuva</th><th>Maç</th><th>Skor</th><th>Dk</th>'
            '<th>Gol</th><th>Asist</th><th>Puan</th></tr></thead><tbody>' + ''.join(satirlar) + '</tbody></table>')


def benzer_suz_uygula(depo, d, S, p, sonuc):
    """Benzer oyuncular süzgeci: 'genc' kendisinden genç, 'ucuz' piyasa değeri kendisinden düşük (değeri bilinenler).
    Döner: [(oyuncu, lig, benzerlik, yaş, değer)] (en çok BENZER_ADET)."""
    degerler = {}
    out = []
    for q, lig_anahtar, b in sonuc:
        yas = q.get('yas') if lig_anahtar == S.lig else yas_hesap(q.get('dogum'), S.yil, lig_anahtar in TAKVIM_YILI)
        if lig_anahtar not in degerler:
            degerler[lig_anahtar] = depo.degerler_onbellek(lig_anahtar) if S.yil == SON_SEZON else {}
        fm = q.get('fm_id')
        dg = degerler[lig_anahtar].get(int(fm)) if str(fm).isdigit() else None
        if d['benzer_suz'] == 'genc' and not (yas is not None and p.get('yas') is not None and yas < p['yas']):
            continue
        if d['benzer_suz'] == 'ucuz' and not (dg and d.get('deger') and dg < d['deger']):
            continue
        out.append((q, lig_anahtar, b, yas, dg))
        if len(out) >= BENZER_ADET:
            break
    return out


def benzer_notu(d, p, r, esik):
    tanim = ', '.join(ilk_kucuk(t[1]) for t in r['tanimlar'])
    return (f'Benzerlik; {tanim} değerlerinin (90 dakika başına) '
            + ('bu ligde' if d['kapsam'] == 'lig' else 'aynı veri kaynağındaki liglerde')
            + f' en az {esik} dakika oynayan {r["n"]} oyuncu arasındaki konumuna göre hesaplanır; '
              'hem oyun tarzı hem üretim düzeyi benzer olmalı.'
            + ({'genc': f' Yalnızca kendisinden ({p.get("yas")} yaş) genç olanlar.',
                'ucuz': f' Yalnızca piyasa değeri kendisinden ({_para(d["deger"]) if d.get("deger") else "–"}) '
                        'düşük olanlar (FotMob değeri).', '': ''}[d['benzer_suz']])
            + (' Bu oyuncu az süre aldığı için sonuçlar yanıltıcı olabilir.' if p['min'] < esik else ''))


def gelisim_notu(noktalar):
    # eğilim yalnızca yeterli süre alınan sezonlardan (az maçlı sezonda endeks 50'ye çekilir, yanıltır)
    dolu = [n[1] for n in noktalar if n[1] is not None and n[3] >= GELISIM_TREND_DK]
    egilim = ''
    if len(dolu) >= 3:
        fark = dolu[-1] - sum(dolu[:-1]) / len(dolu[:-1])
        egilim = (f' En az {GELISIM_TREND_DK} dakika oynadığı son sezonu, önceki sezonlarının ortalamasından '
                  + (f'{fmt(fark, 0)} puan yüksek: yükselişte.' if fark >= 5
                     else f'{fmt(-fark, 0)} puan düşük: düşüşte.' if fark <= -5 else 'farksız: istikrarlı.'))
    return ('Performans endeksi (0-100): o sezon ligindeki mevkidaşlarına göre yüzdeliklerin ortalaması; az süre '
            'alınan sezonda ortalamaya (50) çekilir, eşiğin altında süre alınan sezonda yoktur. Çubuklar 90 '
            'dakikada gol + asist. Lig seviyeleri farklıdır: aynı endeks zor ligde daha değerlidir.' + egilim)


def son_grafik_secenekleri():
    return {
        'animation': False, 'tooltip': {'trigger': 'axis'}, 'legend': {'bottom': 0},
        'grid': {'left': 40, 'right': 40, 'top': 14, 'bottom': 56},
        'xAxis': {'type': 'category', 'data': [], 'axisLabel': {'fontSize': 10}},
        'yAxis': [{'type': 'value', 'name': 'Gol / asist', 'minInterval': 1, 'max': 3},
                  {'type': 'value', 'name': 'Puan', 'min': 4, 'max': 10, 'splitLine': {'show': False}}],
        'series': [{'name': 'Gol', 'type': 'bar', 'stack': 'ga', 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                   {'name': 'Asist', 'type': 'bar', 'stack': 'ga', 'itemStyle': {'color': '#c9960f'}, 'data': []},
                   {'name': 'FotMob puanı', 'type': 'line', 'yAxisIndex': 1, 'connectNulls': True,
                    'itemStyle': {'color': '#35598a'}, 'data': []}],
    }


def deger_grafik_secenekleri():
    return {
        'animation': False, 'tooltip': {'trigger': 'axis'},
        'grid': {'left': 56, 'right': 16, 'top': 14, 'bottom': 30},
        'xAxis': {'type': 'time'}, 'yAxis': {'type': 'value', 'name': 'M€', 'min': 0},
        'series': [{'name': 'Piyasa değeri (M€)', 'type': 'line', 'step': 'end', 'showSymbol': False,
                    'areaStyle': {'opacity': .12}, 'itemStyle': {'color': '#2f7a57'}, 'data': [],
                    'markPoint': {'symbol': 'pin', 'symbolSize': 34, 'label': {'fontSize': 9}, 'data': []}}],
    }


def gelisim_grafik_secenekleri():
    return {
        'animation': False, 'tooltip': {'trigger': 'axis'}, 'legend': {'bottom': 0},
        'grid': {'left': 40, 'right': 44, 'top': 16, 'bottom': 60},
        'xAxis': {'type': 'category', 'data': [], 'axisLabel': {'fontSize': 10}},
        'yAxis': [{'type': 'value', 'name': 'Endeks', 'min': 0, 'max': 100},
                  {'type': 'value', 'name': 'G+A / 90', 'min': 0, 'splitLine': {'show': False}}],
        'series': [{'name': 'Performans endeksi', 'type': 'line', 'connectNulls': True, 'symbolSize': 8,
                    'lineStyle': {'width': 3}, 'itemStyle': {'color': '#2f7a57'}, 'data': []},
                   {'name': 'Gol + asist (90 dk)', 'type': 'bar', 'yAxisIndex': 1, 'barMaxWidth': 26,
                    'itemStyle': {'color': 'rgba(201,150,15,.55)'}, 'data': []}],
    }
