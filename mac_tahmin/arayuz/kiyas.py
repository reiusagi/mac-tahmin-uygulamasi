"""Kıyasla sekmesi: seçilen 2–4 oyuncunun (farklı lig ve sezonlardan da olabilir) istatistikleri yan yana, her satırda
en iyi değer vurgulu; iki oyuncuda aradaki fark ayrı sütunda. Üstte mevkidaşlara göre yüzdeliklerin radar grafiği.

Yeni istatistik eklemek: METRIKLER listesine (anahtar, başlık, grup, tür) satırı ekle. Anahtar oyuncu sözlüğündeki alan
(g, xg…), sezon.EK'teki ek istatistik ya da TURETILMIS'teki bir işlev olabilir."""
import logging

from nicegui import app, run, ui

from ..sezon import EK, LIGLER, kariyer, mevki_adi, sezon_etiketi, yas_metni
from . import disa_aktar, takim_kiyas
from .ortak import e, fmt, lig_bilgi, lig_secenekleri, sayi, sezon_secenekleri

logger = logging.getLogger(__name__)

ID, AD = 'kiyas', 'Kıyasla'
TEMBEL = True  # seçili oyuncuların sezonları ve takım kıyası: yalnızca sekme açıkken
EN_COK = 4
RENKLER = ['#2f7a57', '#c9960f', '#35598a', '#b0413e']

# tür: 'toplam' 90 dk başına çevrilebilir, 'oran' olduğu gibi kalır (yüzde, ortalama), 'sabit' hep toplam gösterilir
METRIKLER = [
    ('mp', 'Maç', 'Genel', 'sabit'), ('min', 'Dakika', 'Genel', 'sabit'), ('rt', 'FotMob puanı', 'Genel', 'oran'),
    ('g', 'Gol', 'Hücum', 'toplam'), ('npg', 'Penaltısız gol', 'Hücum', 'toplam'), ('xg', 'xG', 'Hücum', 'toplam'),
    ('npxg', 'Penaltısız xG', 'Hücum', 'toplam'), ('gxg', 'Gol − xG', 'Hücum', 'toplam'), ('sh', 'Şut', 'Hücum', 'toplam'),
    ('sbg', 'Şut başına gol', 'Hücum', 'oran'), ('xgot', 'İsabetli şut xG (xGOT)', 'Hücum', 'toplam'),
    ('bcm', 'Kaçan net pozisyon', 'Hücum', 'toplam'),
    ('a', 'Asist', 'Yaratıcılık', 'toplam'), ('xa', 'xA', 'Yaratıcılık', 'toplam'), ('ga', 'Gol + asist', 'Yaratıcılık', 'toplam'),
    ('kp', 'Kilit pas', 'Yaratıcılık', 'toplam'), ('bcc', 'Yaratılan net pozisyon', 'Yaratıcılık', 'toplam'),
    ('xgc', 'xG zinciri (xGChain)', 'Yaratıcılık', 'toplam'), ('xgb', 'xG hazırlık (xGBuildup)', 'Yaratıcılık', 'toplam'),
    ('pas', 'İsabetli pas (90 dk)', 'Pas ve top sürme', 'oran'), ('pasp', 'Pas isabeti %', 'Pas ve top sürme', 'oran'),
    ('drb', 'Başarılı çalım (90 dk)', 'Pas ve top sürme', 'oran'), ('drbp', 'Çalım başarısı %', 'Pas ve top sürme', 'oran'),
    ('tkl', 'Top çalma', 'Savunma', 'toplam'), ('int', 'Pas arası', 'Savunma', 'toplam'),
    ('clr', 'Uzaklaştırma', 'Savunma', 'toplam'), ('rec', 'Top kazanma', 'Savunma', 'toplam'),
    ('sav', 'Kurtarış', 'Kaleci', 'toplam'), ('savp', 'Kurtarış %', 'Kaleci', 'oran'), ('gc', 'Yenen gol', 'Kaleci', 'toplam'),
    ('cs', 'Gol yemeden maç', 'Kaleci', 'sabit'), ('gp', 'Önlenen gol', 'Kaleci', 'oran'),
    ('yc', 'Sarı kart', 'Disiplin', 'toplam'), ('rc', 'Kırmızı kart', 'Disiplin', 'toplam'),
]
AZI_IYI = {'yc', 'rc', 'gc', 'bcm'}  # düşük olanın daha iyi sayıldığı istatistikler
TURETILMIS = {
    'ga': lambda p: p['g'] + p['a'],
    'gxg': lambda p: p['g'] - p['xg'],
    'sbg': lambda p: p['g'] / p['sh'] if p.get('sh') else None,
}


def deger(p, k, tur, p90):
    if k in TURETILMIS:
        v = TURETILMIS[k](p)
    elif k in p and k not in EK:
        v = p[k]
    else:
        v = p['ex'].get(k)
    if v is None:
        return None
    if p90 and tur == 'toplam':
        return v / p['min'] * 90 if p['min'] else None
    return v


