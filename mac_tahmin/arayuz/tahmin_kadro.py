"""Maç tahmini sekmesinin oyuncu listeleri ve kadro düzeltmesi (arayüz öğesine dokunmaz): golcü / asist / kart olasılık
listeleri, güncel kadroya göre süzme, eksik oyuncuların etkisi, kesin ve tahmini ilk 11'ler. Sekme: tahmin.py."""
import logging
import time

from nicegui import run

from .. import oyuncu_tahmin
from .. import takim as takim_veri
from ..mac_ozeti import ayrinti
from ..modeller import sonuc_olasiliklari
from ..sezon import DC_RHO
from .ortak import e, fmt, takim_logo, yuzde
from .takim_karti import _saha

logger = logging.getLogger(__name__)

MAC_KADRO_SN = 900  # maçın FotMob kadrosu (tahmini ya da kesin) bu kadar saniyede bir yeniden bakılır
ILK11_NOT = ('Kaynak sırası: açıklanmış kesin ilk 11 (maçtan ~1 saat önce), yoksa FotMob\'un tahmini (önümüzdeki '
             'birkaç günün maçlarında), o da yoksa uygulamanın tahmini: bu sezon oynamış ve sakat olmayan oyunculardan, '
             'FotMob puanı ve süre payına göre, takımın son maçtaki dizilişinde. ✚: şüpheli. Oyuncuya tıklayınca '
             'kartı açılır.')


def _onceki(depo, S, tur):
    """Oyuncuların önceki iki sezonu (sezonda bir kez hesaplanır; kariyer dizini uygulama açılırken hazırlanır)."""
    return oyuncu_tahmin.onceki_sezonlar(S, depo.veri_klasoru, tur)


def golcu_listesi(depo, S, i, lam, hk):
    return S.golculer(i, lam, adet=None, onceki=_onceki(depo, S, 'gol'))


def asist_listesi(depo, S, i, lam, hk):
    return oyuncu_tahmin.asistciler(S, i, lam, onceki=_onceki(depo, S, 'asist'))


def kart_listesi(depo, S, i, lam, hk):
    return oyuncu_tahmin.kartcilar(S, i, hk)


def alt_golcu(p):
    return f'{p["g"]} gol · {p["a"]} asist · {fmt(p["xg"], 1)} xG'


def alt_asist(p):
    return f'{p["a"]} asist · {fmt(p["xa"], 1)} xA' + (f' · {p["kp"]} kilit pas' if p.get('kp') is not None else '')


def alt_kart(p):
    return f'{p["yc"] or 0} sarı · {p["rc"] or 0} kırmızı · {p["mp"]} maç'


def eksik_etkisi(depo, S, i, kadro, ilk11=False):
    """Takımın bu sezonki gol üretiminden eksik oyuncuların payı ve beklenen gol çarpanı. Oyuncunun katkısı: tahmini
    gol + xG oranı (önceki sezonlarla ve mevkinin ortalamasıyla harmanlanmış, oyuncu_tahmin.oran) × oynadığı süre;
    sezon başında birkaç golle payı şişmez. Eksik: güncel kadroda olmayan (ayrılan) ya da sakat oyuncu (tam), şüpheli
    (yarım). Yerine oynayan açığın yarısını kapatır sayılır; çarpan en az 0,7. ilk11=True: kadro açıklanan maç
    kadrosudur (kesin_ilk11); maç kadrosunda olmayan tam, yedekte olan yarım eksik sayılır."""
    if not kadro:
        return 1.0, []
    oyuncular = [p for p in S.PLY if S.T[i] in p['t'].split(' / ') and p['min'] > 0]
    onceki = _onceki(depo, S, 'gol')
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


def _eksik_liste(S, h, t, ad, f, eksik):
    if not eksik:
        return f'<b>{e(ad)}</b>: eksik yok'
    lam = t['lh' if ad == S.T[h] else 'la']
    etki = (f'beklenen gol {fmt(lam)} → {fmt(lam * f)}' if abs(lam * f - lam) >= 0.01
            else 'gol katkıları küçük, tahmine etkisi yok')
    return (f'<b>{e(ad)}</b> ({etki}): ' + ', '.join(
        f'{e(n)} <span class="faint">({d}' + (f', gol payı %{round(s * 100)}' if s >= 0.01 else '') + ')</span>'
        for n, d, s in eksik[:4]) + (f' <span class="faint">ve {len(eksik) - 4} oyuncu daha</span>' if len(eksik) > 4 else ''))


