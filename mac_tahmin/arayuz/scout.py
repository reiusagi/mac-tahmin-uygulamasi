"""Scout sekmesi: mevki mevki oyuncu önerileri (varsayılan: 23 yaş altı). Açık ligde ya da uygulamadaki bütün liglerde,
süren sezon. Sıralama: performans endeksi (oyuncunun mevkidaşlarına göre yüzdelik dilimlerinin ortalaması) ya da
fiyat-performans (endeks ile piyasa değerinin ligdeki sırası arasındaki fark). Piyasa değeri FotMob'un; endeks ve F/P
uygulamanın hesabı (oyuncu_tahmin.py)."""
from datetime import date
import logging

from nicegui import run, ui

from .. import lig_maclari, oyuncu_tahmin
from ..sezon import DETAY, LIG_ADI, LIGLER, SON_SEZON, mevki_adi
from ..ulkeler import turkce
from . import disa_aktar
from .ortak import e, para, takim_link, takim_logo, takim_tiklama

logger = logging.getLogger(__name__)

ID, AD = 'scout', 'Scout'
TEMBEL = True  # piyasa değerleri takım sayfalarından: yalnızca sekme açıkken
LIG_ULKE = {l[0]: f'{l[1]} ({l[2]})' for l in LIGLER}  # aynı adlı ligler (Bundesliga) ayrışsın
YAS_SECENEK = {'U21': '21 yaş altı', 'U23': '23 yaş altı', '': 'Her yaş', '23-29': '23–29', '30+': '30 ve üstü'}
DEGER_SINIRI = {'': 'Her değer', 1e6: '1 M€ altı', 5e6: '5 M€ altı', 10e6: '10 M€ altı', 25e6: '25 M€ altı'}
ZORLUK_SECENEK = {'': 'Her zorluk', 'cok': '"Çok zor" olanlar hariç', 'kolay': 'Yalnızca kolay ve orta'}
ZORLUK_SINIF = {'Kolay': 'kolay', 'Orta': 'orta', 'Zor': 'zor', 'Çok zor': 'cokzor'}
UYRUK_SECENEK = {'': 'Yerli ve yabancı', 'yerli': 'Yalnızca yerli', 'yabanci': 'Yalnızca yabancı'}
ADET = 5
BITEN_ADET = 12  # "sözleşmesi bitecek" bölümünde en çok bu kadar aday
GUCLU_ESIK = 70  # "güçlü yan" sayılan en düşük yüzdelik (Kıyasla'daki gibi; altındakiler güçlü yan diye yazılmaz)


def guclu_yanlar(a):
    """Adayın en yüksek üç yüzdeliğinden GUCLU_ESIK ve üstü olanlar: [(istatistik, yüzdelik)]."""
    return [(ad, pc) for ad, pc in a['guclu'] if pc >= GUCLU_ESIK]


ACIKLAMA_ENDEKS = (
    'Perf.: performans endeksi (0-100), oyuncunun kendi mevkidaşlarına göre gol, xG, asist, xA, şut, kilit pas, çalım, '
    'pas, top çalma… (90 dakika başına) yüzdelik dilimlerinin ortalaması; kaleciler kendi aralarında. Bu '
    'sezonunki önceki sezonuyla (uygulamadaki herhangi bir ligde; o sezon ligindeki mevkidaşlarına göre) '
    'harmanlanır: önceki sezon en çok 15 maçlık sürenin yarısı kadar sayılır, sezon ilerledikçe bu sezon öne '
    'geçer. Az süre alan oyuncunun puanı ortalamaya (50) doğru çekilir: kısa bir parlak gidiş ya da form '
    'düşüşü, uzun süreli üretimle aynı sayılmaz. F/P: '
    'endeks ile piyasa değerinin ligdeki yüzdelik sırası arasındaki fark (artı: değerinin üstünde oynuyor). '
    f'Güçlü yanları: mevkidaşlarına göre en yüksek üç yüzdelikten {GUCLU_ESIK} ve üstü olanlar. Piyasa değeri '
    'FotMob\'un; endeks ve F/P uygulamanın '
    'hesabı.')
