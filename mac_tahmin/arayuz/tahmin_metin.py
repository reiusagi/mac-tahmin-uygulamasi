"""Maç tahmini sekmesinin saf metin ve HTML üreticileri (arayüz öğesine dokunmaz): özet cümlesi, olasılık panosu, skor
matrisi, geçmiş karşılaşmalar, tarih / stadyum / hakem satırı ve oyuncu listelerinin açıklamaları. Sekme: tahmin.py."""
from nicegui import ui

from .. import karne
from ..modeller import piyasalar
from ..stadyum import stadyum_bul
from .ortak import e, fmt, kisa_gun, sayi, tarih_uzun, yerel, yuzde

GUVEN_YUKSEK, GUVEN_ORTA = 0.60, 0.45  # model güveni etiketi: en olası sonucun olasılığına göre
ASIST_ACIKLAMA = ('90 dakika oynarsa en az bir asist yapma olasılığı: takımın beklenen asistleri (beklenen golün '
                  '~%75\'i), oyuncunun asist ve xA oranına göre dağıtılır; oran önceki iki sezonla ve mevkinin '
                  'ortalamasıyla harmanlanır.')


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


def guven_metni(depo, S, p):
    """Model güveni: favorinin olasılığına göre etiket ve modelin geçmişte (Karne) buna benzer olasılık verdiği
    maçlarda favorinin gerçekten kazanma oranı."""
    pmax = max(p)
    fav = ['ev sahibi', 'beraberlik', 'deplasman'][p.index(pmax)]
    etiket, renk = (('yüksek', 'var(--pitch-2)') if pmax >= GUVEN_YUKSEK else ('orta', 'var(--lamp)') if pmax >= GUVEN_ORTA
                    else ('düşük (dengeli maç)', 'var(--bad)'))
    kayitlar = karne.oku_onbellek(depo.veri_klasoru)
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


def olasilik_html(depo, S, h, a, t):
    """Pano: renkli çubuk (sayısız) ve altında üç sonuç, beklenen gol, kısa özet ve model güveni; ayrıntılı açıklama
    "Bu tahmin nasıl hesaplanıyor?" altında."""
    p = t['p']
    pmax = max(p)
    sonuc_ad = [f'{S.T[h]} kazanır', 'Beraberlik', f'{S.T[a]} kazanır']
    i_, j_, pr_ = t['skorlar'][0]
    pz_ = piyasalar(t['hucreler'])
    return (
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
        + guven_metni(depo, S, p))


def aciklama_html(S):
    return ('<div style="line-height:1.5">Beklenen gol: modelin bu maçta her takım için beklediği ortalama gol (soldaki ev '
            'sahibinin, sağdaki deplasmanın); skor olasılıkları bundan hesaplanır. Takım güçleri son sezonların gol ve '
            'xG\'sinden (eski maçların ağırlığı azalır)' + (', kadro değerine göre hafif düzeltmeyle' if S.kadro_degeri else '')
            + '; sonuç olasılıkları maç maç güncellenen Elo puanıyla harmanlanır (%65 gol modeli, %35 Elo). Model güveni: en '
            'olası sonucun olasılığı; yanında modelin geçmişte buna benzer olasılık verdiği maçlarda ne kadar tuttuğu. Kadro '
            'eksikleri: eksik oyuncuların sezondaki gol ve xG payının yarısı kadar beklenen gol düşülür (yerine oynayan açığın '
            'yarısını kapatır sayılır); savunma eksikleri hesaba katılmaz; ana tahmine değil ayrı satıra yansır.</div>')


def _bilgi_oge(simge, metin, ipucu=''):
    return (f'<span title="{e(ipucu)}"><i class="material-icons">{simge}</i>{e(metin)}</span>' if metin else '')


def bilgi_html(depo, S, h, a, oynanan):
    """Tarih · stadyum · hakem · oynandıysa sonucu: yaklaşan maçın detayı varsa oradan, yoksa ev sahibinin iç sahası."""
    fm = depo.canli_mac(S, h, a)
    ev_std = stadyum_bul(depo.stadyumlar(), S.lig, S.T[h])
    if fm and fm.get('stadyum'):
        std = {'ad': fm['stadyum'], 'sehir': fm.get('sehir'),
               'kapasite': ev_std.get('kapasite') if ev_std and ev_std.get('ad') == fm['stadyum'] else None}
    else:
        std = ev_std
    z = yerel(fm['baslangic']) if fm and fm.get('baslangic') else None
    parcalar = [
        _bilgi_oge('event', f'{kisa_gun(z.date())} · {z:%H:%M}' if z else ''),
        _bilgi_oge('stadium', ' · '.join(x for x in (std.get('ad'), std.get('sehir')) if x) if std else '',
                   f'{sayi(std["kapasite"])} kişilik' if std and std.get('kapasite') else ''),
        _bilgi_oge('sports', (f'Hakem: {fm["hakem"]["ad"]}' + (f' · maç başına {fmt(fm["hakem"]["sariOrt"])} sarı'
                                                               if fm['hakem'].get('sariOrt') is not None else '')
                              if fm.get('hakem') else 'Hakem henüz atanmadı') if fm else '',
                   hakem_metni(fm['hakem']) if fm and fm.get('hakem') else ''),
        _bilgi_oge('history', f'Bu sezon oynandı: {oynanan.hg}–{oynanan.ag} ({tarih_uzun(oynanan.d)})' if oynanan else '')]
    return ''.join(parcalar)