def yaz(k, v, tur, p90):
    if v is None:
        return '–'
    if k == 'min':
        return sayi(v)
    if k == 'gxg':
        return ('+' if v > 0 else '') + fmt(v, 2 if p90 else 1)
    if k == 'sbg':
        return fmt(v, 2)
    if (p90 and tur == 'toplam') or k in ('xg', 'xa', 'npxg', 'xgot', 'xgc', 'xgb', 'gp', 'rt', 'pas', 'drb'):
        return fmt(v, 2)
    if isinstance(v, float) and not v.is_integer():
        return fmt(v, 1)
    return str(int(v))


# ---------------------------------------------------------------- saf HTML / veri üreticiler (arayüz öğesine dokunmaz)
def _kisa_ad(p, S, liste):
    """Aynı oyuncu iki farklı sezonla eklenmişse adın yanına sezon yazılır."""
    ayni = sum(1 for _, _, q in liste if q['n'] == p['n']) > 1
    return p['n'] + (f' ({sezon_etiketi(S.yil, S.lig)})' if ayni else '')


def _radar_hazirla(liste):
    """Ortak istatistikler ve radar serileri: (ortak, seriler); ortak üçten azsa seriler boş."""
    kartlar_ = [(S.oyuncu_karti(p), p) for _, S, p in liste]
    ortak = None
    for k, _ in kartlar_:
        etiketler = [y[0] for y in k['yuzdelik']]
        ortak = etiketler if ortak is None else [x for x in ortak if x in etiketler]
    if not ortak or len(ortak) < 3:
        return ortak, []
    return ortak, [
        {'name': _kisa_ad(p, S, liste), 'value': [dict((y[0], y[2]) for y in k['yuzdelik'])[x] for x in ortak],
         'lineStyle': {'color': RENKLER[i], 'width': 2}, 'itemStyle': {'color': RENKLER[i]},
         'areaStyle': {'color': RENKLER[i], 'opacity': .12}}
        for i, ((k, p), (_, S, _p)) in enumerate(zip(kartlar_, liste))]


def _aktar_tablosu(liste, p90):
    """Karşılaştırma tablosunun sayıları (ekrandaki görünümle) ve oyuncuların künyesi."""
    if len(liste) < 2:
        return 'Kıyas', [], []
    oyuncular = [p for _, _, p in liste]
    kaleci_var = any(p['pos'] == 'G' for p in oyuncular)
    basliklar = ['İstatistik'] + [_kisa_ad(p, S, liste) for _, S, p in liste]
    satirlar = [['Takım'] + [p['t'] for p in oyuncular],
                ['Lig ve sezon'] + [f'{lig_bilgi(S.lig)[1]} {sezon_etiketi(S.yil, S.lig)}' for _, S, _ in liste],
                ['Mevki'] + [mevki_adi(p) for p in oyuncular], ['Yaş'] + [p.get('yas') for p in oyuncular]]
    for k, ad, grup, tur in METRIKLER:
        if grup == 'Kaleci' and not kaleci_var:
            continue
        vals = [deger(p, k, tur, p90) for p in oyuncular]
        if all(v is None for v in vals):
            continue
        satirlar.append([ad + (' (90 dk)' if p90 and tur == 'toplam' and k not in ('mp', 'min') else '')] + vals)
    return 'Oyuncu kıyası ' + ' - '.join(p['n'] for p in oyuncular), basliklar, satirlar


def _fark_hucresi(k, tur, p90, a, b):
    """İki oyuncuda "Fark" sütununun hücresi (birinci eksi ikinci; rengi önde olanın rengi)."""
    if a is None or b is None or a == b:
        return '<td class="sag cap">–</td>'
    fark = a - b
    onde = 0 if (fark > 0) != (k in AZI_IYI) else 1
    yuzde_fark = f' <small class="cap">({abs(fark) / abs(b) * 100:.0f}%)</small>' if b and tur != 'oran' and k != 'gxg' else ''
    return (f'<td class="sag" style="color:{RENKLER[onde]};font-weight:700">'
            f'{"+" if fark > 0 else "−"}{yaz(k, abs(fark), tur, p90).lstrip("+")}{yuzde_fark}</td>')