ACIKLAMA_ZORLUK = (
    'Transfer zorluğu (0-100): oyuncuyu kulübünden almanın ne kadar zor olduğu. Kulübün büyüklüğü (kadro değeri; '
    'Real Madrid, Barcelona, Bayern gibi dev kulüpler satma baskısı altında değildir, küçük kulüpler doğru fiyata '
    'satar), oyuncunun takımındaki rolü (düzenli ilk 11 mi, yedek mi), kulüp için önemi (değerinin kadro '
    'değerindeki payı) ve yaşı (30 yaş üstünü kulüpler daha kolay bırakır, 21 yaş altını korur). Gerçekçi hedef: performans endeksi, zorluk arttıkça indirimli (en zor oyuncuda %40). '
    'Sözleşme: bitişine 6 aydan az kalan oyuncu bedelsiz ya da çok ucuza alınabilir (−35), son yılındaki '
    'oyuncuda kulüp satmaya daha açıktır (−15), 4 yıl ve üstü sözleşme korur (+5). Sözleşme bitişi FotMob\'dan; '
    'FotMob\'da yoksa Transfermarkt\'tan (yalnızca sözleşme tarihi; kiralık oyuncuda ana kulübüyle sözleşmesi). '
    'Listede görünebilecek oyuncular için, yavaşça alınır ve saklanır. Serbest kalma bedeli veride yok.')
JS_OYUNCU = '(e) => { const t = e.target.closest("[data-oyuncu]"); if (t) { e.stopPropagation(); emit(t.dataset.oyuncu); } }'


# ---------------------------------------------------------------- saf HTML / veri üreticiler (arayüz öğesine dokunmaz)
def _izin(zorluk):
    """Transfer zorluğu süzgecinin izin verdiği etiketler (None: hepsi)."""
    return {'': None, 'cok': {'Kolay', 'Orta', 'Zor'}, 'kolay': {'Kolay', 'Orta'}}[zorluk or '']


def _aday_html(depo, a, tum, anahtar):
    """Bir scout adayının kutusu: ad, endeks, takım, değer, F/P, güçlü yanlar, transfer zorluğu."""
    p = a['p']
    takim_ad = p['t'].split(' / ')[-1]
    tid = depo.takim_kimligi(a['lig'], takim_ad)
    guclu = ' · '.join(f'{e(ad)} {pc}' for ad, pc in guclu_yanlar(a)) or 'belirgin bir üstün yanı yok'
    fp = '' if a['fp'] is None else (f'<span style="color:{"var(--pitch-2)" if a["fp"] > 0 else "var(--bad)"};font-weight:700">'
                                     f'F/P {"+" if a["fp"] > 0 else ""}{round(a["fp"])}</span>')
    return (f'<div class="sc-oyuncu"><div class="sc-ust"><span class="link sc-ad" data-oyuncu="{e(a["lig"])}:{e(a["yil"])}:{e(p["id"])}">'
            f'{e(p["n"])}</span><span class="sc-endeks" title="Performans endeksi">{round(a["endeks"])}</span></div>'
            f'<div class="cap">{takim_logo(tid)}{takim_link(takim_ad, tid) if tid else e(takim_ad)} · {e(mevki_adi(p))}'
            + (f' · {p["yas"]} yaş' if p.get('yas') is not None else '')
            + (f' · {e(turkce(a["uyruk"][1]))}' if a.get('uyruk') and a['uyruk'][1] else '')
            + (f' · {e(LIG_ULKE.get(a["lig"], a["lig"]))}' if tum else '') + '</div>'
            f'<div class="sc-alt"><span>{para(a["deger"], "–")}</span>{fp}<span class="cap">{p["min"]} dk · {p["g"]} gol · '
            f'{p["a"]} asist</span></div>'
            f'<div class="sc-bar"><i style="width:{round(a["endeks"])}%"></i></div>'
            f'<div class="cap">Güçlü yanları: {guclu}</div>'
            + (f'<div class="cap">İstikrar: {e(lig_maclari.istikrar_yazisi(a["istikrar"]))}</div>' if a.get('istikrar') else '')
            + f'<div class="sc-zorluk"><span class="sc-z {ZORLUK_SINIF[a["zorluk_etiket"]]}">Transfer: '
            f'{e(a["zorluk_etiket"])} ({a["zorluk"]})</span><span class="cap">{e("; ".join(a["zorluk_neden"]))}</span>'
            + (f'<span class="cap"> · gerçekçi hedef puanı {round(a["gercekci"])}</span>' if anahtar == 'gercekci' else '')
            + '</div></div>')


