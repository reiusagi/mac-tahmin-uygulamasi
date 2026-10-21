"""Arayüzün ortak parçaları: sayı ve tarih biçimleri, lig grupları, takım formu, stil."""
import logging
from datetime import date, datetime
from html import escape

from ..bicim import fmt, para, sayi_kimlik, yuzde  # noqa: F401
from ..logo import logo_html, takim_logo_url
from ..sezon import LIGLER, SON_SEZON, TAKVIM_YILI, sezon_etiketi
from ..veri import hata_ozeti

logger = logging.getLogger(__name__)

UYGULAMA = 'Maç Tahmin Laboratuvarı'
AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
AY_KISA = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']
GUN_KISA = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']

LIG_GRUPLARI = [
    ('Büyük beş lig', ['EPL', 'La_liga', 'Serie_A', 'Bundesliga', 'Ligue_1']),
    ('Diğer Avrupa ligleri', ['Super_Lig', 'Eredivisie', 'Primeira_Liga', 'Pro_League', 'Premiership', 'Championship',
                              'Austria_Bundesliga', 'Swiss_Super_League', 'Greek_Super_League', 'Eliteserien']),
    ('Güney Amerika', ['Brasileirao', 'Liga_Profesional']),
    ('Asya', ['Saudi_Pro_League']),
]
KAYNAK = {
    'understat': ('Understat', 'understat.com (maç sonuçları, xG ve oyuncu istatistikleri) ve fotmob.com (mevki, yaş, canlı skor, hakem, stadyum)'),
    'fotmob': ('FotMob', 'fotmob.com (maç sonuçları, xG, oyuncu istatistikleri, canlı skor, hakem, stadyum)'),
}
FORM = {'G': ('G', 'Galibiyet'), 'B': ('B', 'Beraberlik'), 'M': ('M', 'Mağlubiyet')}


def takim_link(ad, anahtar):
    """HTML içinde tıklanınca takım sayfasını açan takım adı. anahtar: FotMob takım id'si (sayı) ya da açık ligdeki
    takım adı. Tıklamayı yakalamak için kapsayan ui.html'de takim_tiklama(öğe, G) çağrılır."""
    return f'<span class="link takim-link" data-takim="{escape(str(anahtar), quote=True)}">{escape(str(ad))}</span>'


def hata_metni(ex, ne=''):
    """Arayüzde gösterilecek kısa hata metni (yol ve istisna metni içermez); ayrıntı günlüğe yazılır."""
    logger.warning('%s', ne or 'işlem başarısız', exc_info=ex)
    return hata_ozeti(ex)


def takim_logo(tid, boyut='xsmall'):
    """FotMob takım logosu; indirilemezse boş kalır. boyut: 'xsmall' (35 px, satır içi) ya da 'small' (150 px, büyük
    gösterilen logolar bulanıklaşmasın)."""
    return logo_html(takim_logo_url(tid, boyut), bos='<span class="logo"></span>')


def takim_tiklama(oge, G):
    """oge (ui.html) içindeki takim_link'lere tıklanınca G.takim_ac çağrılır."""
    oge.on('click', lambda ev: G.takim_ac(ev.args) if ev.args else None,
           js_handler='(e) => { const t = e.target.closest("[data-takim]"); if (t) { e.stopPropagation(); emit(t.dataset.takim); } }')
    return oge


KUPA_ONEKLERI = ('avrupa-', 'kupa-', 'milli-')  # canlı skordaki lig anahtarı: kupa ve milli maçlar


def tahmin_acilabilir(m):
    """Canlı skordaki maçın tahmini açılabilir mi: canlı lig maçında hayır (lig tahmini kendi sekmesidir, açık sekme
    korunur); kupa ve milli maçların ayrıntılı tahmini pencere olarak her zaman açılır."""
    return m.get('durum') != 'canli' or (m.get('lig') or '').startswith(KUPA_ONEKLERI)


def tahmine_git(G, m):
    """Canlı skor verisindeki bir maçın tahminine geçer: uygulamanın liginde Maç tahmini sekmesinde o maç; Avrupa / yerel
    kupa ya da milli maçta ayrıntılı tahmin penceresi, açık sekme değişmeden (maç kimliği yoksa ilgili sekmeye geçilir).
    Döner: geçildiyse True."""
    from nicegui import ui
    if not tahmin_acilabilir(m):
        return False
    lig = m.get('lig') or ''
    if lig.startswith(KUPA_ONEKLERI):
        milli_mi = lig.startswith('milli-')
        kimlik = lig.split('-', 1)[1]
        if sayi_kimlik(kimlik) and m.get('id'):
            (G.milli_mac_ac if milli_mi else G.avrupa_mac_ac)(int(kimlik), m['id'])
        else:
            G.sekme_ac('milli' if milli_mi else 'avrupa')
            ui.notify('Ayrıntılı tahmin için bu sekmede maça tıkla.')
        return True
    bulunan = _lig_takimlari(G.depo.stadyumlar()['ligler'], lig, m.get('evId'), m.get('depId'))
    if not bulunan:
        ui.notify('Bu maçın takımları uygulamanın liglerinde bulunamadı.')
        return False
    G.tahmin_ac(*bulunan)
    return True


def _lig_takimlari(ligler, lig, ev_id, dep_id):
    """(lig, ev adı, deplasman adı): önce verilen lig, yoksa iki takımı birlikte içeren lig (Takımlarım ve takım
    sayfasından açılan maç kartında lig bilinmez); bulunamazsa None."""
    for anahtar in ([lig] if lig in ligler else []) + [k for k in ligler if k != lig]:
        ters = {str(v): ad for ad, v in ligler[anahtar].items()}
        ev, dep = ters.get(str(ev_id)), ters.get(str(dep_id))
        if ev and dep:
            return anahtar, ev, dep
    return None


def mac_kimlikleri_tamamla(m, veri):
    """Maç kartının maç sözlüğü, eksik takım kimlikleri kartın yüklediği ayrıntıdan (mac_ozeti.ayrinti) tamamlanmış
    kopya; özgün sözlük değişmez."""
    if not veri:
        return m
    return {**m, 'evId': m.get('evId') or (veri.get('ev') or {}).get('id'),
            'depId': m.get('depId') or (veri.get('dep') or {}).get('id')}


# renk paletleri: anahtar -> (ad, örnek renk); CSS'te body.palet-<anahtar> (açık ve koyu tema ayrı). 'saha' varsayılan.
PALETLER = {'saha': ('Saha yeşili', '#1c5b3e'), 'gece': ('Gece mavisi', '#1f3f73'), 'bordo': ('Bordo', '#7a2335'),
            'grafit': ('Grafit', '#2d3a45')}
TEMALAR = {'oto': 'Bilgisayara göre', 'acik': 'Açık', 'koyu': 'Koyu'}
# görünüm stili: 'modern' body'ye stil-modern sınıfını ekler (CSS: stil_modern.py); klasik menüden seçilebilir
STILLER = {'klasik': 'Klasik', 'modern': 'Modern'}
VARSAYILAN_STIL = 'modern'