def _tablo_html(liste, p90):
    oyuncular = [p for _, _, p in liste]
    kaleci_var = any(p['pos'] == 'G' for p in oyuncular)
    iki = len(oyuncular) == 2
    bas = ''.join(f'<th class="sag"><span class="kiyas-nokta" style="background:{RENKLER[i]}"></span>{e(_kisa_ad(p, S, liste))}</th>'
                  for i, (_, S, p) in enumerate(liste)) + ('<th class="sag">Fark</th>' if iki else '')
    satirlar, grup0 = [], None
    for k, ad, grup, tur in METRIKLER:
        if grup == 'Kaleci' and not kaleci_var:
            continue
        vals = [deger(p, k, tur, p90) for p in oyuncular]
        if all(v is None for v in vals):
            continue
        if grup != grup0:
            satirlar.append(f'<tr class="kiyas-grup"><td colspan="{len(oyuncular) + 1 + iki}">{e(grup)}</td></tr>')
            grup0 = grup
        dolu = [v for v in vals if v is not None]
        en_iyi = (min(dolu) if k in AZI_IYI else max(dolu)) if len(dolu) > 1 and len(set(dolu)) > 1 else None
        olcek = max(abs(v) for v in dolu) or 1
        etiket = ad + (' <small class="cap">(90 dk)</small>' if p90 and tur == 'toplam' and k not in ('mp', 'min') else '')
        hucre = []
        for i, v in enumerate(vals):
            cubuk = (f'<div class="kiyas-cubuk"><i style="width:{abs(v) / olcek * 100:.0f}%;background:{RENKLER[i]}"></i></div>'
                     if v is not None and tur != 'sabit' else '')
            hucre.append(f'<td class="sag{" kiyas-iyi" if en_iyi is not None and v == en_iyi else ""}">'
                         f'{yaz(k, v, tur, p90)}{cubuk}</td>')
        if iki:
            hucre.append(_fark_hucresi(k, tur, p90, *vals))
        satirlar.append(f'<tr><td>{etiket}</td>{"".join(hucre)}</tr>')
    return (f'<table class="tb kiyas-tablo"><thead><tr><th>İstatistik</th>{bas}</tr></thead>'
            f'<tbody>{"".join(satirlar)}</tbody></table>')


def _tablo_notu(liste, p90):
    iki = len(liste) == 2
    kaynaklar = {S.src for _, S, _ in liste}
    return ('Her satırda en iyi değer kalın ve vurgulu (kart, yenen gol ve kaçan net pozisyonda düşük olan iyi). '
            + ('Fark sütunu birinci oyuncu eksi ikinci oyuncudur; rengi önde olan oyuncunun rengidir, parantezdeki '
               'yüzde ikinci oyuncuya göre farktır. ' if iki else '')
            + ('90 dakika başına değerler az süre almış oyuncularda yanıltıcı olabilir. ' if p90 else '')
            + ('xG zinciri ve xG hazırlık yalnızca 5 büyük ligde (Understat) var. ' if len(kaynaklar) > 1 else '')
            + '"–": değer yok. FotMob puan, pas, çalım, top çalma gibi listelerine yalnızca kendi oynama eşiğini '
              'geçen oyuncuları alır; 5 büyük ligde FotMob\'la eşleşmeyen az sayıdaki oyuncuda ve 2016 öncesi sezonlarda '
              'bu istatistikler boştur.')


def _radar_secenekleri():
    return {
        'animation': False, 'tooltip': {'trigger': 'item'}, 'legend': {'bottom': 0, 'textStyle': {'color': '#8a9088'}},
        'radar': {'indicator': [], 'radius': '62%', 'splitNumber': 4, 'axisName': {'color': '#8a9088', 'fontSize': 11}},
        'series': [{'type': 'radar', 'data': []}],
    }