def eksik_html(S, h, a, t, etkiler, ilk11):
    (fh, eh), (fa, ea) = etkiler
    if fh > 0.995 and fa > 0.995:
        return ('<div class="soft" style="margin-top:8px;text-align:center">'
                + ('İlk 11\'ler açıklandı: gol katkısı olan oyuncuların hepsi ilk 11\'de.' if ilk11 else
                   'Güncel kadro denetlendi: gol katkısı olan eksik oyuncu yok.') + '</div>')
    # eksiklerin etkisi, modelin (Poisson + Elo harmanı) olasılıklarına göreli değişiklik olarak uygulanır
    once, _ = sonuc_olasiliklari(t['lh'], t['la'], DC_RHO)
    sonra, _ = sonuc_olasiliklari(t['lh'] * fh, t['la'] * fa, DC_RHO)
    p = [t['p'][k] * sonra[k] / once[k] if once[k] else t['p'][k] for k in range(3)]
    p = [x / sum(p) for x in p]
    return (
        '<div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--board-line)">'
        f'<div class="soft" style="text-align:center"><b>{"Açıklanan ilk 11&#39;lere göre" if ilk11 else "Eksik oyuncularla"}</b>: '
        f'{e(S.T[h])} {yuzde(p[0])} · beraberlik {yuzde(p[1])} · {e(S.T[a])} {yuzde(p[2])}</div>'
        f'<div class="soft" style="font-size:.82rem;margin-top:4px;line-height:1.5">{_eksik_liste(S, h, t, S.T[h], fh, eh)}<br>'
        f'{_eksik_liste(S, h, t, S.T[a], fa, ea)}</div></div>')


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


def kesin_ilk11(k, h, a):
    """Açıklanmış kesin ilk 11'ler (kadro türü 'standard'): {takım indeksi: [{'id', 'ad', 'sakat', 'ilk11'}]} (yedekler
    'şüpheli' gibi yarım eksik sayılır) ya da None."""
    if not k or k.get('tur') != 'standard' or not (k.get('ev') or {}).get('ilk11') or not (k.get('dep') or {}).get('ilk11'):
        return None

    def liste(tk):
        return ([{'id': p['id'], 'ad': p['ad'], 'sakat': None, 'ilk11': True} for p in tk['ilk11']]
                + [{'id': p['id'], 'ad': p['ad'], 'sakat': 'Doubtful', 'ilk11': False} for p in tk.get('yedek') or []])
    return {h: liste(k['ev']), a: liste(k['dep'])}


def ilk11_html(depo, S, i, k, taraf, sayfalar):
    """Bir takımın tahmini ilk 11'i: açıklanmış kesin kadro > FotMob'un tahmini > uygulamanın "en güçlü 11"i (bu sezon
    oynamış, sakat olmayanlar; puan ve süreye göre, takımın son dizilişinde)."""
    tid = depo.takim_kimligi(S.lig, S.T[i])
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
        return (f'<div class="disp" style="font-weight:700">{takim_logo(tid)}{e(S.T[i])}</div>'
                '<p class="cap">Bu takım için ilk 11 tahmini yapılamadı.</p>')
    return (f'<div class="disp" style="font-weight:700;font-size:1.05rem">{takim_logo(tid)}{e(S.T[i])}'
            f'<span class="cap" style="font-weight:400"> · {e(dizilis)} · {e(kaynak)}</span></div>'
            + _saha(oyuncular))


async def mac_kadrosu(depo, durum, S, h, a):
    """Maçın FotMob kadrosu (yalnızca canlı skor listesindeki, yani önümüzdeki birkaç gündeki maçlar): mac_ozeti
    kadro biçimi {'tur', 'ev', 'dep'} ya da None. tur: 'standard' açıklanmış kesin kadro (kalıcı saklanır),
    'predicted' FotMob'un tahmini, 'lastStarting11' önceki maçın 11'i (bu ikisi MAC_KADRO_SN boyunca saklanır)."""
    fm = depo.canli_mac(S, h, a)
    if not fm or fm.get('durum', 'baslamadi') != 'baslamadi':
        return None
    onbellek = durum.setdefault('mac_kadro', {})
    eski = onbellek.get(fm['id'])
    if eski and (eski[1].get('tur') == 'standard' or time.time() - eski[0] < MAC_KADRO_SN):
        return eski[1]
    try:
        ay = await run.io_bound(ayrinti, fm['id'], depo.g.ham)
    except Exception:
        logger.debug('maç kadrosu alınamadı: %s', fm['id'], exc_info=True)
        return eski[1] if eski else None
    k = ay.get('kadro')
    if k:
        onbellek[fm['id']] = (time.time(), k)
    return k


async def kadro_topla(depo, S, h, a, ilk11):
    """İki takımın güncel kadrosu (FotMob takım sayfası, bir saat önbellekte): (kadrolar, etkiler, notlar, sayfalar)."""
    kadrolar, etkiler, notlar, sayfalar = {}, [], {}, {}
    for i in (h, a):
        tid = depo.takim_kimligi(S.lig, S.T[i])
        if tid is not None:
            try:
                sayfalar[i] = await run.io_bound(takim_veri.takim_sayfasi, tid, depo.g.ham)
            except Exception:
                logger.debug('takım sayfası alınamadı: %s', tid, exc_info=True)
        if ilk11:
            kadrolar[i], notlar[i] = ilk11[i], 'İlk 11 açıklandı: liste kesin kadroya göre (yalnızca ilk 11\'dekiler).'
            etkiler.append(eksik_etkisi(depo, S, i, ilk11[i], ilk11=True))
        elif i in sayfalar:
            kadrolar[i], notlar[i] = sayfalar[i]['kadro'], ''
            etkiler.append(eksik_etkisi(depo, S, i, sayfalar[i]['kadro']))
        else:
            kadrolar[i] = None
            notlar[i] = '' if tid is None else 'Güncel kadro alınamadı; sezon verisine göre.'
            etkiler.append((1.0, []))
    return kadrolar, etkiler, notlar, sayfalar