def piyasa_kartlari(p, pz, lh, la, ev, dep):
    """Maçın olasılıkları dört kartta, her satır ad · çubuk · yüzde: maç sonucu ve çifte şans, goller, handikap (±1,5),
    ilk yarı (modeller.ilk_yari). p: [ev, beraberlik, deplasman] (ekranda gösterilen sonuç olasılıkları); pz:
    modeller.piyasalar (skor tablosundan); lh, la: maçın beklenen golleri. Her kartın en olası seçeneği vurgulu."""
    from ..modeller import ilk_yari
    iy = ilk_yari(lh, la)
    ev, dep = e(ev), e(dep)

    def kart(baslik, satirlar, en_grubu=None, alt=''):
        en = max(v for _, v, _ in satirlar[:en_grubu]) if en_grubu else None
        govde = ''
        for k, (ad, v, ipucu) in enumerate(satirlar):
            if ad == '-':
                govde += '<div class="pz-ayrac"></div>'
                continue
            vurgu = ' en' if en_grubu and k < en_grubu and v == en else ''
            govde += (f'<div class="pz-satir{vurgu}" title="{ipucu}"><span class="ad">{ad}</span>'
                      f'<span class="cubuk"><i style="width:{v * 100:.0f}%"></i></span><b>{yuzde(v)}</b></div>')
        return (f'<div class="pz-kart"><div class="pz-baslik">{baslik}</div>{govde}'
                + (f'<div class="pz-alt">{alt}</div>' if alt else '') + '</div>')
    return '<div class="pz-izgara">' + ''.join((
        kart('Maç sonucu', [(f'{ev} kazanır', p[0], ''), ('Beraberlik', p[1], ''), (f'{dep} kazanır', p[2], ''),
                            ('-', 0, ''), (f'1X · {ev} kaybetmez', pz['cs_1x'], 'Çifte şans: ev sahibi kazanır ya da berabere'),
                            (f'X2 · {dep} kaybetmez', pz['cs_x2'], 'Çifte şans: deplasman kazanır ya da berabere'),
                            ('12 · beraberlik olmaz', pz['cs_12'], 'Çifte şans: iki takımdan biri kazanır')], 3),
        kart('Goller', [('1,5 üst (2+ gol)', pz['ust15'], ''), ('2,5 üst (3+ gol)', pz['ust25'], ''),
                        ('3,5 üst (4+ gol)', pz['ust35'], ''), ('-', 0, ''), ('Karşılıklı gol', pz['kg'], 'İki takım da gol atar'),
                        (f'{ev} gol yemez', pz['ev_gol_yemez'], ''), (f'{dep} gol yemez', pz['dep_gol_yemez'], '')]),
        kart('Handikap (±1,5 gol)', [(f'{ev} −1,5', pz['ev_m15'], 'İki ve üstü farkla kazanır'),
                                     (f'{dep} +1,5', pz['dep_p15'], 'Kazanır, berabere kalır ya da tek farkla kaybeder'),
                                     ('-', 0, ''), (f'{dep} −1,5', pz['dep_m15'], 'İki ve üstü farkla kazanır'),
                                     (f'{ev} +1,5', pz['ev_p15'], 'Kazanır, berabere kalır ya da tek farkla kaybeder')],
             alt='−1,5: iki ve üstü farkla kazanır · +1,5: kaybetse bile en çok bir farkla'),
        kart('İlk yarı', [(f'{ev} önde', iy['p'][0], ''), ('Berabere', iy['p'][1], ''), (f'{dep} önde', iy['p'][2], ''),
                          ('-', 0, ''), ('İlk yarıda gol olur (0,5 üst)', iy['ust05'], ''),
                          ('İlk yarıda 2+ gol (1,5 üst)', iy['ust15'], '')], 3,
             alt=f'İlk yarıda beklenen gol {fmt(iy["lh"])} – {fmt(iy["la"])}'))) + '</div>'

def hava_html(hv, kisa=False):
    """Maç saatinin hava tahmini satırı (hava.mac_havasi'nin sonucu); şiddetli yağışta ölçülen etkinin notu. kisa: maç
    tahmini panosunun bilgi satırı için simgeli tek parça (not ve kaynak üstüne gelince)."""
    if not hv:
        return ''
    parca = [f'{round(hv["sicaklik"])}°C']
    if hv.get('durum'):
        parca.append(hv['durum'])
    if hv['yagis'] >= 0.1:
        parca.append(f'yağış {fmt(hv["yagis"], 1)} mm' + (f' (olasılık %{hv["olasilik"]})' if hv.get('olasilik') is not None else ''))
    elif (hv.get('olasilik') or 0) >= 30:
        parca.append(f'yağış olasılığı %{hv["olasilik"]}')
    if hv.get('ruzgar') is not None:
        parca.append(f'rüzgâr {round(hv["ruzgar"])} km/sa')
    from ..hava import SIDDETLI_YAGIS
    if kisa:
        ipucu = 'Maç saatinin hava tahmini (Open-Meteo)' + (
            '. Yağmurlu maçlarda geçmişte biraz daha çok gol atıldı (~%5); etkisi küçük olduğu için tahmine katılmadı.'
            if hv['yagis'] >= SIDDETLI_YAGIS else '')
        return f'<span title="{escape(ipucu, quote=True)}"><i class="material-icons">wb_cloudy</i>{e(" · ".join(parca))}</span>'
    not_ = ('<div class="faint" style="font-size:.75rem">Yağmurlu maçlarda geçmişte biraz daha çok gol atıldı (~%5); '
            'etkisi çok küçük olduğu için tahmine katılmadı.</div>' if hv['yagis'] >= SIDDETLI_YAGIS else '')
    return (f'<div class="soft">Maç saatinde hava: {e(" · ".join(parca))}'
            f'<span class="faint" style="font-size:.75rem"> · tahmin: Open-Meteo</span></div>{not_}')


def lig_bilgi(anahtar):
    return next(l for l in LIGLER if l[0] == anahtar)


def lig_secenekleri():
    """Lig seçimi: bölgelere göre sıralı {anahtar: 'Ad (Ülke)'}. LIGLER'e eklenip bir gruba yazılmamış lig sona eklenir."""
    sira = [k for _, anahtarlar in LIG_GRUPLARI for k in anahtarlar]
    sira += [l[0] for l in LIGLER if l[0] not in sira]
    return {k: f'{lig_bilgi(k)[1]} ({lig_bilgi(k)[2]})' for k in sira if any(l[0] == k for l in LIGLER)}


def sezon_secenekleri(anahtar):
    ilk = lig_bilgi(anahtar)[3]
    return {y: sezon_etiketi(y, anahtar) + (' (sürüyor)' if y == SON_SEZON else '') for y in range(SON_SEZON, ilk - 1, -1)}