class _Kiyas:
    """Kıyasla sekmesi: öğeler özniteliklerde; yenile() sekme yenilenince çağrılır. d['surum']: eski çizimin sonucu
    yenisinin üstüne yazılmasın."""

    def __init__(self, G):
        self.G = G
        self.d = {'secili': list(app.storage.general.get('kiyas', [])), 'p90': True, 'lig': None, 'yil': None, 'surum': 0}
        self._iskelet_secim()
        self._iskelet_sonuc()
        self._iskelet_sezonlar()
        self.lig_sec.on_value_change(self.lig_degisti)
        self.sezon_sec.on_value_change(lambda ev: G.arka_plan(self.secenek_yukle()) if ev.value is not None else None)
        self.oyuncu_sec.on_value_change(self.secildi)
        G.kiyasa_ekle = self.kiyasa_ekle
        self.takim_yenile = takim_kiyas.kur(G)  # altta takım kıyaslama paneli

    # ---------------------------------------------------------------- arayüz iskeleti
    def _iskelet_secim(self):
        with ui.column().classes('panel'):
            ui.html('<h3>Oyuncu kıyasla</h3>', sanitize=False)
            ui.label(f'En çok {EN_COK} oyuncu seç; farklı liglerden ve sezonlardan da olabilir. Lig ve sezonu seç, oyuncunun adını '
                     'yazıp listeden tıkla. Oyuncu kartındaki "Kıyasla" düğmesiyle de eklenir. Aynı oyuncunun geçmiş sezonlarını '
                     '(başka takım ve liglerdeki de) karşılaştırmak için seçilen oyuncunun kutusundaki saat simgesine tıkla.').classes('lead')
            with ui.row().classes('w-full items-end gap-3'):
                self.lig_sec = ui.select(lig_secenekleri(), label='Lig').props('outlined dense options-dense').style('min-width:240px')
                self.sezon_sec = ui.select({}, label='Sezon').props('outlined dense options-dense').style('min-width:130px')
                self.oyuncu_sec = ui.select({}, label='Oyuncu', with_input=True).props(
                    'outlined dense options-dense input-debounce=150').classes('grow').style('min-width:260px')
            self.secim_not = ui.label().classes('cap')
            self.kartlar = ui.element('div').classes('w-full kiyas-kartlar')

    def _iskelet_sonuc(self):
        with ui.column().classes('panel') as self.sonuc_panel:
            with ui.row().classes('w-full items-center'):
                ui.html('<h3>Karşılaştırma</h3>', sanitize=False)
                ui.space()
                self.mod = ui.toggle({True: '90 dk başına', False: 'Sezon toplamı'}, value=True,
                                     on_change=lambda ev: self.mod_degisti(ev.value)).props(
                    'dense no-caps unelevated toggle-color=primary')
                disa_aktar.dugme('Excel\'e aktar', lambda: self.aktar(), 'Karşılaştırma tablosu (seçili görünümle: 90 dk başına ya da '
                                 'sezon toplamı) İndirilenler\\MacTahmin klasörüne CSV olarak')
            self.radar_baslik = ui.label('Mevkidaşlarına göre yüzdelik dilimler').classes('disp text-lg font-bold')
            self.radar = ui.echart(_radar_secenekleri()).classes('w-full').style('height:400px')
            self.radar_not = ui.label().classes('cap')
            self.tablo = ui.html('', sanitize=False).classes('w-full kaydir')
            self.tablo_not = ui.label().classes('cap')
            ui.html('<h3>Değerlendirme</h3>', sanitize=False)
            self.ozet = ui.html('', sanitize=False).classes('w-full kiyas-ozet')
            ui.label('Değerlendirme, yukarıdaki sayılardan kurallarla üretilir (90 dakika başına değerler ve mevkidaşlara göre '
                     'yüzdelikler); izleme, taktik ve lig seviyesi hesaba katılmaz.').classes('cap')

    def _iskelet_sezonlar(self):
        # oyuncunun diğer sezonları (farklı takım ve liglerde de): kartındaki saat düğmesiyle açılır
        with ui.dialog() as self.sezon_dlg, ui.card().classes('w-full gap-2').style(
                'max-width:640px;background:var(--panel);color:var(--ink)'):
            with ui.row().classes('w-full items-center no-wrap'):
                self.sezon_baslik = ui.label().classes('disp text-lg font-bold grow')
                ui.button(icon='close', on_click=self.sezon_dlg.close).props('flat round dense')
            self.sezon_not = ui.label().classes('cap')
            self.sezon_liste = ui.column().classes('w-full gap-0')

    # ------------------------------------------------------------ seçim alanı
    async def secenek_yukle(self):
        lig, yil = self.lig_sec.value, self.sezon_sec.value
        if not lig or yil is None:
            return
        oyuncu_sec = self.oyuncu_sec
        # yüklenirken kutu kapalı: liste gelmeden yazılan arama, gelen listeye uygulanmıyor
        oyuncu_sec.set_options({}, value=None)
        oyuncu_sec.set_enabled(False)
        oyuncu_sec.props('label="Oyuncu (yükleniyor…)"')
        try:
            S = await run.io_bound(self.G.depo.sezon, lig, yil)
        except Exception:
            logger.debug('sezon kurulamadı: %s %s', lig, yil, exc_info=True)
            oyuncu_sec.props('label="Oyuncu (bu sezonun verisi yok)"')
            return
        if (self.lig_sec.value, self.sezon_sec.value) != (lig, yil):
            return
        oyuncu_sec.set_enabled(len(self.d['secili']) < EN_COK)
        oyuncular = sorted(S.PLY, key=lambda p: -p['min'])
        oyuncu_sec.set_options({p['idx']: f'{p["n"]} · {p["t"]} · {mevki_adi(p)} · {sayi(p["min"])} dk' for p in oyuncular}, value=None)
        oyuncu_sec.props('label="Oyuncu (yazarak ara)"')

    def lig_degisti(self, ev):
        sec = sezon_secenekleri(ev.value)
        y = self.sezon_sec.value if self.sezon_sec.value in sec else max(sec)
        self.sezon_sec.set_options(sec, value=y)
        self.G.arka_plan(self.secenek_yukle())

    async def secildi(self, ev):
        """Listeden oyuncu seçilince hemen eklenir; kutu bir sonraki seçim için boşalır."""
        if ev.value is None:
            return
        S = await run.io_bound(self.G.depo.sezon, self.lig_sec.value, self.sezon_sec.value)
        self.ekle(S.lig, S.yil, S.PLY[ev.value])
        self.oyuncu_sec.set_value(None)

    def ekle(self, lig, yil, p):
        d = self.d
        anahtar = {'lig': lig, 'yil': yil, 'id': p['id'], 'n': p['n'], 't': p['t']}
        if any(_ayni(x, anahtar) for x in d['secili']):
            ui.notify(f'{p["n"]} ({sezon_etiketi(yil, lig)}) zaten listede.')
            return False
        if len(d['secili']) >= EN_COK:
            ui.notify(f'En çok {EN_COK} oyuncu kıyaslanabilir; önce birini çıkar.', type='warning')
            return False
        d['secili'].append(anahtar)
        self.kaydet()
        self.G.arka_plan(self.ciz())
        return True

    def cikar(self, i):
        self.d['secili'].pop(i)
        self.kaydet()
        self.G.arka_plan(self.ciz())

    def kaydet(self):
        app.storage.general['kiyas'] = self.d['secili']

    def kiyasa_ekle(self, lig, yil, p):
        """Oyuncu kartından: oyuncuyu ekler ve bu sekmeye geçer."""
        if self.ekle(lig, yil, p):
            self.G.sekme_ac(ID)
            ui.notify(f'{p["n"]} kıyaslamaya eklendi ({len(self.d["secili"])}/{EN_COK}).', type='positive')

    # ------------------------------------------------------------ çizim
    async def oyunculari_bul(self):
        """Seçili oyuncuları sezonlarından bulur: [(seçim, Sezon, oyuncu)]; verisi kalmayan atlanır."""
        out = []
        for x in self.d['secili']:
            try:
                S = await run.io_bound(self.G.depo.sezon, x['lig'], x['yil'])
            except Exception:
                logger.debug('sezon kurulamadı: %s %s', x['lig'], x['yil'], exc_info=True)
                continue
            p = next((q for q in S.PLY if x['id'] is not None and q['id'] == x['id']), None) \
                or next((q for q in S.PLY if q['n'] == x['n'] and q['t'] == x['t']), None)
            if p is not None:
                out.append((x, S, p))
        return out

    def mod_degisti(self, v):
        self.d['p90'] = v
        self.G.arka_plan(self.ciz())

    async def ciz(self):
        d = self.d
        d['surum'] += 1
        surum = d['surum']
        liste = await self.oyunculari_bul()
        if surum != d['surum']:
            return
        self.oyuncu_sec.set_enabled(len(d['secili']) < EN_COK)
        self.secim_not.text = (f'{len(liste)}/{EN_COK} oyuncu seçili.' if liste else 'Henüz oyuncu seçilmedi.')
        self.kartlar.clear()
        with self.kartlar:
            for i, (x, S, p) in enumerate(liste):
                self.kart_ciz(i, S, p)
        self.sonuc_panel.set_visibility(len(liste) >= 2)
        d['liste'] = liste
        if len(liste) >= 2:
            self.radar_ciz(liste)
            self.tablo_ciz(liste)
            adlar = [_kisa_ad(p, S, liste) for _, S, p in liste]
            self.ozet.content = ''.join(f'<p>{c}</p>' for c in cikarim([(S, p) for _, S, p in liste], adlar))

    def kart_ciz(self, i, S, p):
        G = self.G
        l = lig_bilgi(S.lig)
        with ui.element('div').classes('kiyas-kart').style(f'border-top:4px solid {RENKLER[i]}'):
            with ui.row().classes('w-full items-start no-wrap gap-1'):
                with ui.column().classes('gap-0 grow').style('min-width:0'):
                    ui.button(p['n'], on_click=lambda _, S=S, p=p: self.kart_ac(S, p)).props('flat dense no-caps').classes('link kiyas-ad')
                    ui.label(f'{p["t"]} · {mevki_adi(p)}').classes('cap')
                    ui.label(' · '.join(x for x in (f'{l[1]} {sezon_etiketi(S.yil, S.lig)}', yas_metni(p.get('yas'), S.yil),
                                                    p.get('rol') or '') if x)).classes('cap')
                with ui.column().classes('gap-0'):
                    ui.button(icon='close', on_click=lambda _, i=i: self.cikar(i)).props('flat round dense size=sm').tooltip('Çıkar')
                    ui.button(icon='history', on_click=lambda _, S=S, p=p: G.arka_plan(self.sezonlar_ac(S, p))).props(
                        'flat round dense size=sm color=primary').tooltip('Diğer sezonları (başka takım ve liglerdeki de): '
                                                                          'kıyaslamaya ekle')

    async def sezonlar_ac(self, S, p):
        """Oyuncunun uygulamadaki diğer lig-sezonları (sezon.kariyer); her biri tek tıkla kıyaslamaya eklenir."""
        G = self.G
        self.sezon_baslik.text = f'{p["n"]}: diğer sezonları'
        self.sezon_not.text = 'Sezonlar yükleniyor…'
        self.sezon_liste.clear()
        self.sezon_dlg.open()
        if p.get('id') is None:
            self.sezon_not.text = 'Bu oyuncu için sezon geçmişi yok.'
            return
        satirlar = await run.io_bound(kariyer, G.depo.veri_klasoru, S.src, p['id'], p.get('fm_id')) or []
        diger = [r for r in satirlar if not (r['anahtar'] == S.lig and r['yil'] == S.yil)]
        if not diger:
            self.sezon_not.text = f'Uygulamadaki {len(LIGLER)} ligde başka sezonu yok (kupalar ve uygulamada olmayan ligler sayılmaz).'
            return
        self.sezon_not.text = (f'Uygulamadaki {len(LIGLER)} ligde bulunan sezonları (kupalar ve uygulamada olmayan ligler yok). '
                               f'"Ekle" ile kıyaslamaya eklenir; en çok {EN_COK} sütun, aynı oyuncunun sezonları adının yanında '
                               'sezonla ayrılır.')
        with self.sezon_liste:
            for r in diger:
                var = any(x['lig'] == r['anahtar'] and x['yil'] == r['yil'] and x['id'] == r['id'] for x in self.d['secili'])
                with ui.row().classes('w-full items-center no-wrap gap-2').style('border-bottom:1px solid var(--line);padding:4px 0'):
                    with ui.column().classes('gap-0 grow').style('min-width:0'):
                        ui.label(f'{sezon_etiketi(r["yil"], r["anahtar"])} · {r["takim"]}').style('font-weight:600')
                        ui.label(f'{r["lig"]} · {r["mp"]} maç · {sayi(r["min"])} dk · {r["g"]} gol · {r["a"]} asist').classes('cap')
                    b = ui.button('Eklendi' if var else 'Ekle', icon='check' if var else 'add').props(
                        'unelevated dense no-caps color=primary')
                    b.set_enabled(not var)
                    b.on_click(lambda _, r=r, b=b: G.arka_plan(self.sezon_ekle(r, b)))

    async def sezon_ekle(self, r, dugme):
        try:
            S2 = await run.io_bound(self.G.depo.sezon, r['anahtar'], r['yil'])
        except Exception:
            logger.warning('sezon kurulamadı: %s %s', r['anahtar'], r['yil'], exc_info=True)
            ui.notify('Bu sezonun verisi yüklenemedi.', type='negative')
            return
        q = next((x for x in S2.PLY if x['id'] == r['id'] and x['t'] == r['takim']), None) \
            or next((x for x in S2.PLY if x['id'] == r['id']), None)
        if q is not None and self.ekle(S2.lig, S2.yil, q):
            dugme.text = 'Eklendi'
            dugme.props('icon=check')
            dugme.set_enabled(False)
            ui.notify(f'{q["n"]} ({sezon_etiketi(S2.yil, S2.lig)}) kıyaslamaya eklendi ({len(self.d["secili"])}/{EN_COK}).',
                      type='positive')

    def kart_ac(self, S, p):
        if self.G.S is S:
            self.G.oyuncu_ac(p['idx'])
        else:  # başka lig ya da sezon: kart açık lig değişmeden açılır
            self.G.git(S.lig, S.yil, p['id'])

    def radar_ciz(self, liste):
        ortak, seriler = _radar_hazirla(liste)
        if not ortak or len(ortak) < 3:
            self.radar_baslik.set_visibility(False)
            self.radar.set_visibility(False)
            self.radar_not.text = ('Yüzdelik grafiği için oyuncuların ortak en az üç istatistiği gerekiyor (kaleci ile saha oyuncusu '
                                   'ya da veri kaynakları farklı ligler bu yüzden grafikte kıyaslanamaz).')
            return
        self.radar_baslik.set_visibility(True)
        self.radar.set_visibility(True)
        self.radar.options['radar']['indicator'] = [{'name': x, 'max': 100} for x in ortak]
        self.radar.options['series'][0]['data'] = seriler
        self.radar.options['legend']['data'] = [s['name'] for s in self.radar.options['series'][0]['data']]
        self.radar.update()
        self.radar_not.text = ('Her eksen 0–100 arası yüzdelik dilim: oyuncunun kendi liginde ve sezonunda, aynı mevkideki (en az '
                               'eşik kadar oynamış) oyuncuların yüzde kaçının önünde olduğu. Farklı liglerdeki oyuncularda değerler '
                               'kendi liglerine görelidir.')

    def aktar(self):
        """Karşılaştırma tablosunun sayıları (ekrandaki görünümle) ve oyuncuların künyesi."""
        return _aktar_tablosu(self.d.get('liste') or [], self.d['p90'])

    def tablo_ciz(self, liste):
        self.tablo.content = _tablo_html(liste, self.d['p90'])
        self.tablo_not.text = _tablo_notu(liste, self.d['p90'])

    def yenile(self):
        S = self.G.S
        if self.lig_sec.value is None:  # ilk açılış: seçim alanı açık sezonla başlar
            self.lig_sec.set_value(S.lig)
            self.sezon_sec.set_options(sezon_secenekleri(S.lig), value=S.yil)
        self.G.arka_plan(self.ciz())
        self.G.arka_plan(self.takim_yenile())