def matris_html(S, h, a, t, oynanan):
    """Skor matrisi (0-5 gol)."""
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
    return html + '</div></div>'


def enolasi_ciz(enolasi, t):
    enolasi.clear()
    with enolasi:
        ilk = t['skorlar'][0][2]
        for i, j, pr in t['skorlar']:
            ui.html(f'<div class="satir"><span class="num disp" style="font-size:1.2rem;font-weight:700">{i} – {j}</span>'
                    f'<div class="track"><i style="width:{pr / ilk * 100:.0f}%"></i></div><span class="pv">{fmt(pr * 100, 1)}%</span></div>',
                    sanitize=False).classes('w-full')


def h2h_html(maclar, ev, dep):
    """(özet, tablo) HTML'i: iki takımın bu ligdeki son karşılaşmaları."""
    if not maclar:
        return '<p class="cap">Bu ligde (uygulamadaki sezonlarda) aralarında maç yok.</p>', ''
    g1 = sum(1 for m in maclar if (m[1] == ev and m[3] > m[4]) or (m[2] == ev and m[4] > m[3]))
    g2 = sum(1 for m in maclar if (m[1] == dep and m[3] > m[4]) or (m[2] == dep and m[4] > m[3]))
    b = len(maclar) - g1 - g2
    gol1 = sum(m[3] if m[1] == ev else m[4] for m in maclar)
    gol2 = sum(m[3] if m[1] == dep else m[4] for m in maclar)
    ozet = (
        f'<div class="lead">Son {len(maclar)} karşılaşma: <b>{e(ev)}</b> {g1} galibiyet · {b} beraberlik · '
        f'<b>{e(dep)}</b> {g2} galibiyet · goller {gol1}–{gol2}</div>'
        f'<div class="bar" style="margin:6px 0 4px"><div class="h" style="flex-basis:{g1 / len(maclar) * 100:.1f}%">'
        f'{g1 or ""}</div><div class="d" style="flex-basis:{b / len(maclar) * 100:.1f}%">{b or ""}</div>'
        f'<div class="a" style="flex-basis:{g2 / len(maclar) * 100:.1f}%">{g2 or ""}</div></div>')
    tablo = '<table class="tb"><tbody>' + ''.join(
        f'<tr><td class="cap">{m[0][8:10]}.{m[0][5:7]}.{m[0][:4]}</td><td style="text-align:right">'
        f'{"<b>" if m[3] > m[4] else ""}{e(m[1])}{"</b>" if m[3] > m[4] else ""}</td><td class="hi" style="text-align:center">'
        f'{m[3]} – {m[4]}</td><td>{"<b>" if m[4] > m[3] else ""}{e(m[2])}{"</b>" if m[4] > m[3] else ""}</td></tr>'
        for m in maclar) + '</tbody></table>'
    return ozet, tablo


def golcu_metni(S, guncel):
    return (f'90 dakika oynarsa en az bir gol atma olasılığı. Takımın beklenen golü, oyuncunun gol ve xG '
            f'oranına göre dağıtılır. Oran, oyuncunun önceki iki sezonuyla ve mevkisinin ortalamasıyla '
            f'harmanlanır: sezon başında birkaç maçlık şanslı gidiş olasılığı şişirmez. En az {S.min_esik} '
            f'dakika oynamış ya da önceki sezonlarda düzenli oynamış oyuncular.'
            + (' Güncel kadro ve sakatlıklar FotMob\'dan: kadroda olmayan (transfer olan) ve sakat oyuncular '
               'listeye alınmaz, şüpheliler işaretlidir.' if guncel else ''))


def kart_metni(hk_bilgi, hk):
    return ('Sarı kart görme olasılığı: oyuncunun 90 dakikadaki sarı kart oranı (ligin ortalamasıyla 10 maçlık '
            'süre kadar harmanlanır) × maç başına oynadığı süre'
            + (f' × hakemin sertliği ({e(hk_bilgi["ad"])}: {hk_bilgi.get("mac") or "?"} maçta maç başına '
               f'{fmt(hk_bilgi["sariOrt"])} sarı, lig ortalaması {fmt(hk_bilgi["sariLigOrt"])} → ×{fmt(hk, 2)}; '
               f'az maç yönetmiş hakemde lig ortalamasına doğru çekilir)'
               if hk_bilgi.get('sariOrt') is not None and hk_bilgi.get('sariLigOrt') else
               ' (hakem henüz atanmadı; atanınca sertliği de hesaba katılır)') + '.')