def _aktar_tablosu(adaylar, izin, anahtar):
    """Süzgeçlere uyan bütün adaylar, mevki grubu ve seçili sıralamaya göre: (başlıklar, satırlar)."""
    grup_sira = {g: k for k, (g, _) in enumerate(oyuncu_tahmin.SCOUT_GRUPLARI)}
    grup_ad = dict(oyuncu_tahmin.SCOUT_GRUPLARI)
    liste = sorted((a for a in adaylar if izin is None or a['zorluk_etiket'] in izin),
                   key=lambda a: (grup_sira.get(a['grup'], 99), -(a[anahtar] if a[anahtar] is not None else -999)))
    basliklar = ['Mevki grubu', 'Oyuncu', 'Takım', 'Lig', 'Mevki', 'Yaş', 'Uyruk', 'Performans endeksi', 'Piyasa değeri (€)',
                 'Fiyat-performans', 'Transfer zorluğu', 'Zorluk', 'Gerçekçi hedef puanı', 'Sözleşme bitişi', 'Dakika', 'Gol',
                 'Asist', 'Güçlü yanları', 'İstikrar', 'İstikrar yüzdeliği']
    satirlar = [[grup_ad.get(a['grup'], a['grup']), a['p']['n'], a['p']['t'].split(' / ')[-1], LIG_ULKE.get(a['lig'], a['lig']),
                 mevki_adi(a['p']), a['p'].get('yas'), turkce(a['uyruk'][1]) if a.get('uyruk') and a['uyruk'][1] else None,
                 round(a['endeks'], 1), a['deger'], round(a['fp'], 1) if a['fp'] is not None else None, a['zorluk'],
                 a['zorluk_etiket'], round(a['gercekci'], 1), a.get('sozlesme'), a['p']['min'], a['p']['g'], a['p']['a'],
                 ', '.join(f'{ad} {pc}' for ad, pc in guclu_yanlar(a)),
                 (a.get('istikrar') or {}).get('etiket'), (a.get('istikrar') or {}).get('yuzdelik')] for a in liste]
    return basliklar, satirlar


def _izgara_html(depo, adaylar, tum, anahtar, izin):
    kartlar = []
    for g, baslik in oyuncu_tahmin.SCOUT_GRUPLARI:
        liste = [a for a in adaylar if a['grup'] == g and (anahtar != 'fp' or a['fp'] is not None)
                 and (izin is None or a['zorluk_etiket'] in izin)]
        liste.sort(key=lambda a: -a[anahtar])
        satirlar = [_aday_html(depo, a, tum, anahtar) for a in liste[:ADET]]
        kartlar.append(f'<div class="sc-grup"><div class="sc-baslik">{baslik}</div>'
                       + (''.join(satirlar) or '<div class="cap">Bu süzgeçlerle aday yok.</div>') + '</div>')
    return '<div class="sc-izgara">' + ''.join(kartlar) + '</div>'


def _kalan_ay(a, bugun):
    b = date.fromisoformat(a['sozlesme'][:10])
    return (b.year - bugun.year) * 12 + b.month - bugun.month


def _bitenler_html(depo, uygun, tum, bugun):
    return ('<div class="sc-izgara">' + ''.join(
        f'<div>{_aday_html(depo, a, tum, "endeks")}<div class="cap" style="margin:-6px 0 8px 4px">Sözleşme bitişi '
        f'{a["sozlesme"][5:7]}.{a["sozlesme"][:4]} · {_kalan_ay(a, bugun)} ay kaldı</div></div>' for a in uygun) + '</div>'
        if uygun else '<p class="cap">Bu süzgeçlerle sözleşmesi yakında bitecek aday yok.</p>')


def _bitenler_notu(sinir, bilinen, toplam):
    return (f'Sözleşmesi {sinir} ay içinde bitecek adaylar, performans endeksine göre (yaş, kapsam, değer ve '
            f'zorluk süzgeçleri geçerli). Sözleşme bitişi bilinen {bilinen} aday arasından '
            f'(toplam {toplam}); tarih, listelerde görünebilecek adaylar için indirilir. Sözleşmesi '
            'biten oyuncu bedelsiz, son 6 ayındaki oyuncu ön sözleşmeyle alınabilir.')