def kur(G):
    return _Kiyas(G).yenile


# değerlendirmede istatistik gruplarının adı: "hücumda X önde", "X gol tehdidi konusunda öne çıkıyor"
GRUP_YERI = {'Hücum': 'hücumda', 'Yaratıcılık': 'yaratıcılıkta', 'Pas ve top sürme': 'pas ve top sürmede',
             'Savunma': 'savunmada', 'Kaleci': 'kalecilikte', 'Disiplin': 'disiplinde'}
GRUP_ANLAMI = {'Hücum': 'gol tehdidi', 'Yaratıcılık': 'pozisyon üretme', 'Pas ve top sürme': 'top hakimiyeti',
               'Savunma': 'savunma katkısı', 'Kaleci': 'kalecilik'}


def _ve(xs):
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' ve ' + xs[-1]


def _adi(adlar, i):
    return f'<b style="color:{RENKLER[i]}">{e(adlar[i])}</b>'


def _cikarim_genel(adlar, kartlar):
    """1) mevkidaşlara göre yüzdeliklerin ortak istatistiklerdeki ortalaması. Döner: (cümle ya da None, önde olan ya da None, ortak)."""
    n = len(adlar)
    A = lambda i: _adi(adlar, i)  # noqa: E731
    ortak = [k for k in kartlar[0] if all(k in y for y in kartlar[1:])]
    genel = None
    if len(ortak) < 3:
        return None, genel, ortak
    ort = [sum(y[k] for k in ortak) / len(ortak) for y in kartlar]
    sira = sorted(range(n), key=lambda i: -ort[i])
    fark = ort[sira[0]] - ort[sira[1]]
    if fark >= 2:
        genel = sira[0]
    derece = 'açık ara' if fark >= 15 else 'belirgin biçimde' if fark >= 8 else 'biraz'
    return (f'<b>Genel:</b> {len(ortak)} ortak istatistikte mevkidaşlarına göre ortalama yüzdelik: '
            + ', '.join(f'{A(i)} {round(ort[i])}' for i in sira) + '. '
            + (f'{A(genel)} {derece} önde.' if genel is not None else 'Genel düzeyleri neredeyse aynı.')), genel, ortak