def kucuk(s):
    """Türkçe küçük harf (Python'un lower()'ı 'İ'yi 'i̇' yapar)."""
    return s.replace('İ', 'i').replace('I', 'ı').lower()


_TR_ALFABE = 'abcçdefgğhıijklmnoöpqrsştuüvwxyz'


def tr_anahtar(s):
    """Türkçe alfabe sırasıyla sıralama anahtarı (Ç, Ğ, İ, Ö, Ş, Ü yerinde; yabancı aksanlı harfler (é, ñ…)
    temel harflerinin yanında)."""
    import unicodedata
    out = []
    for c in kucuk(str(s)):
        if c not in _TR_ALFABE:
            c = unicodedata.normalize('NFD', c)[0]
        out.append((_TR_ALFABE.index(c) if c in _TR_ALFABE else 100 + ord(c), c))
    return out


def ilk_kucuk(s):
    return kucuk(s[:1]) + s[1:]


def yuzde_uc(p):
    """Olasılık; uçlarda yuvarlama yanıltmasın diye '%>99' ve '%<1', hiç olmayan için '–'."""
    return '%>99' if p >= .995 else '%<1' if 0 < p < .005 else '–' if p == 0 else yuzde(p)


def sayi(n):
    return f'{n:,}'.replace(',', '.')


def e(s):
    """HTML'e yazılacak metin."""
    return escape(str(s))


def tarih_uzun(d):
    g = date.fromisoformat(d) if isinstance(d, str) else d
    return f'{g.day} {AYLAR[g.month - 1]} {g.year}'


def kisa_gun(g):
    if isinstance(g, str):
        g = date.fromisoformat(g)
    return f'{GUN_KISA[g.weekday()]} {g.day} {AY_KISA[g.month - 1]}'


def yerel(iso):
    """UTC ISO zamanı bilgisayarın saat dilimine çevirir; okunamazsa None."""
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone()
    except (AttributeError, ValueError):
        return None


def form(S, son=5):
    """Takım başına son maçların sonuçları (eskiden yeniye): 'G', 'B', 'M'."""
    out = {i: [] for i in range(len(S.T))}
    for m in S.M:
        for t, ag, yg in ((m.h, m.hg, m.ag), (m.a, m.ag, m.hg)):
            out[t].append('G' if ag > yg else 'B' if ag == yg else 'M')
    return {i: v[-son:] for i, v in out.items()}


def takvim_yili(anahtar):
    return anahtar in TAKVIM_YILI