def _ihtiyac_html(depo, S, takim, ihtiyac, en_iyi, oneriler, uyruk, havuz_bos):
    """Takımın mevki mevki gücü ve en zayıf mevkisi için öneriler (ihtiyac: oyuncu_tahmin.takim_ihtiyaci)."""
    zayif = ihtiyac[0]
    tid = depo.takim_kimligi(S.lig, takim)
    mevkiler = ''.join(
        f'<div class="ih-satir"><span>{e(r["baslik"])}</span><div class="sc-bar" style="flex:1"><i style="width:'
        f'{round(r["guc"])}%;background:{"var(--bad)" if r["fark"] < -3 else "var(--pitch-2)"}"></i></div>'
        f'<span class="cap" title="Takımın gücü / ligin ortalaması">{round(r["guc"])} / {round(r["lig_ort"])}</span></div>'
        for r in ihtiyac)
    mevcut = ', '.join(f'{e(p["n"])} ({round(x)})' for p, x in zayif['oyuncular']) or 'düzenli oynayan yok'
    detay_ad = DETAY.get(zayif.get('detay'), ('', ''))[1].lower()
    if detay_ad and zayif.get('zayif'):
        halka = (f' En zayıf halka: {e(zayif["zayif"]["n"])} ({detay_ad}); öneriler önce {detay_ad} oynayanlardan, '
                 'yeterli değilse mevkinin diğerlerinden.')
    elif detay_ad:
        halka = f' Bu mevkide {detay_ad} eksik; öneriler önce {detay_ad} oynayanlardan.'
    else:
        halka = ''
    return (
        f'<div class="ih-kutu"><div class="ih-sol"><div class="disp" style="font-weight:700;font-size:1.1rem">'
        f'{takim_logo(tid)}{e(takim)}: mevki mevki güç</div>{mevkiler}'
        f'<div class="cap" style="margin-top:4px">Güç: o mevkide en çok oynayanların performans endeksi ortalaması '
        f'(önceki sezonla harmanlanmış: kısa bir form düşüşü mevkiyi zayıf göstermesin); sağdaki sayı ligin '
        f'ortalaması. Kırmızı: ortalamanın belirgin altında.</div></div>'
        f'<div class="ih-sag"><div class="disp" style="font-weight:700;font-size:1.1rem">En zayıf mevki: {e(zayif["baslik"])}'
        f'</div><div class="cap">Şu an: {mevcut}.{halka} Öneriler: bütün liglerden, bundan iyi (endeks {round(en_iyi)} '
        f'üstü), alınabilir{"" if not uyruk else ", " + UYRUK_SECENEK[uyruk].split()[-1]}, gerçekçi hedef '
        f'puanına göre.</div>'
        + (''.join(_aday_html(depo, a, True, 'gercekci') for a in oneriler)
           or ('<p class="cap">Bütün liglerin adayları hazırlanıyor…</p>' if havuz_bos else
               '<p class="cap">Bu süzgeçlerle uygun aday yok; yaş, değer ya da uyruk süzgecini gevşetmeyi dene.</p>'))
        + '</div></div>')


def _kisa_liste(adaylar):
    """Listede görünebilecekler: her mevkide her sıralamanın ilk 15'i."""
    kisa = []
    for g, _ in oyuncu_tahmin.SCOUT_GRUPLARI:
        grup = [a for a in adaylar if a['grup'] == g]
        for k in ('endeks', 'fp', 'gercekci'):
            kisa += sorted((a for a in grup if a[k] is not None), key=lambda a: -a[k])[:15]
    return kisa