def _cikarim_alanlar(oyuncular, adlar):
    """2) alan alan: 90 dakika başına kaç istatistikte önde. Döner: (cümle ya da None, liderler: en az iki istatistik farkla önde olunan alanlar)."""
    n = len(oyuncular)
    A = lambda i: _adi(adlar, i)  # noqa: E731
    sayac = {}
    for k, _, grup, tur in METRIKLER:
        if tur == 'sabit' or grup == 'Genel':
            continue
        vals = [deger(p, k, tur, True) for _, p in oyuncular]
        if any(v is None for v in vals) or len(set(vals)) == 1:
            continue
        lider = (min if k in AZI_IYI else max)(range(n), key=lambda i: vals[i])
        sayac.setdefault(grup, [0] * n)[lider] += 1
    liderler, parca = {}, []
    for grup, s in sayac.items():
        en = max(range(n), key=lambda i: s[i])
        if s.count(s[en]) > 1:
            parca.append(f'{GRUP_YERI[grup]} denge')
        else:
            if s[en] - sorted(s)[-2] >= 2:
                liderler[grup] = en
            parca.append(f'{GRUP_YERI[grup]} {A(en)} ({s[en]}/{sum(s)})')
    cumle = ('<b>Alan alan</b> (90 dakika başına, önde olduğu istatistik sayısı): ' + '; '.join(parca) + '.') if parca else None
    return cumle, liderler