CSS = r'''
:root{
  --bg:#edf1ec; --panel:#ffffff; --panel-2:#f4f7f3; --ink:#13221a; --soft:#5a6d61; --line:#d6ddd7;
  --pitch:#1c5b3e; --pitch-2:#2f7a57; --lamp:#c9960f; --away:#35598a; --draw:#8a9088; --bad:#b0413e;
  --board:#123524; --board-ink:#eef6f0; --board-soft:#a8c3b2; --board-line:rgba(255,255,255,.14);
  --b-home:#7fd4a2; --b-draw:#c8cec5; --b-away:#9fbff0; --b-text:#0c2217;
  --display:"Barlow Condensed","Arial Narrow",sans-serif; --body:"Barlow",system-ui,"Segoe UI",sans-serif;
  --mk-ev:#e07b24; --mk-dep:#2f6fd6;  /* maç kartında ev sahibi ve deplasmanın rengi: birbirinden ve sahadan ayrışır */
}
body.body--dark{
  --bg:#0c1712; --panel:#132119; --panel-2:#182a20; --ink:#e6eee8; --soft:#93a89b; --line:#253b2f;
  --pitch:#3f9a6c; --pitch-2:#5bb886; --lamp:#f0c43c; --away:#7fa3d6; --draw:#a3a89f; --bad:#e0716c; --board:#0f2b1e;
  --mk-ev:#f59a4a; --mk-dep:#5b9bff;
}
/* renk paletleri (Görünüm menüsü; PALETLER): body'deki palet-… sınıfı, açık ve koyu temada ayrı */
body:not(.body--dark).palet-gece{
  --bg:#eceff5; --panel-2:#f3f5fa; --ink:#131b2b; --soft:#5a6478; --line:#d5dbe7;
  --pitch:#1f3f73; --pitch-2:#2f5b9e; --lamp:#c98612; --board:#14284a; --board-soft:#a9b8d6; --q-primary:#1f3f73 !important;
}
body.body--dark.palet-gece{
  --bg:#0b1220; --panel:#121b2c; --panel-2:#172238; --ink:#e6ebf5; --soft:#94a1bb; --line:#24324c;
  --pitch:#5b8bd6; --pitch-2:#7aa5ea; --lamp:#f0c43c; --board:#0f1d36; --board-soft:#a9b8d6; --q-primary:#3f6fb8 !important;
}
body:not(.body--dark).palet-bordo{
  --bg:#f3eeee; --panel-2:#f8f3f3; --ink:#241316; --soft:#6e5a5e; --line:#e2d6d8;
  --pitch:#7a2335; --pitch-2:#9c3a4d; --lamp:#c9960f; --board:#4a1420; --board-soft:#d9b3ba; --q-primary:#7a2335 !important;
}
body.body--dark.palet-bordo{
  --bg:#170c0f; --panel:#221216; --panel-2:#2a171c; --ink:#f0e6e8; --soft:#b39aa0; --line:#3d2329;
  --pitch:#c65b70; --pitch-2:#dc7a8d; --lamp:#f0c43c; --board:#2e0f16; --board-soft:#d9b3ba; --q-primary:#a8445a !important;
}
body:not(.body--dark).palet-grafit{
  --bg:#eef0f2; --panel-2:#f5f6f8; --ink:#161b20; --soft:#5d6670; --line:#d8dce1;
  --pitch:#2d3a45; --pitch-2:#4a5d6e; --lamp:#d9922e; --board:#1e2830; --board-soft:#aeb8c2; --q-primary:#2d3a45 !important;
}
body.body--dark.palet-grafit{
  --bg:#0f1215; --panel:#171b20; --panel-2:#1d2228; --ink:#e7eaee; --soft:#9aa3ad; --line:#2b323a;
  --pitch:#8fa3b8; --pitch-2:#a9bccf; --lamp:#f0c43c; --board:#151b21; --board-soft:#aeb8c2; --q-primary:#5f7489 !important;
}
.palet-ornek{display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:6px;vertical-align:-2px;
  border:1px solid rgba(0,0,0,.15)}
body{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:15px}
.nicegui-content{padding:0;gap:0;max-width:1180px;margin:0 auto;width:100%}
h1,h2,h3,.disp{font-family:var(--display);letter-spacing:.01em}
.app-ust{padding:18px 20px 8px;gap:14px;width:100%}
.app-ust h1{font-size:1.9rem;font-weight:700;line-height:1;margin:0}
.app-ust .alt{color:var(--soft);font-size:.92rem}
.sekmeler{width:100%;border-bottom:1px solid var(--line);padding:0 12px}
.sekmeler .q-tab__label{font-family:var(--display);font-size:1.05rem;font-weight:600;letter-spacing:.02em}
.icerik{padding:16px 20px 28px;gap:16px;width:100%}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;width:100%;
  box-shadow:0 1px 2px rgba(16,40,28,.05),0 6px 18px rgba(16,40,28,.06)}
.panel h3{font-size:1.35rem;font-weight:700;margin:0 0 8px}
.lead{color:var(--soft);font-size:.92rem;line-height:1.45}
.cap{color:var(--soft);font-size:.82rem;line-height:1.4}
.num{font-variant-numeric:tabular-nums}
.board{background:var(--board);color:var(--board-ink);border-radius:14px;padding:18px 20px;width:100%;gap:12px}
.board .q-field__native,.board .q-field__label,.board .q-select__dropdown-icon{color:var(--board-ink)!important}
.board .q-field--outlined .q-field__control:before{border-color:var(--board-line)}
.board .soft{color:var(--board-soft);font-size:.9rem}
.board .faint{color:var(--board-soft);opacity:.75;font-size:.88rem}
.bar{display:flex;height:40px;border-radius:8px;overflow:hidden;width:100%;font-weight:700;color:var(--b-text)}
.bar > div{display:flex;align-items:center;justify-content:center;min-width:0;white-space:nowrap;font-size:.95rem}
.bar .h{background:var(--b-home)} .bar .d{background:var(--b-draw)} .bar .a{background:var(--b-away)}
.oran{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;width:100%;text-align:center}
.oran .k{font-size:.8rem;color:var(--board-soft)} .oran .v{font-family:var(--display);font-size:1.7rem;font-weight:700}
.oran .top .v{color:var(--lamp)}
.eg{font-family:var(--display);font-size:2.4rem;font-weight:700;line-height:1}
.serit{display:flex;gap:8px;overflow-x:auto;padding:4px 2px 10px;width:100%}
.fx{flex:0 0 auto;min-width:168px;max-width:200px;text-align:left;background:var(--panel);border:1px solid var(--line);
  border-radius:9px;padding:8px 10px;cursor:pointer;color:var(--ink);font:inherit;line-height:1.3}
.fx:hover{border-color:var(--pitch-2)} .fx.sec{border-color:var(--pitch);box-shadow:0 0 0 2px var(--pitch) inset}
.fx small{display:block;color:var(--soft);font-size:.76rem} .fx b{display:flex;justify-content:space-between;font-weight:600;font-size:.9rem}
.fx.done{opacity:.6} .fx .zaman{color:var(--pitch);font-weight:700}
.matris{display:grid;grid-template-columns:28px repeat(6,1fr);gap:3px;font-size:.85rem}
.matris span{display:flex;align-items:center;justify-content:center;height:34px;border-radius:5px}
.matris .ax{color:var(--soft);font-weight:600}
.matris .best{outline:2px solid var(--lamp);outline-offset:-2px;font-weight:700}
.matris .real{box-shadow:inset 0 0 0 2px var(--ink);opacity:.95}
.liste{display:flex;flex-direction:column;gap:6px;width:100%}
.satir{display:grid;grid-template-columns:minmax(0,1fr) 140px 48px;gap:12px;align-items:center;font-size:.92rem;width:100%}
.satir > div:first-child{min-width:0} .satir .link{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.satir small{display:block;color:var(--soft);font-size:.78rem}
.track{height:8px;background:var(--panel-2);border-radius:5px;overflow:hidden;border:1px solid var(--line)}
.track i{display:block;height:100%;background:var(--pitch-2)}
.pv{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.link{color:var(--pitch);font-weight:600;cursor:pointer;background:none;border:0;padding:0;font:inherit;text-align:left}
.link:hover{text-decoration:underline}
.q-btn.link{padding:0;min-height:0;justify-content:flex-start} .q-btn.link .q-btn__content{justify-content:flex-start}
table.tb{width:100%;border-collapse:collapse;font-size:.9rem;font-variant-numeric:tabular-nums}
table.tb th{text-align:left;color:var(--soft);font-weight:600;font-size:.8rem;border-bottom:1px solid var(--line);padding:6px 8px;white-space:nowrap}
table.tb td{border-bottom:1px solid var(--line);padding:6px 8px;white-space:nowrap}
table.tb tr.champ td:first-child{box-shadow:inset 3px 0 0 var(--lamp)} table.tb tr.cl td:first-child{box-shadow:inset 3px 0 0 var(--pitch)}
table.tb tr.rel td:first-child{box-shadow:inset 3px 0 0 var(--bad)} table.tb td.pts,table.tb td.hi{font-weight:700}
.kiyas-kartlar{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.kiyas-kart{background:var(--panel-2);border-radius:8px;padding:8px 10px;min-width:0}
.kiyas-ad{font-size:1.05rem;max-width:100%} .kiyas-ad .q-btn__content{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}
.kiyas-nokta{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
table.kiyas-tablo .sag{text-align:center} table.kiyas-tablo td{vertical-align:middle}
table.kiyas-tablo td.kiyas-iyi{font-weight:700;color:var(--pitch);background:var(--panel-2)}
table.kiyas-tablo tr.kiyas-grup td{font-family:var(--display);font-weight:700;font-size:1rem;color:var(--ink);padding-top:14px;border-bottom:2px solid var(--line)}
.kiyas-cubuk{height:4px;background:var(--panel-2);border-radius:3px;margin:4px auto 0;min-width:70px;max-width:120px;overflow:hidden;display:flex;justify-content:center}
.kiyas-cubuk i{display:block;height:100%;border-radius:3px}
table.tb tr.cur td{background:var(--panel-2);font-weight:600} table.tb tr.best-row td{background:var(--panel-2);font-weight:700}
.kaydir{overflow-x:auto;width:100%}
.form{display:inline-flex;gap:3px} .form i{font-style:normal;font-size:.7rem;font-weight:700;width:18px;height:18px;border-radius:4px;
  display:inline-flex;align-items:center;justify-content:center;color:#fff}
.form i.G{background:var(--pitch-2)} .form i.B{background:var(--draw)} .form i.M{background:var(--bad)}
.dist{display:inline-flex;gap:1px} .dist i{width:9px;height:16px;border-radius:2px;display:inline-block}
.ok{color:var(--pitch);font-weight:700} .no{color:var(--bad);font-weight:700}
.lm .st{white-space:nowrap}
.lm{display:grid;grid-template-columns:86px minmax(0,1fr) 56px minmax(0,1fr);gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:.93rem}
.lm .st{color:var(--soft);font-size:.82rem} .lm.live .st{color:var(--bad);font-weight:700}
.lm .h{text-align:right} .lm .sc{text-align:center;font-weight:700;font-family:var(--display);font-size:1.2rem}
.lm .win{font-weight:700} .lm .lv{grid-column:2 / 5;color:var(--soft);font-size:.78rem;text-align:center;margin-top:-4px}
.lm.done{opacity:.8}
/* canlı skorlar */
.gun-panel{padding:10px 14px} .gun-dugme{font-size:1.15rem;font-weight:700}
.gun-ozet{color:var(--soft);font-size:.9rem} .gun-ozet b{color:var(--ink)}
.lig-panel{padding:12px 16px 6px}
.lig-baslik{display:flex;align-items:center;gap:10px;padding-bottom:8px;border-bottom:1px solid var(--line);margin-bottom:2px}
.lig-baslik .disp{font-size:1.2rem;font-weight:700;flex:1}
.turnuva-baslik{display:flex;align-items:center;gap:10px;flex-wrap:wrap} .turnuva-baslik h3{margin:0}
.turnuva-logo{width:32px;height:32px;background-size:contain;background-repeat:no-repeat;background-position:center;flex:none}
.turnuva-logo.kucuk{width:22px;height:22px;display:block}
/* Avrupa kupaları: puan durumu, eleme ağacı, takımın yolu */
table.avrupa-tablo td .logo, table.kiyas-tablo td .logo, .agac .logo, .yol-tur .logo, .liste .logo, .mm .logo{width:18px;height:18px;vertical-align:-4px}
table.avrupa-tablo td, table.avrupa-tablo th{padding:5px 6px}
.agac{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(170px,1fr);gap:12px;min-width:min-content}
.agac-tur{display:flex;flex-direction:column;gap:6px}
.agac-kutular{display:flex;flex-direction:column;justify-content:space-around;gap:8px;flex:1}
.agac-baslik{font-family:var(--display);font-weight:700;font-size:1rem;text-align:center;color:var(--soft)}
.agac-mac{border:1px solid var(--line);border-radius:6px;padding:4px 7px;font-size:.82rem;background:var(--panel-2)}
.agac-mac .t{display:flex;align-items:center;justify-content:space-between;gap:6px;line-height:1.6}
.agac-mac .t .ad{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.agac-mac .t.kaz{font-weight:700} .agac-mac .t.kay{color:var(--soft)} .agac-mac .not{font-size:.72rem;color:var(--soft);text-align:right}
.yol-tur{padding:6px 0;border-bottom:1px solid var(--line);line-height:1.7}
.lig-logo{width:24px;height:24px;background-size:contain;background-repeat:no-repeat;background-position:center;flex:none}
.logo{width:22px;height:22px;background-size:contain;background-repeat:no-repeat;background-position:center;flex:none;display:inline-block}
.cm{display:grid;grid-template-columns:62px minmax(0,1fr) 78px minmax(0,1fr) 62px;column-gap:10px;row-gap:1px;align-items:center;
  padding:9px 6px;border-bottom:1px solid var(--line);border-radius:8px;transition:background .15s;width:100%;max-width:880px;margin:0 auto}
.cm:last-child{border-bottom:0} .cm:hover{background:var(--panel-2)}
.cm .durum{font-size:.8rem;color:var(--soft);text-align:center;line-height:1.2;font-variant-numeric:tabular-nums}
.cm .durum.canli{color:var(--bad);font-weight:700;display:inline-flex;align-items:center;justify-content:center;gap:4px}
.cm .durum.bitti{font-weight:700;color:var(--ink);background:var(--panel-2);border-radius:5px;padding:2px 0}
.cm .durum.iptal{color:var(--bad)}
.cm .takim{display:flex;align-items:center;gap:8px;min-width:0;font-size:.95rem}
.cm .takim.ev{justify-content:flex-end;text-align:right} .cm .takim.kaz{font-weight:700}
.cm.bitti .takim:not(.kaz){color:var(--soft)}
.cm .skor{justify-self:center;font-family:var(--display);font-size:1.35rem;font-weight:700;background:var(--panel-2);
  border-radius:7px;padding:1px 10px;min-width:64px;text-align:center;font-variant-numeric:tabular-nums}
.cm .skor i{font-style:normal;margin:0 4px;color:var(--soft)} .cm .skor.canli{background:var(--bad);color:#fff}
.cm .skor.canli i{color:#fff}
.cm .skor.saat{background:transparent;border:1px solid var(--line);color:var(--pitch);font-size:1.05rem;padding:3px 8px}
.cm .alt{grid-column:2 / 5;text-align:center;color:var(--soft);font-size:.76rem}
.cm .cm-olas{grid-column:2 / 5;display:flex;justify-content:center;align-items:center;gap:8px;flex-wrap:wrap;margin-top:3px}
.cm .cm-olas .olas span{font-size:.72rem;padding:1px 6px}
.cm.canli{background:color-mix(in srgb,var(--bad) 6%,transparent)}
.nabiz{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--bad);animation:nabiz 1.4s infinite}
@keyframes nabiz{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--bad) 60%,transparent)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
.canli-rozet{display:inline-flex;align-items:center;gap:5px;color:var(--bad);font-weight:700;font-size:.82rem}
.canli-yazi{color:var(--bad);font-weight:700;display:inline-flex;align-items:center;gap:5px}
@media (max-width:600px){.cm{grid-template-columns:46px minmax(0,1fr) 64px minmax(0,1fr) 0;column-gap:6px}.cm .takim{font-size:.85rem}
  .cm .logo{display:none}}
.cm{cursor:pointer}
/* maç kartı */
.mk-ust{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;padding:6px 0 4px}
.mk-takim{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center;font-size:1.05rem}
/* takım sayfası */
.takim-link{cursor:pointer} .takim-link:hover{text-decoration:underline}
td.takim-hucre{white-space:nowrap} td.takim-hucre .logo{width:20px;height:20px;vertical-align:-5px;margin-right:7px}
.tk-baslik{display:flex;gap:14px;align-items:center} .tk-logo{width:64px;height:64px;flex:none;background-size:contain;background-repeat:no-repeat;background-position:center}
.tk-mac{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) 26px;column-gap:8px;align-items:center;padding:5px 4px;
  border-bottom:1px solid var(--line);cursor:pointer;font-size:.88rem} .tk-mac:hover{background:var(--panel-2)}
.tk-mac .tk-ust{grid-column:1 / 5;font-size:.72rem;color:var(--soft)}
.tk-mac .tk-ev{text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap} .tk-mac .tk-dep{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tk-mac .b{font-weight:700} .tk-mac .tk-orta{text-align:center;min-width:56px} .tk-mac .logo{width:16px;height:16px;vertical-align:-3px}
.tk-oyuncu{display:flex;justify-content:space-between;gap:8px;padding:3px 0;border-bottom:1px solid var(--line);font-size:.88rem}
.tk-grup{font-family:var(--display);font-weight:700;margin-top:8px} .tk-no{display:inline-block;min-width:22px;color:var(--soft)}
.sakat-isaret{color:var(--bad);font-weight:700}
.hm-mac{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);column-gap:10px;align-items:center;padding:5px 4px;
  border-bottom:1px solid var(--line);cursor:pointer;font-size:.88rem} .hm-mac:hover{background:var(--panel-2)}
.hm-mac > .cap{grid-column:1 / 4} .hm-ev{text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hm-dep{overflow:hidden;text-overflow:ellipsis;white-space:nowrap} .hm-mac .logo{width:16px;height:16px;vertical-align:-3px}
.tl-kart{background:var(--panel-2);border-radius:10px;padding:10px 12px;min-width:0}
.tl-mac{display:grid;grid-template-columns:1fr auto;column-gap:8px;padding:4px 0;border-bottom:1px solid var(--line);cursor:pointer;font-size:.88rem}
.tl-mac > span:first-child{grid-column:1 / 3} .tl-mac:hover{background:var(--panel)} .tl-mac .logo{width:16px;height:16px;vertical-align:-3px}
.tl-canli{padding:6px 8px;margin-bottom:6px;border-radius:8px;background:color-mix(in srgb,var(--bad) 10%,transparent)}
.tl-canli .logo{width:18px;height:18px;vertical-align:-4px}
.kariyer-ozet{background:var(--panel-2);border-radius:8px;padding:8px 10px;margin-bottom:8px;font-size:.9rem}
.kariyer-ozet .kilometre{margin-top:4px;font-weight:600;color:var(--pitch)}
table.kariyer-tablo tr.kr-grup td{font-family:var(--display);font-weight:700;font-size:1rem;padding-top:12px;border-bottom:2px solid var(--line)}
table.kariyer-tablo tr.kr-sezon td{font-weight:600;border-top:1px solid var(--line)} table.kariyer-tablo .logo{width:16px;height:16px;vertical-align:-3px}
table.kariyer-tablo tr.kr-kulvar td{font-size:.82rem;color:var(--soft);border-bottom:0;padding-top:2px;padding-bottom:2px}
table.kariyer-tablo tr.kr-kulvar td:nth-child(2){padding-left:28px}
/* maç tahmini: seçim kutusunda, şeritte ve golcü başlıklarında takım logoları */
.secim-logo{width:24px;height:24px;display:block}
.secim-liste{max-height:420px !important}
/* maç tahmini: seçili takım adı ve açılan listedeki adlar ortada */
.secim-satiri .q-field__native, .secim-satiri .q-field__native > span{justify-content:center;text-align:center;width:100%}
.secim-satiri .q-field__label{left:0 !important;right:0;width:100%;max-width:100% !important;text-align:center;transform-origin:center top !important}
.secim-liste .q-item{justify-content:center;text-align:center} .secim-liste .q-item__section{align-items:center}
.secim-satiri{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:10px}
.logo-dugme{cursor:pointer;border-radius:50%;padding:2px;transition:background .15s} .logo-dugme:hover{background:rgba(255,255,255,.15)}
.fx b .logo{width:16px;height:16px;vertical-align:-3px;margin-right:4px}
.tahmin-takim{display:inline-flex;align-items:center;gap:8px} .tahmin-takim .logo{width:26px;height:26px}
/* maç kartı: oyuncunun maçtaki performansı */
.perf-izgara{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}
.perf-grup{background:var(--panel-2);border-radius:8px;padding:8px 10px}
.perf-baslik{font-family:var(--display);font-weight:700;font-size:1rem;margin-bottom:4px}
.perf-satir{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px solid var(--line);font-size:.88rem}
.perf-satir:last-child{border-bottom:0} .perf-satir b{font-variant-numeric:tabular-nums;white-space:nowrap}
.perf-puan{margin-left:auto;font-family:var(--display);font-weight:700;font-size:1.6rem;padding:2px 10px;border-radius:8px;background:#888;color:#fff}
.perf-puan.iyi{background:#1f9d55} .perf-puan.kotu{background:#d9534f}
.lider-izgara{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.lider-kutu{background:var(--panel-2);border-radius:8px;padding:8px 10px}
.lider{display:grid;grid-template-columns:18px minmax(0,1fr) auto auto;gap:6px;align-items:baseline;padding:3px 0;font-size:.9rem}
.lider .sira{color:var(--soft);font-size:.8rem} .lider .ad{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.krallik{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:16px 20px}
.krallik.genis{grid-template-columns:repeat(auto-fit,minmax(min(100%,620px),1fr))}  /* 6 sütunlu krallık tabloları */
.krallik>div{min-width:0;overflow-x:auto}  /* geniş tablo komşu listenin üstüne taşmasın, kendi içinde kaysın */
table.krallik-tablo td .logo{width:18px;height:18px;vertical-align:-4px;margin-right:5px}
.oy.tiklanir{cursor:pointer} .oy.tiklanir:hover .isim{text-decoration:underline}
.mk-takim{cursor:pointer}
.mk-logo{width:52px;height:52px;background-size:contain;background-repeat:no-repeat;background-position:center}
.mk-orta{display:flex;flex-direction:column;align-items:center;gap:4px}
.mk-skor{font-family:var(--display);font-size:2.4rem;font-weight:700;line-height:1;padding:4px 16px;border-radius:10px;background:var(--panel-2)}
.mk-skor.canli{background:var(--bad);color:#fff}
.mk-orta .durum{font-size:.85rem;color:var(--soft);display:inline-flex;align-items:center;gap:5px}
.mk-orta .durum.canli{color:var(--bad);font-weight:700}
.olay{display:grid;grid-template-columns:52px 26px minmax(0,1fr);align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid var(--line);
  font-size:.92rem;width:60%}
.olay.dep{margin-left:40%;grid-template-columns:minmax(0,1fr) 26px 52px;text-align:right}
.olay.dep .olay-dk{order:3} .olay.dep .olay-simge{order:2} .olay.dep .olay-metin{order:1}
.olay-dk{font-weight:700;color:var(--soft);font-variant-numeric:tabular-nums} .olay-simge{text-align:center}
.olay-ayrac{text-align:center;color:var(--soft);font-size:.8rem;padding:6px 0;border-bottom:1px solid var(--line);font-weight:600}
.olay-skor{display:inline-block;background:var(--panel-2);border-radius:5px;padding:0 6px;font-weight:700;margin-left:4px}
.kart{display:inline-block;width:11px;height:15px;border-radius:2px;vertical-align:middle} .kart.sari{background:#f2c418} .kart.kirmizi{background:#d33}
.degis{color:var(--pitch);font-weight:700} .giren{color:var(--pitch-2)} .cikan{color:var(--bad)}
.ist{display:grid;grid-template-columns:70px minmax(0,1fr) 70px;row-gap:3px;padding:6px 0;font-size:.9rem}
.ist .d{font-weight:600;font-variant-numeric:tabular-nums} .ist .d:last-of-type{text-align:right} .ist .d.onde{font-weight:800} .ist .d.onde.ev{color:var(--mk-ev)} .ist .d.onde.dep{color:var(--mk-dep)}
.ist .ad{text-align:center;color:var(--soft)}
.ist-cubuk{grid-column:1 / 4;display:flex;gap:4px;height:6px} .ist-cubuk i{display:block;border-radius:3px}
.ist-cubuk .e{background:var(--mk-ev)} .ist-cubuk .a{background:var(--mk-dep)} .ist-cubuk.bos i{background:var(--line)}
.ist-lejant{display:flex;justify-content:space-between;font-weight:700;font-size:.85rem;margin-bottom:4px}
.ist-lejant .ev{color:var(--mk-ev)} .ist-lejant .dep{color:var(--mk-dep)}
.ist-lejant i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 6px;vertical-align:middle}
.ist-grup{font-family:var(--display);font-weight:700;font-size:1.05rem;margin:12px 0 2px;border-bottom:1px solid var(--line)}
.saha{position:relative;width:100%;max-width:520px;margin:6px auto;aspect-ratio:68/105;background:linear-gradient(#2f7a57,#2a7050);
  border-radius:10px;overflow:hidden;border:2px solid #24603f}
.saha-cizgi{position:absolute;border:2px solid rgba(255,255,255,.35)}
.saha-cizgi.orta{left:0;right:0;top:50%;height:0;border-width:2px 0 0}
.saha-cizgi.yuvarlak{left:50%;top:50%;width:22%;aspect-ratio:1;border-radius:50%;transform:translate(-50%,-50%)}
.saha-cizgi.ceza{left:22%;right:22%;height:15%} .saha-cizgi.ceza-ust{top:-2px;border-top:0} .saha-cizgi.ceza-alt{bottom:-2px;border-bottom:0}
.oy{position:absolute;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;gap:2px;width:80px}
.forma{position:relative;width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-weight:700;font-size:.8rem;color:#fff;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.oy.ev .forma{background:var(--mk-ev)} .oy.dep .forma{background:var(--mk-dep)}
.oy .isim{color:#fff;font-size:.72rem;font-weight:600;text-shadow:0 1px 2px rgba(0,0,0,.7);text-align:center;line-height:1.1;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:80px}
.puan{position:absolute;top:-8px;right:-14px;font-size:.62rem;padding:0 3px;border-radius:4px;background:#888;color:#fff}
.puan.iyi{background:#1f9d55} .puan.kotu{background:#d9534f}
/* oyuncunun maçtaki olayları: formanın sol üstünde (sahada), adının yanında (yedeklerde) */
.forma .isaretler{position:absolute;top:-12px;right:calc(100% - 6px);display:flex;gap:0;flex-direction:row-reverse}
.forma .isaretler i{font-size:.95rem} .forma .isaretler i.is-kart{width:8px;height:12px}
.isaretler{display:inline-flex;align-items:center;gap:1px;margin-left:3px;vertical-align:middle}
.isaretler i{font-style:normal;font-size:.78rem;line-height:1;filter:drop-shadow(0 1px 1px rgba(0,0,0,.5))}
.isaretler i.kk{filter:drop-shadow(0 0 2px #d9534f) drop-shadow(0 0 1px #d9534f)}
.isaretler i.is-kart{width:7px;height:10px;border-radius:1px;display:inline-block;border:1px solid rgba(0,0,0,.3)}
.isaretler i.is-kart.sari{background:#f5c518} .isaretler i.is-kart.kirmizi{background:#d9534f}
.kadro-alt{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px} .kadro-bilgi{font-size:.9rem}
@media (max-width:600px){.olay,.olay.dep{width:100%;margin-left:0}.kadro-alt{grid-template-columns:1fr}.oy .isim{font-size:.62rem;max-width:60px}}
/* milli maç satırı: üstte tarih/grup, altında ev · orta · deplasman */
.mm{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);column-gap:12px;row-gap:2px;align-items:center;
  padding:8px 0;border-bottom:1px solid var(--line);font-size:.93rem;width:100%}
.mm .st{grid-column:1 / -1;color:var(--soft);font-size:.78rem}
.mm .h{text-align:right;font-weight:600} .mm .a{text-align:left;font-weight:600} .mm .orta{text-align:center;min-width:56px}
.mm.done{opacity:.85}
.olas{display:inline-flex;gap:4px}
.olas span{padding:2px 7px;border-radius:6px;font-weight:700;font-size:.8rem;font-variant-numeric:tabular-nums;white-space:nowrap}
.olas .kaz{background:var(--pitch-2);color:#fff} .olas .kay{background:var(--bad);color:#fff}
.olas .ber{background:#dfe3de;color:#3d4a42} body.body--dark .olas .ber{background:#3a4a40;color:#dfe7e1}
.rol{background:var(--panel-2);border:1px solid var(--line);border-radius:9px;padding:12px;cursor:pointer}
.rol.sec{border-color:var(--pitch);box-shadow:0 0 0 2px var(--pitch) inset}
.kiyas-ozet p{margin:0 0 8px;line-height:1.55}
/* bildirim sesi yükleme kutusu: Quasar'ın "0.0B / 0.00%" satırı ve boş dosya listesi gizli (dosya hemen yüklenir) */
.ses-yukle .q-uploader__subtitle,.ses-yukle .q-uploader__list{display:none}
/* kulüp Elo'sunun az tanıdığı takımlar (avrupa.KulupElo.belirsizlik) */
.belirsiz{color:var(--lamp);font-weight:600;cursor:help}
.belirsiz-kutu{background:color-mix(in srgb,var(--lamp) 14%,transparent);border-left:3px solid var(--lamp);border-radius:6px;
  padding:8px 12px;font-size:.88rem;line-height:1.45;margin:8px 0}
/* maç tahmini: olasılık kartları (piyasa_kartlari), panodaki özet çipleri ve maç bilgisi satırı */
.pz-izgara{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;width:100%}
.pz-kart{background:var(--panel-2);border-radius:10px;padding:10px 12px}
.pz-baslik{font-family:var(--display);font-weight:700;font-size:1.05rem;margin-bottom:6px}
.pz-satir{display:grid;grid-template-columns:minmax(0,1fr) 64px 42px;align-items:center;gap:8px;font-size:.86rem;padding:3px 0}
.pz-satir .ad{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pz-satir .cubuk{height:6px;border-radius:3px;background:var(--line);overflow:hidden;display:block}
.pz-satir .cubuk i{display:block;height:100%;background:var(--pitch-2);border-radius:3px}
.pz-satir b{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.pz-satir.en .ad,.pz-satir.en b{color:var(--pitch);font-weight:700} .pz-satir.en .cubuk i{background:var(--pitch)}
.pz-ayrac{border-top:1px dashed var(--line);margin:5px 0} .pz-alt{color:var(--soft);font-size:.75rem;margin-top:6px}
.matris-eksen{display:grid;grid-template-columns:26px 1fr;font-size:.78rem;color:var(--soft);font-weight:600;text-align:center;margin-bottom:2px}
.matris-sar{display:flex;align-items:stretch;gap:6px} .matris-sar .matris{flex:1}
.matris-dikey{writing-mode:vertical-rl;transform:rotate(180deg);font-size:.78rem;color:var(--soft);font-weight:600;text-align:center}
.ozet-cumle{text-align:center;color:var(--board-ink);font-size:1.05rem;line-height:1.45;margin:2px 0 12px}
.ozet-cipler{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:12px}
.ozet-cip{background:rgba(255,255,255,.07);border:1px solid var(--board-line);border-radius:999px;padding:3px 12px;
  font-size:.86rem;color:var(--board-soft)} .ozet-cip b{color:var(--board-ink)}
.mac-bilgi{display:flex;flex-wrap:wrap;justify-content:center;gap:4px 18px;color:var(--board-soft);font-size:.85rem;
  margin-top:12px;padding-top:10px;border-top:1px solid var(--board-line)}
.mac-bilgi span{display:inline-flex;align-items:center;gap:5px} .mac-bilgi .material-icons{font-size:16px;opacity:.75}
.board .q-expansion-item{color:var(--board-soft);font-size:.85rem} .board .q-expansion-item .q-item{min-height:30px;padding:2px 8px}
.ozel-rol{display:inline-block;font-size:.75rem;font-weight:700;padding:1px 8px;margin:4px 4px 0 0;border-radius:999px;
  background:color-mix(in srgb,var(--lamp) 22%,transparent);color:var(--ink);border:1px solid color-mix(in srgb,var(--lamp) 60%,transparent);
  cursor:help}
/* ayrıntılı maç tahmini penceresi (kupa ve milli maçlar) */
.mt-ust{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;margin-bottom:8px}
.mt-takim{display:flex;align-items:center;gap:6px;font-family:var(--display);font-size:1.25rem;font-weight:700}
.mt-takim.sag{justify-content:flex-end}
.mt-eg{display:flex;flex-direction:column;align-items:center}
.mt-oran{grid-template-columns:repeat(3,1fr);margin-top:8px}
.mt-top .num{color:var(--pitch-2)}
.mt-h{font-family:var(--display);font-size:1.15rem;font-weight:700;margin:14px 0 6px}
.mt-iki{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;align-items:start}
.mm.secilebilir{cursor:pointer} .mm.secilebilir:hover{background:var(--panel-2)}
/* scout sekmesi: mevki grubu kartları */
.sc-izgara{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.sc-grup{background:var(--panel-2);border:1px solid var(--line);border-radius:9px;padding:10px 12px}
.sc-baslik{font-family:var(--display);font-size:1.15rem;font-weight:700;color:var(--pitch);margin-bottom:4px}
.sc-oyuncu{padding:8px 0;border-top:1px solid var(--line)}
.sc-baslik + .sc-oyuncu{border-top:none}
.sc-ust{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.sc-ad{font-weight:700;cursor:pointer}
.sc-endeks{font-family:var(--display);font-size:1.3rem;font-weight:700;color:var(--pitch-2)}
.sc-alt{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;font-size:.9rem;margin-top:2px}
.sc-bar{height:4px;background:var(--line);border-radius:2px;margin:5px 0 3px;overflow:hidden}
.sc-bar i{display:block;height:100%;background:var(--pitch-2)}
.ih-kutu{display:grid;grid-template-columns:minmax(260px,1fr) minmax(300px,1.3fr);gap:18px;padding:12px;margin:6px 0 10px;
  background:var(--panel-2);border:1px solid var(--line);border-radius:9px}
@media (max-width:760px){.ih-kutu{grid-template-columns:1fr}}
.sans-izgara{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;width:100%;margin-bottom:6px}
.sans-kutu{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel-2)}
.sans-satir{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px;padding:5px 0;border-bottom:1px solid var(--line)}
.sans-satir:last-child{border-bottom:0} .sans-satir .cap{grid-column:1 / -1}
.fk-cip{display:inline-block;padding:1px 6px;margin:1px 2px;border-radius:6px;font-size:.75rem;font-weight:700;color:#fff}
.fk-cip small{font-weight:400;opacity:.85} .fk-cip.k{background:var(--pitch-2)} .fk-cip.o{background:var(--lamp)}
.fk-cip.z{background:var(--bad)}
.dg-izgara{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;width:100%;margin-top:6px}
.dg-kart{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--panel-2)}
.dg-sayi{font-family:var(--display);font-size:1.9rem;font-weight:700;line-height:1.1;color:var(--pitch-2)}
.dg-cumle{font-weight:600;margin:2px 0 6px}
.ih-satir{display:flex;align-items:center;gap:8px;margin:5px 0} .ih-satir > span:first-child{width:80px;font-weight:600}
.sc-zorluk{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:baseline;margin-top:3px}
.sc-z{font-size:.75rem;font-weight:700;padding:1px 7px;border-radius:999px;color:#fff;white-space:nowrap}
.sc-z.kolay{background:var(--pitch-2)} .sc-z.orta{background:var(--lamp);color:#2a2005}
.sc-z.zor{background:#d9822b} .sc-z.cokzor{background:var(--bad)}
.rol .ad{font-family:var(--display);font-size:1.15rem;font-weight:700}
.chip{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1px 8px;font-size:.76rem;margin:2px 4px 2px 0}
.tiles{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;width:100%}
.tile{background:var(--panel-2);border-radius:8px;padding:8px;text-align:center}
.tile .num{font-family:var(--display);font-size:1.5rem;font-weight:700;display:block} .tile small{color:var(--soft);font-size:.75rem}
.kv{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 16px;font-size:.9rem;width:100%}
.kv dt{color:var(--soft)} .kv dd{margin:0;text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
.pctrow{display:grid;grid-template-columns:minmax(0,1.2fr) 1fr 36px;gap:10px;align-items:center;font-size:.9rem}
.pctrow small{color:var(--soft)}
.q-table th{font-weight:600;color:var(--soft)} .q-table tbody td{font-variant-numeric:tabular-nums}
.oyuncu-tablo tbody tr{cursor:pointer}
.oyuncu-tablo td.sar{white-space:normal;min-width:90px;max-width:200px;line-height:1.25}
.oyuncu-tablo .q-table th,.oyuncu-tablo .q-table td{padding-left:6px;padding-right:6px}
.q-dialog .q-card > *{flex-shrink:0}  /* uzun kartta bölümler ezilmesin, kart kaysın */
.alt-bilgi{color:var(--soft);font-size:.8rem;padding:6px 20px 24px;width:100%}
@media (max-width:700px){.tiles{grid-template-columns:repeat(3,1fr)} .icerik{padding:12px} .app-ust{padding:12px}}
'''