class _Scout:
    """Scout sekmesi: öğeler özniteliklerde; yukle() sekme yenilenince çağrılır. d['istek']: süzgeç değişince eski
    hesabın sonucu yenisinin üstüne yazılmasın."""

    def __init__(self, G):
        self.G = G
        self.d = {'adaylar': [], 'istek': 0, 'havuz': [], 'havuz_anahtar': None, 'h_istek': 0, 'izin': None, 'ulke': {}}
        with ui.column().classes('panel'):
            ui.html('<h3>Scout</h3>', sanitize=False)
            ui.label('Mevki mevki oyuncu önerileri: her grupta en iyi 5 aday. Süren sezon; ligde eşik kadar oynamış oyuncular. '
                     'Oyuncuya tıklayınca kartı, takıma tıklayınca takım sayfası açılır.').classes('lead')
            self._iskelet_sureklu()
            self._iskelet_ihtiyac()
            self._iskelet_sonuc()
        for oge in (self.izgara, self.ihtiyac_kutu, self.bitenler):  # oyuncu adına tıklanınca kartı
            oge.on('click', self.tiklandi, js_handler=JS_OYUNCU)
        for oge in (self.yas, self.kapsam, self.deger):
            oge.on_value_change(lambda _: G.arka_plan(self.yukle()))
        self.sira.on_value_change(lambda _: self.ciz())
        self.zorluk.on_value_change(lambda _: self.ciz())
        self.ihtiyac_sec.on_value_change(lambda _: self.ihtiyac_degisti())
        self.uyruk.on_value_change(lambda _: self.ihtiyac_degisti())

    # ---------------------------------------------------------------- arayüz iskeleti
    def _iskelet_sureklu(self):
        with ui.row().classes('w-full items-end gap-3'):
            self.yas = ui.select(YAS_SECENEK, value='U23', label='Yaş').props('outlined dense options-dense').style('min-width:150px')
            self.kapsam = ui.select({'lig': 'Açık lig', 'tum': 'Bütün ligler'}, value='lig', label='Kapsam').props(
                'outlined dense options-dense').style('min-width:150px')
            self.deger = ui.select(DEGER_SINIRI, value='', label='Piyasa değeri').props('outlined dense options-dense').style(
                'min-width:140px')
            self.zorluk = ui.select(ZORLUK_SECENEK, value='', label='Transfer zorluğu').props('outlined dense options-dense').style(
                'min-width:190px')
            self.sira = ui.toggle({'endeks': 'Performans', 'fp': 'Fiyat-performans', 'gercekci': 'Gerçekçi hedef'},
                                  value='endeks').props('dense no-caps unelevated toggle-color=primary')
            disa_aktar.dugme('Excel\'e aktar', lambda: self.aktar(), 'Süzgeçlere uyan bütün adaylar (her mevkinin ilk 5\'i değil), '
                             'İndirilenler\\MacTahmin klasörüne CSV olarak')

    def _iskelet_ihtiyac(self):
        with ui.row().classes('w-full items-end gap-3'):
            self.ihtiyac_sec = ui.select({'': 'Seçilmedi'}, value='', label='Takımın ihtiyacına göre öner', with_input=True).props(
                'outlined dense options-dense').style('min-width:260px')
            self.uyruk = ui.select(UYRUK_SECENEK, value='', label='Uyruk').props('outlined dense options-dense').style(
                'min-width:150px')
            ui.label('Bir takım seç: en zayıf mevkisi bulunur ve o mevki için takımdakinden iyi, alınabilir adaylar '
                     'uygulamadaki bütün liglerin bu sezon oynayan oyuncularından önerilir (yaş, piyasa değeri ve transfer '
                     'zorluğu süzgeçleri geçerli). Yerli: takımın ülkesinin vatandaşı.').classes('cap').style('flex:1')
        self.ih_durum = ui.label().classes('cap')
        self.ihtiyac_kutu = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), self.G)

    def _iskelet_sonuc(self):
        self.durum = ui.label().classes('cap')
        self.izgara = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), self.G)
        with ui.row().classes('w-full items-end gap-3').style('margin-top:10px'):
            ui.html('<h3>Sözleşmesi bitecek iyi oyuncular</h3>', sanitize=False)
            self.bitis_sec = ui.toggle({6: '6 ay içinde', 12: '12 ay içinde'}, value=12, on_change=lambda _: self.bitenler_ciz()).props(
                'dense no-caps unelevated toggle-color=primary')
        self.bitenler_not = ui.label().classes('cap')
        self.bitenler = takim_tiklama(ui.html('', sanitize=False).classes('w-full'), self.G)
        ui.label(ACIKLAMA_ENDEKS).classes('cap')
        ui.label(ACIKLAMA_ZORLUK).classes('cap')

    # ---------------------------------------------------------------- etkileşim
    def tiklandi(self, ev):
        G = self.G
        a = str(ev.args or '')
        if ':' in a:
            lig, yil, pid = a.split(':', 2)
            if G.S and G.S.lig == lig and G.S.yil == int(yil):
                p = next((q for q in G.S.PLY if str(q['id']) == pid), None)
                if p:
                    G.oyuncu_ac(p['idx'])
                    return
            G.git(lig, int(yil), int(pid) if pid.lstrip('-').isdigit() else pid)

    def aktar(self):
        """Süzgeçlere uyan bütün adaylar, mevki grubu ve seçili sıralamaya göre."""
        basliklar, satirlar = _aktar_tablosu(self.d['adaylar'], _izin(self.zorluk.value), self.sira.value)
        kapsam_ad = 'bütün ligler' if self.kapsam.value == 'tum' else LIG_ADI.get(self.G.S.lig, self.G.S.lig)
        return f'Scout {kapsam_ad} {YAS_SECENEK[self.yas.value]}', basliklar, satirlar

    def ihtiyac_degisti(self):
        self.ciz()
        self.G.arka_plan(self.havuz_hazirla())

    # ---------------------------------------------------------------- çizim
    def ciz(self):
        tum = self.kapsam.value == 'tum'
        self.izgara.content = _izgara_html(self.G.depo, self.d['adaylar'], tum, self.sira.value, _izin(self.zorluk.value))
        self.ihtiyac_ciz()
        self.bitenler_ciz()

    def bitenler_ciz(self):
        """Sözleşmesi bitis_sec ay içinde bitecek adaylar (yaş, kapsam, değer ve zorluk süzgeçleriyle), performans endeksine
        göre: bedelsiz ya da ucuz transfer fırsatları. Sözleşme tarihi yalnızca bilinen adaylarda (önbellek ve listelerde
        görünebilecekler için indirilenler)."""
        bugun = date.today()
        sinir = self.bitis_sec.value or 12
        izin = _izin(self.zorluk.value)
        bilinen = [a for a in self.d['adaylar'] if a.get('sozlesme')]
        uygun = sorted((a for a in bilinen if 0 <= _kalan_ay(a, bugun) <= sinir and (izin is None or a['zorluk_etiket'] in izin)),
                       key=lambda a: -a['endeks'])[:BITEN_ADET]
        self.bitenler.content = _bitenler_html(self.G.depo, uygun, self.kapsam.value == 'tum', bugun)
        self.bitenler_not.text = _bitenler_notu(sinir, len(bilinen), len(self.d['adaylar']))

    def havuz(self):
        """İhtiyaç önerilerinin aday havuzu: bütün liglerin adayları (kapsam "Bütün ligler"se ana liste zaten odur)."""
        return self.d['adaylar'] if self.kapsam.value == 'tum' else self.d['havuz']

    def ihtiyac_adaylari(self, S, takim, zayif, en_iyi):
        """Takımdaki en iyisinden yüksek endeksli, "Çok zor" olmayan (zorluk süzgeci seçiliyse ona göre), uyruk süzgecine
        uyan, takımın kendi oyuncusu olmayan adaylar; gerçekçi hedef puanına göre. Asıl ihtiyaç olan ayrıntılı mevki
        (zayif['detay']: ör. sağ bek, ön libero) biliniyorsa önce o mevkinin oyuncuları; yeterli değilse grubun diğerleri."""
        liste = self._ihtiyac_adaylari(S, takim, zayif, en_iyi)
        detay = zayif.get('detay')
        if not detay:
            return liste
        ayni = [a for a in liste if a['p'].get('detay') == detay]
        return ayni + [a for a in liste if a['p'].get('detay') != detay] if len(ayni) < ADET else ayni

    def _ihtiyac_adaylari(self, S, takim, zayif, en_iyi):
        uygun = _izin(self.zorluk.value) or {'Kolay', 'Orta', 'Zor'}
        ulke = self.d['ulke'].get(takim)
        uyruk = self.uyruk.value

        def uyruk_uygun(a):
            if not uyruk:
                return True
            if not ulke or not a.get('uyruk'):  # uyruğu bilinmeyen süzgeçte dışarıda kalır
                return False
            return (a['uyruk'][0] == ulke) == (uyruk == 'yerli')
        return sorted((a for a in self.havuz() if a['grup'] == zayif['grup'] and a['endeks'] > en_iyi
                       and a['zorluk_etiket'] in uygun and uyruk_uygun(a)
                       and not (a['lig'] == S.lig and a['p']['t'].split(' / ')[-1] == takim)),
                      key=lambda a: -a['gercekci'])

    def ihtiyac_ciz(self):
        """Seçilen takımın en zayıf mevkisi ve o mevki için bütün liglerden öneriler (ihtiyac_adaylari)."""
        takim, S = self.ihtiyac_sec.value, self.G.S
        if not takim or not S or takim not in S.T or S.yil != SON_SEZON:
            self.ihtiyac_kutu.content = ''
            return
        ihtiyac = oyuncu_tahmin.takim_ihtiyaci(S, takim)
        zayif = ihtiyac[0]
        en_iyi = max((x for _, x in zayif['oyuncular']), default=0)
        oneriler = self.ihtiyac_adaylari(S, takim, zayif, en_iyi)[:ADET]
        self.ihtiyac_kutu.content = _ihtiyac_html(self.G.depo, S, takim, ihtiyac, en_iyi, oneriler, self.uyruk.value,
                                                  not self.havuz())

    # ---------------------------------------------------------------- yükleme
    async def yukle(self):
        G, d = self.G, self.d
        d['istek'] += 1
        istek = d['istek']
        if not G.S:
            return
        if set(self.ihtiyac_sec.options) != {''} | set(G.S.T):  # ihtiyaç analizi açık ligin takımları için
            self.ihtiyac_sec.set_options({'': 'Seçilmedi', **{t: t for t in sorted(G.S.T)}},
                                         value=self.ihtiyac_sec.value if self.ihtiyac_sec.value in G.S.T else '')
        ligler = [l[0] for l in LIGLER] if self.kapsam.value == 'tum' else [G.S.lig]
        if d.get('ligler') != ligler:  # başka lig: yenisi hazırlanırken öncekinin adayları görünmesin
            d['ligler'], d['adaylar'] = ligler, []
            self.izgara.content = ''
        gecerli = lambda: istek == d['istek']  # noqa: E731

        def yaz(metin):
            if gecerli():  # bu arada başka bir seçim yapıldıysa onun durum yazısını ezme
                self.durum.text = metin
        adaylar = await self.topla(ligler, gecerli, yaz)
        if adaylar is None:
            return
        d['adaylar'] = adaylar
        ozet = (f'{len(adaylar)} aday · {"bütün ligler" if self.kapsam.value == "tum" else LIG_ADI.get(G.S.lig, G.S.lig)} · '
                f'{YAS_SECENEK[self.yas.value].lower()}'
                + (f' · {DEGER_SINIRI[self.deger.value].lower()}' if self.deger.value else ''))
        if await self.sozlesme_ekle(adaylar, lambda: _kisa_liste(adaylar), gecerli, yaz, ozet, self.ciz):
            G.arka_plan(self.havuz_hazirla())

    async def topla(self, ligler, gecerli, yaz):
        """Liglerin scout adayları (süren sezon; yaş ve piyasa değeri süzgeçleriyle), uyruk ve istikrarla
        (Depo.lig_scout_adaylari). Bütün ligler: diske yazılmış havuzdan hemen (bayatsa yenisi arkada hesaplanır, gelince
        ekran yenilenir); hiç yoksa hesaplanıp yazılır. Bu arada başka bir seçim yapıldıysa (gecerli() False) None."""
        G = self.G
        y, dg = self.yas.value, self.deger.value
        # run.io_bound uygulama kapanırken None döner
        if len(ligler) > 1:
            kayit = await run.io_bound(G.depo.scout_havuzu_oku, y, dg)
            if kayit:
                adaylar, taze = kayit
                if not taze:
                    G.arka_plan(self.havuz_tazele(y, dg))
                return adaylar if gecerli() else None
            adaylar = await run.io_bound(G.depo.scout_havuzu_hesapla, y, dg, yaz, lambda: not gecerli())
            return adaylar if adaylar is not None and gecerli() else None
        yaz(f'Hazırlanıyor… {LIG_ADI.get(ligler[0], ligler[0])}')
        try:
            S = await run.io_bound(G.depo.sezon, ligler[0], SON_SEZON)
        except Exception:
            logger.debug('sezon kurulamadı: %s', ligler[0], exc_info=True)
            return []
        if S is None or not S.M:
            return [] if gecerli() else None
        adaylar = await run.io_bound(G.depo.lig_scout_adaylari, S, y, dg, yaz) or []
        return adaylar if gecerli() else None

    async def havuz_tazele(self, y, dg):
        """Bayat havuzun (lig verisi değişti ya da bir gün geçti) yenisi arkada hesaplanır; süzgeçler değişmediyse ekran
        yeni havuzla yenilenir."""
        G, d = self.G, self.d
        if d.get('tazeleniyor') == (y, dg):
            return
        d['tazeleniyor'] = (y, dg)
        try:
            yeni = await run.io_bound(G.depo.scout_havuzu_hesapla, y, dg)
        finally:
            d['tazeleniyor'] = None
        if yeni is None or (self.yas.value, self.deger.value) != (y, dg):
            return
        if self.kapsam.value == 'tum':
            G.arka_plan(self.yukle())
        else:
            d['havuz_anahtar'] = None
            G.arka_plan(self.havuz_hazirla())

    async def sozlesme_ekle(self, adaylar, kisa_liste, gecerli, yaz, ozet, ciz_fn):
        """Sözleşme bitişleri. Sırası: FotMob (önbellek) → Transfermarkt (önbellek, yalnızca FotMob'da yoksa); önbellektekiler
        hemen uygulanıp çizilir, kisa_liste()'dekilerin eksikleri arka planda indirilir, gelince yeniden çizilir.
        Döner: tamamlandıysa True (bu arada başka bir seçim yapıldıysa False)."""
        depo = self.G.depo
        fid = lambda a: str(a['p'].get('fm_id'))  # noqa: E731
        tm_satir = lambda a: (a['p'].get('fm_id'), a['p']['n'], a['p']['t'].split(' / ')[-1], a['p'].get('yas'))  # noqa: E731
        fm = await run.io_bound(depo.sozlesmeler, [a['p'].get('fm_id') for a in adaylar], None, False) or {}
        tmk = await run.io_bound(depo.sozlesmeler_tm, [tm_satir(a) for a in adaylar if not fm.get(fid(a))], None, False) or {}
        if not gecerli():
            return False

        def uygula(a):
            if fm.get(fid(a)):
                oyuncu_tahmin.sozlesme_uygula(a, fm[fid(a)])
            elif (tmk.get(fid(a)) or {}).get('bitis'):
                r = tmk[fid(a)]
                oyuncu_tahmin.sozlesme_uygula(a, r['bitis'], kiralik=r.get('kiralik'))
        for a in adaylar:
            uygula(a)
        yaz(ozet)
        ciz_fn()
        kisa = list({fid(a): a for a in kisa_liste() if a['p'].get('fm_id') is not None}.values())

        def ilerleme2(kaynak, sure):
            return lambda i, n: yaz(f'{ozet} · sözleşme bilgileri alınıyor ({kaynak})… {i}/{n} (bir kez, sonra {sure} önbellekten)')
        # 1) FotMob'da hiç bakılmamışlar
        ids = [a['p'].get('fm_id') for a in kisa if fid(a) not in fm]
        if ids:
            fm.update(await run.io_bound(depo.sozlesmeler, ids, ilerleme2('FotMob', '30 gün')) or {})
            if not gecerli():
                return False
        # 2) FotMob'da sözleşmesi olmayanlar: Transfermarkt'tan yalnızca sözleşme bitişi
        tm_ids = [tm_satir(a) for a in kisa if not fm.get(fid(a)) and not (tmk.get(fid(a)) or {}).get('tm')
                  and fid(a) not in tmk]
        if tm_ids:
            tmk.update(await run.io_bound(depo.sozlesmeler_tm, tm_ids, ilerleme2('Transfermarkt', '90 gün')) or {})
            if not gecerli():
                return False
        for a in adaylar:
            uygula(a)
        yaz(ozet)
        ciz_fn()
        return True

    async def havuz_hazirla(self):
        """İhtiyaç önerileri için bütün liglerin adayları (kapsam "Açık lig"ken ayrı havuz; yaş ve değer süzgeci değişince
        yeniden). Takım seçilmemişse bir şey yapılmaz."""
        G, d = self.G, self.d
        takim, S = self.ihtiyac_sec.value, G.S
        if not takim or not S or S.yil != SON_SEZON or takim not in S.T:
            self.ih_durum.text = ''
            return
        if takim not in d['ulke']:
            tid = G.depo.takim_kimligi(S.lig, takim)
            d['ulke'][takim] = await run.io_bound(G.depo.takim_ulkesi, tid) if tid is not None else None
        if getattr(S, '_endeks_harman', None) is None:  # mevkilerin gücü önceki sezonla harmanlı endeksten
            self.ih_durum.text = 'Takımın mevkileri değerlendiriliyor (oyuncuların önceki sezonu okunuyor)…'
            await run.io_bound(G.depo.endeks_harmanla, S)
            if G.S is not S:
                return
            self.ih_durum.text = ''
        if self.kapsam.value == 'tum':
            self.ih_durum.text = ''
            self.ihtiyac_ciz()
            return
        anahtar = (self.yas.value, self.deger.value)
        if d['havuz_anahtar'] == anahtar:
            self.ihtiyac_ciz()
            return
        d['h_istek'] += 1
        istek = d['h_istek']
        gecerli = lambda: istek == d['h_istek'] and anahtar == (self.yas.value, self.deger.value)  # noqa: E731

        def yaz(metin):
            if gecerli():
                self.ih_durum.text = 'İhtiyaç önerileri (bütün ligler): ' + metin
        d['havuz'], d['havuz_anahtar'] = [], None
        self.ihtiyac_ciz()
        adaylar = await self.topla([l[0] for l in LIGLER], gecerli, yaz)
        if adaylar is None:
            return
        d['havuz'], d['havuz_anahtar'] = adaylar, anahtar

        def kisa_liste():
            """Seçili takımın en zayıf mevkisi için önerilebilecek ilk 15."""
            S2, t = G.S, self.ihtiyac_sec.value
            if not t or t not in S2.T:
                return []
            zayif = oyuncu_tahmin.takim_ihtiyaci(S2, t)[0]
            en_iyi = max((x for _, x in zayif['oyuncular']), default=0)
            return self.ihtiyac_adaylari(S2, t, zayif, en_iyi)[:15]
        ozet = f'{len(adaylar)} aday'
        if await self.sozlesme_ekle(adaylar, kisa_liste, gecerli, yaz, ozet, self.ihtiyac_ciz):
            self.ih_durum.text = f'İhtiyaç önerileri: bütün liglerden {len(adaylar)} aday arasından.'


def kur(G):
    return _Scout(G).yukle