def _cikarim_farklar(adlar, kartlar, ortak):
    """3) en belirgin farklar: yüzdelik farkı en büyük üç istatistik."""
    n = len(adlar)
    A = lambda i: _adi(adlar, i)  # noqa: E731
    farklar = []
    for k in sorted(ortak, key=lambda k: -(max(y[k] for y in kartlar) - min(y[k] for y in kartlar)))[:3]:
        ust = max(range(n), key=lambda i: kartlar[i][k])
        alt = min(range(n), key=lambda i: kartlar[i][k])
        if kartlar[ust][k] - kartlar[alt][k] >= 20:
            farklar.append(f'<i>{e(k)}</i>: {A(ust)} {kartlar[ust][k]}, {A(alt)} {kartlar[alt][k]}')
    return ('<b>En belirgin farklar</b> (yüzdelik): ' + '; '.join(farklar) + '.') if farklar else None


def _cikarim_guclu(adlar, kartlar):
    """4) güçlü yanlar: her oyuncunun mevkidaşlarına göre en yüksek iki yüzdeliği."""
    A = lambda i: _adi(adlar, i)  # noqa: E731
    guclu = []
    for i, y in enumerate(kartlar):
        iyi = [(k, pc) for k, pc in sorted(y.items(), key=lambda x: -x[1]) if pc >= 70][:2]
        guclu.append(f'{A(i)} ' + (_ve([f'{e(k)} ({pc})' for k, pc in iyi]) if iyi else 'belirgin bir üstün yanı yok'))
    return ('<b>Güçlü yanları:</b> ' + '; '.join(guclu) + '.') if any(kartlar) else None


def _cikarim_dikkat(oyuncular, adlar):
    """5) dikkat edilecekler."""
    n = len(oyuncular)
    A = lambda i: _adi(adlar, i)  # noqa: E731
    uyari = []
    dk = [p['min'] for _, p in oyuncular]
    az = [i for i, m in enumerate(dk) if m < 900 or m < max(dk) / 2]
    if az:
        uyari.append(_ve([f'{A(i)} ({sayi(dk[i])} dk)' for i in az]) + ' az süre aldı; 90 dakika başına değerleri daha oynak')
    if len({S.lig for S, _ in oyuncular}) > 1:
        uyari.append('oyuncular farklı liglerde: yüzdelikler kendi liglerine göre, lig seviyesi farkı hesaba katılmaz')
    if len({p['pos'] for _, p in oyuncular}) > 1:
        uyari.append('mevkileri farklı (' + ', '.join(mevki_adi(p) for _, p in oyuncular) + '); her biri kendi mevkidaşlarıyla '
                     'kıyaslandı, ham sayılar mevkinin rolünden etkilenir')
    yaslar = [(p.get('yas'), i) for i, (_, p) in enumerate(oyuncular) if p.get('yas') is not None]
    if len(yaslar) == n and max(yaslar)[0] - min(yaslar)[0] >= 4:
        uyari.append(f'yaş farkı {max(yaslar)[0] - min(yaslar)[0]}: en genç {A(min(yaslar)[1])} ({min(yaslar)[0]}), '
                     'gelişim payı daha fazla')
    return ('<b>Dikkat:</b> ' + '; '.join(uyari) + '.') if uyari else None


def _cikarim_sonuc(adlar, genel, liderler):
    """6) sonuç."""
    n = len(adlar)
    A = lambda i: _adi(adlar, i)  # noqa: E731
    alanlar = [[GRUP_ANLAMI[g] for g, l in liderler.items() if l == i and g in GRUP_ANLAMI] for i in range(n)]
    sonuc = []
    if genel is not None:
        sonuc.append(f'{A(genel)} genel olarak daha etkili' + (f', özellikle {_ve(alanlar[genel])} konusunda' if alanlar[genel] else '') + '.')
    for i in range(n):
        if i == genel:
            continue
        if alanlar[i]:
            sonuc.append(f'{A(i)} ise {_ve(alanlar[i])} konusunda öne çıkıyor.')
        elif genel is not None:
            sonuc.append(f'{A(i)} bu kıyasta belirgin bir alanda öne geçemiyor.')
    if n == 2 and all(alanlar):
        sonuc.append(f'{_ve(alanlar[0]).capitalize()} arayan bir takım için {A(0)}, {_ve(alanlar[1])} arayan için {A(1)} daha uygun.')
    if not sonuc:
        sonuc.append('Oyuncular birbirine çok yakın; seçim takımın ihtiyacına ve oyun tarzına bağlı.')
    return '<b>Sonuç:</b> ' + ' '.join(sonuc)


def cikarim(oyuncular, adlar):
    """Kıyaslanan oyunculardan kurallarla birkaç cümlelik değerlendirme (HTML cümleleri): genel üstünlük, alan alan kim
    önde, en belirgin farklar, güçlü yanlar, dikkat edilecekler ve sonuç. oyuncular: [(Sezon, oyuncu)], adlar: görünen adlar.
    Yeni kural eklemek: yukarıdaki _cikarim_* işlevlerinden birine ya da yeni bir tanesine cümle üret."""
    kartlar = [{y[0]: y[2] for y in S.oyuncu_karti(p)['yuzdelik']} for S, p in oyuncular]
    genel_cumle, genel, ortak = _cikarim_genel(adlar, kartlar)
    alan_cumle, liderler = _cikarim_alanlar(oyuncular, adlar)
    farklar = _cikarim_farklar(adlar, kartlar, ortak) if len(ortak) >= 3 else None
    cumleler = [genel_cumle, alan_cumle, farklar, _cikarim_guclu(adlar, kartlar), _cikarim_dikkat(oyuncular, adlar)]
    return [c for c in cumleler if c] + [_cikarim_sonuc(adlar, genel, liderler)]


def _ayni(a, b):
    return (a['lig'], a['yil']) == (b['lig'], b['yil']) and (
        (a['id'] is not None and a['id'] == b['id']) or (a['n'], a['t']) == (b['n'], b['t']))
