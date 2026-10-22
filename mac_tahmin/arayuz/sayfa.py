"""Uygulamanın tek sayfası: başlık, lig/sezon seçimi, sekmeler ve verilerin kendini güncellemesinin takibi.

Yeni sekme eklemek: arayuz/ altına bir modül yaz (ID, AD, kur(G) -> yenile; ayrıntı: GELISTIRME.md) ve aşağıdaki
SEKMELER listesine ekle. Sayfanın geri kalanına dokunmak gerekmez.
"""
import inspect

from nicegui import app, background_tasks, run, ui

from ..logo import logo_html, takim_logo_url
from ..sezon import SON_SEZON, sezon_etiketi
from . import (avrupa_sekme, bildirim, canli_sekme, guc, haftanin, karne_sekme, kiyas, mac_karti, milli_sekme, model_sekme,
               mac_tahmini, oyun, oyuncu_karti, oyuncular, scout, tablo, tahmin, takim_karti, takimlarim, yildizlar)
from .ortak import (CSS, KAYNAK, PALETLER, STILLER, TEMALAR, UYGULAMA, VARSAYILAN_STIL, hata_metni, lig_bilgi,
                    lig_secenekleri, sezon_secenekleri)
from .stil_modern import CSS_MODERN

# sekmeler, göründükleri sırayla
SEKMELER = [tahmin, canli_sekme, takimlarim, haftanin, avrupa_sekme, tablo, oyuncular, yildizlar, scout, kiyas, guc, model_sekme,
            karne_sekme, oyun, milli_sekme]
VARSAYILAN = ('Super_Lig', SON_SEZON)


class Gorunum:
    """Bir pencerenin durumu ve sekmeler arası bağlantılar.

    S: açık sezon (sezon.Sezon; S.raw ham veri, S.sim simülasyon önbelleği). depo: veri deposu (depo.Depo).
    Olaylar: G.dinle(ad, fn) ile abone olunur, G.yay(ad) ile duyurulur. Şimdilik:
      'sezon'  açık sezon değişti ya da yeniden kuruldu      'canli'  yeni canlı skor verisi geldi
    Diğer sekmelere açılan işlevler: G.oyuncu_ac(idx), G.mac_ac(mac) (canlı skor verisindeki bir maçın kartı),
    G.git(lig, yil, oyuncu_id=None) (oyuncuyla: kartı açık lig değişmeden; oyuncusuz: o lig ve sezona geçer),
    G.lige_gec(lig, yil, oyuncu_id=None), G.sekme_ac(sekme_id), G.kiyasa_ekle(lig, yil, oyuncu), G.arka_plan(coro),
    G.takim_ac(FotMob takım id'si ya da açık ligdeki takım adı) (HTML içinde: ortak.takim_link + ortak.takim_tiklama).
    """

    def __init__(self, depo):
        self.depo = depo
        self.S = None
        self.ek = {}  # sekmelerin başlığa eklediği öğeler (ör. canlı maç sayısı rozeti)
        self._dinleyiciler = {}
        self.oyuncu_ac = lambda idx: None
        self.mac_ac = lambda mac: None
        self.git = lambda lig, yil, oyuncu_id=None: None
        self.lige_gec = lambda lig, yil, oyuncu_id=None: None
        self.sekme_ac = lambda sekme_id: None
        self.kiyasa_ekle = lambda lig, yil, oyuncu: None
        self.takim_ac = lambda anahtar: None
        self.tahmin_ac = lambda lig, ev, dep: None  # maç tahmini sekmesinde bu maçı aç
        self.bekleyen_tahmin = None
        self.ayrintili_tahmin = lambda bilgi: None  # kupa / milli maçın ayrıntılı tahmini (arayuz/mac_tahmini.py)
        self.avrupa_mac_ac = lambda kupa_id, mac_id: None  # canlı skordan kupa maçının ayrıntılı tahmini (avrupa_sekme)
        self.milli_mac_ac = lambda turnuva_id, mac_id: None  # canlı skordan milli maçın ayrıntılı tahmini (milli_sekme)
        self.kart_kapatanlar = []  # kulüp ve oyuncu kartının kapatıcıları (kartlar kendini kurarken ekler)

    def kartlari_kapat(self):
        """Açık kulüp / oyuncu kartlarını kapatır: bir sekmeye geçilirken (ör. lig maçının tahmini) önde kalmasınlar."""
        for kapat in self.kart_kapatanlar:
            kapat()

    def dinle(self, olay, fn):
        self._dinleyiciler.setdefault(olay, []).append(fn)

    def yay(self, olay):
        for fn in self._dinleyiciler.get(olay, []):
            sonuc = fn()
            if inspect.isawaitable(sonuc):
                self.arka_plan(sonuc)

    def arka_plan(self, coro):
        background_tasks.create(coro)


class _Sayfa:
    """Uygulamanın tek sayfası: başlık, sekmeler, alt bilgi ve bunları bağlayan lig / sezon yükleme, genel arama,
    kendini güncelleme takibi. Her pencere (tarayıcı sekmesi) için bir tane kurulur."""

    def __init__(self, depo):
        ui.add_css(CSS)
        ui.add_css(CSS_MODERN)  # yalnızca body.stil-modern altında etkili
        ui.colors(primary='#1c5b3e', secondary='#2f7a57', accent='#c9960f', positive='#2f7a57', negative='#b0413e')
        # görünüm (başlıktaki palet düğmesi): tema bilgisayara göre / açık / koyu, renk paleti (ortak.PALETLER)
        self.gorunum = dict(app.storage.general.get('gorunum') or {})
        self.karanlik = ui.dark_mode({'acik': False, 'koyu': True}.get(self.gorunum.get('tema')))
        palet0 = self.gorunum.get('palet') if self.gorunum.get('palet') in PALETLER else 'saha'
        stil0 = self.gorunum.get('stil') if self.gorunum.get('stil') in STILLER else VARSAYILAN_STIL
        ui.query('body').classes(add=f'palet-{palet0}' + (' stil-modern' if stil0 == 'modern' else ''))
        self.G = G = Gorunum(depo)
        hafiza = app.storage.general.get('son', {})
        lig0 = hafiza.get('lig', VARSAYILAN[0])
        if lig0 not in lig_secenekleri():
            lig0 = VARSAYILAN[0]
        yil0 = hafiza.get('yil', VARSAYILAN[1])
        if yil0 not in sezon_secenekleri(lig0):
            yil0 = SON_SEZON
        ilk_sekme = hafiza.get('sekme') if hafiza.get('sekme') in [m.ID for m in SEKMELER] else SEKMELER[0].ID
        self.bayat = set()  # tembel sekmeler: sezon değişince kapalıysa burada bekler, açılınca yenilenir
        self.secim = {'sessiz': False, 'hedef': None}
        self.izlenen = {'surum': depo.g.veri_surum, 'canli': None}
        self.gorulen = {'sira': bildirim.kuyruk[-1][0] if bildirim.kuyruk else 0}

        self._baslik_kur(lig0, yil0)
        self.gorunum['palet'] = palet0
        self.palet_ciz()
        self._sekmeler_kur(ilk_sekme)
        self._alt_bilgi_kur()

        self.kart_ac = oyuncu_karti.kur(G)
        G.oyuncu_ac = lambda idx: G.arka_plan(self.kart_ac(idx=idx))
        mac_ac = mac_karti.kur(G)
        G.mac_ac = lambda m: G.arka_plan(mac_ac(m))
        takim_karti.kur(G)  # G.takim_ac(FotMob takım id'si ya da açık ligdeki takım adı)
        G.ayrintili_tahmin = mac_tahmini.kur(G)  # kupa ve milli maçların ayrıntılı tahmin penceresi

        self.lig_sec.on_value_change(self.lig_degisti)
        self.sezon_sec.on_value_change(self.sezon_degisti)
        G.git = self.git
        G.lige_gec = self.lige_gec
        self.sekmeler.on_value_change(self.sekme_degisti)
        self.ara_kutu.on_value_change(self.ara)
        ui.timer(15, self.takip)
        ui.timer(5, self.bildirimleri_goster)  # favori takım bildirimleri: bildirim.kuyruk'taki yeniler bu pencerede de gösterilir
        self.istek(lig0, yil0)

    def hatirla(self, **kv):
        app.storage.general['son'] = {**app.storage.general.get('son', {}), **kv}

    # ---------------------------------------------------------------- arayüz iskeleti
    def _baslik_kur(self, lig0, yil0):
        gorunum = self.gorunum
        with ui.row().classes('app-ust items-end'):
            with ui.column().classes('gap-0'):
                ui.html(f'<h1>{UYGULAMA}</h1>', sanitize=False)
                self.alt_baslik = ui.label().classes('alt').mark('alt-baslik')
            ui.space()
            # genel arama: takım ya da oyuncu adı (süren sezondaki bütün ligler ve Avrupa kupaları)
            with ui.input(placeholder='Takım ya da oyuncu ara').props('outlined dense clearable debounce=250').style(
                    'min-width:230px') as self.ara_kutu:
                with self.ara_kutu.add_slot('prepend'):
                    ui.icon('search')
                with ui.menu().props('no-focus no-refocus fit') as self.ara_menu:
                    self.ara_liste = ui.column().classes('gap-0').style('min-width:300px')
            self.lig_sec = ui.select(lig_secenekleri(), value=lig0, label='Lig').props('outlined dense options-dense').style(
                'min-width:270px')
            self.sezon_sec = ui.select(sezon_secenekleri(lig0), value=yil0, label='Sezon').props(
                'outlined dense options-dense').style('min-width:150px')
            with ui.button(icon='palette').props('flat round dense').tooltip('Görünüm: tema ve renkler'):
                with ui.menu().props('auto-close=false'):
                    with ui.column().classes('gap-2').style('padding:12px 14px;min-width:260px'):
                        ui.label('Stil').classes('cap').style('font-weight:600')
                        ui.toggle(STILLER, value=gorunum.get('stil') if gorunum.get('stil') in STILLER else VARSAYILAN_STIL,
                                  on_change=lambda ev: self.stil_degisti(ev.value)).props(
                            'dense no-caps unelevated toggle-color=primary')
                        ui.label('Tema').classes('cap').style('font-weight:600')
                        ui.toggle(TEMALAR, value=gorunum.get('tema') if gorunum.get('tema') in TEMALAR else 'oto',
                                  on_change=lambda ev: self.tema_degisti(ev.value)).props(
                            'dense no-caps unelevated toggle-color=primary')
                        ui.label('Renkler').classes('cap').style('font-weight:600;margin-top:4px')
                        self.palet_liste = ui.list().props('dense').classes('w-full')
            self.durum = ui.label().classes('cap')

    def _sekmeler_kur(self, ilk_sekme):
        G = self.G
        with ui.tabs(value=ilk_sekme).classes('sekmeler').props(
                'align=left no-caps active-color=primary indicator-color=primary dense') as self.sekmeler:
            for m in SEKMELER:
                with ui.tab(m.ID, m.AD):
                    if hasattr(m, 'sekme_ek'):
                        G.ek[m.ID] = m.sekme_ek()

        G.sekme_ac = self.sekmeler.set_value
        self.yenileyiciler = {}  # sekme ID -> yenile işlevi
        with ui.tab_panels(self.sekmeler, value=ilk_sekme).props('animated=false keep-alive').classes('w-full').style(
                'background:transparent'):
            for m in SEKMELER:
                with ui.tab_panel(m.ID).classes('icerik'):
                    self.yenileyiciler[m.ID] = m.kur(G)

    def _alt_bilgi_kur(self):
        with ui.row().classes('alt-bilgi items-center gap-2'):
            self.kaynak = ui.label()
            ui.space()
            self.veri_durum = ui.label()
            self.guncelle_dugme = ui.button('Şimdi güncelle', icon='refresh', on_click=lambda: self.simdi()).props(
                'flat dense no-caps size=sm')
            self.bicim_uyari = ui.label().classes('w-full').style('color:#e0a030')  # FotMob/Understat veri biçimi değiştiyse (sema.py)
            self.bicim_uyari.set_visibility(False)

    # ---------------------------------------------------------------- görünüm
    def palet_ciz(self):
        self.palet_liste.clear()
        with self.palet_liste:
            for k, (ad, renk) in PALETLER.items():
                with ui.item(on_click=lambda _, k=k: self.palet_degisti(k)).props('clickable dense'):
                    with ui.item_section().props('avatar').style('min-width:30px'):
                        ui.icon('circle').style(f'color:{renk}')
                    with ui.item_section():
                        ui.item_label(ad)
                    with ui.item_section().props('side'):
                        if k == self.gorunum.get('palet', 'saha'):
                            ui.icon('check', color='primary')

    def tema_degisti(self, tema):
        self.karanlik.set_value({'acik': False, 'koyu': True}.get(tema))
        self.gorunum['tema'] = tema
        app.storage.general['gorunum'] = dict(self.gorunum)

    def stil_degisti(self, stil):
        """Klasik / modern görünüm: body'deki stil-modern sınıfı (yeniden yüklemeden uygulanır) ve kalıcı ayar."""
        if stil not in STILLER:
            return
        if stil == 'modern':
            ui.query('body').classes(add='stil-modern')
        else:
            ui.query('body').classes(remove='stil-modern')
        self.gorunum['stil'] = stil
        app.storage.general['gorunum'] = dict(self.gorunum)

    def palet_degisti(self, palet):
        ui.query('body').classes(remove=' '.join(f'palet-{k}' for k in PALETLER), add=f'palet-{palet}')
        self.gorunum['palet'] = palet
        app.storage.general['gorunum'] = dict(self.gorunum)
        self.palet_ciz()

    # ---------------------------------------------------------------- sezon yükleme
    async def sekme_yenile(self, m):
        sonuc = self.yenileyiciler[m.ID]()
        if inspect.isawaitable(sonuc):
            await sonuc

    async def hepsini_yenile(self):
        """Tembel sekmeler (TEMBEL = True, ör. modeller: saniyeler süren eğitim) yalnızca açıkken yenilenir; sezon
        değiştiğinde kapalıysa 'bayat' işaretlenir ve açıldığında yenilenir."""
        for m in SEKMELER:
            if getattr(m, 'TEMBEL', False) and self.sekmeler.value != m.ID:
                self.bayat.add(m.ID)
            else:
                self.bayat.discard(m.ID)
                self.G.arka_plan(self.sekme_yenile(m))
        self.G.yay('sezon')

    async def yukle(self, lig, yil, oyuncu_id=None):
        G, secim = self.G, self.secim
        self.durum.text = 'Yükleniyor…'
        try:
            S = await run.io_bound(G.depo.sezon, lig, yil)
        except Exception as ex:
            secim['hedef'] = None
            self.durum.text = 'Bu lig ve sezonun verisi yüklenemedi.'
            ui.notify(f'Veri yüklenemedi: {hata_metni(ex, "lig verisi")}', type='negative')
            return
        if secim['hedef'] != (lig, yil):  # bu sırada başka bir sezon seçildi
            return
        if not S.M:
            secim['hedef'] = None
            self.durum.text = 'Bu sezonda henüz oynanmış maç yok; önceki sezonu seç.'
            return
        G.S = S
        self.durum.text = ''
        self.hatirla(lig=lig, yil=yil)
        l = lig_bilgi(lig)
        self.alt_baslik.text = f'{l[1]} ({l[2]}) · {sezon_etiketi(yil, lig)}' + (' · sezon sürüyor' if S.U else '')
        self.kaynak.text = f'Veri kaynağı: {KAYNAK[S.src][1]}. Tahminler istatistiksel modeldir; kesin sonuç değildir.'
        await self.hepsini_yenile()
        if oyuncu_id is not None:
            await self.kart_ac(oyuncu_id=oyuncu_id)

    def istek(self, lig, yil, oyuncu_id=None):
        if self.secim['hedef'] == (lig, yil) and oyuncu_id is None:
            return
        self.secim['hedef'] = (lig, yil)
        self.G.arka_plan(self.yukle(lig, yil, oyuncu_id))

    def lig_degisti(self, ev):
        if self.secim['sessiz']:
            return
        sec = sezon_secenekleri(ev.value)
        y = self.sezon_sec.value if self.sezon_sec.value in sec else SON_SEZON
        self.secim['sessiz'] = True
        self.sezon_sec.set_options(sec, value=y)
        self.secim['sessiz'] = False
        self.istek(ev.value, y)

    def sezon_degisti(self, ev):
        if not self.secim['sessiz'] and ev.value is not None:
            self.istek(self.lig_sec.value, ev.value)

    def lige_gec(self, lig, yil, oyuncu_id=None):
        """Uygulamayı o lig ve sezona geçirir; oyuncu verildiyse kartı orada açılır."""
        self.secim['sessiz'] = True
        self.lig_sec.set_value(lig)
        self.sezon_sec.set_options(sezon_secenekleri(lig), value=yil)
        self.secim['sessiz'] = False
        self.istek(lig, yil, oyuncu_id)

    async def oyuncu_goster(self, lig, yil, oyuncu_id):
        """Oyuncunun kartı, açık lig ve sezon değişmeden (başka lig-sezonunsa o sezon arka planda kurulur): scout'ta, maç
        kartında, kariyer tablosunda başka ligden bir oyuncuya tıklayınca bulunulan sayfa kaybolmasın."""
        G = self.G
        if G.S and (G.S.lig, G.S.yil) == (lig, yil):
            await self.kart_ac(oyuncu_id=oyuncu_id)
            return
        try:
            S = await run.io_bound(G.depo.sezon, lig, yil)
        except Exception as ex:
            ui.notify(f'Veri yüklenemedi: {hata_metni(ex, "lig verisi")}', type='negative')
            return
        if S is not None:
            await self.kart_ac(oyuncu_id=oyuncu_id, S=S)

    def git(self, lig, yil, oyuncu_id=None):
        """Oyuncu verildiyse kartını açık lig değişmeden açar (kartta "bu sezona geç" düğmesi var); verilmediyse o lig ve
        sezona geçer."""
        if oyuncu_id is not None:
            self.G.arka_plan(self.oyuncu_goster(lig, yil, oyuncu_id))
        else:
            self.lige_gec(lig, yil)

    async def sekme_degisti(self, ev):
        self.hatirla(sekme=ev.value)
        if ev.value in self.bayat and self.G.S:
            self.bayat.discard(ev.value)
            await self.sekme_yenile(next(m for m in SEKMELER if m.ID == ev.value))

    # ---------------------------------------------------------------- genel arama
    async def ara(self, ev):
        G = self.G
        sorgu = ev.value or ''
        sonuc = await run.io_bound(G.depo.ara, sorgu) if len(sorgu.strip()) >= 2 else []
        if (self.ara_kutu.value or '') != sorgu:  # bu sırada yazılmaya devam edildi
            return
        self.ara_liste.clear()
        if not sonuc:
            self.ara_menu.close()
            return
        with self.ara_liste:
            for x in sonuc:
                with ui.item(on_click=lambda _, x=x: self.secildi(x)).props('dense clickable'):
                    with ui.item_section().props('avatar'):
                        if x['tur'] == 'takim':
                            ui.html(logo_html(takim_logo_url(x['tid']), bos='<span class="logo"></span>'), sanitize=False)
                        else:
                            ui.icon('person', size='sm').classes('text-grey-7')
                    with ui.item_section():
                        ui.item_label(x['ad'])
                        ui.item_label(('Takım · ' if x['tur'] == 'takim' else '') + x['ek']).props('caption')
        self.ara_menu.open()

    def secildi(self, x):
        self.ara_menu.close()
        self.ara_kutu.set_value('')
        if x['tur'] == 'takim':
            self.G.takim_ac(x['tid'])
        else:
            self.G.git(x['lig'], x['yil'], x['id'])

    # ---------------------------------------------------------------- kendini güncelleme
    def simdi(self):
        if not self.G.depo.g.simdi_guncelle():  # arka arkaya basılırsa kaynak sitelere yük binmesin
            ui.notify(f'Veriler az önce güncellendi. Yeni bir güncelleme için {self.G.depo.g.simdi_kalan_sn()} saniye sonra '
                      'tekrar dene.')
            return
        ui.notify('Süren sezonların, milli turnuvaların ve Avrupa kupalarının verisi indiriliyor; bitince açık sayfalar '
                  'kendiliğinden yenilenir.')

    async def takip(self):
        G, izlenen = self.G, self.izlenen
        g = G.depo.g
        if g.veri_yenileniyor:
            self.veri_durum.text = 'Süren sezonların verisi yenileniyor…'
        elif g.son_veri:
            self.veri_durum.text = f'Süren sezon verisi: {g.son_veri:%d.%m %H:%M} · {g.veri_saat:g} saatte bir kendini yeniler'
        self.guncelle_dugme.set_enabled(not g.veri_yenileniyor)
        self.bicim_uyari.text = g.bicim_uyarisi()
        self.bicim_uyari.set_visibility(bool(self.bicim_uyari.text))
        if g.veri_surum != izlenen['surum']:  # süren sezonun verisi yenilendi
            izlenen['surum'] = g.veri_surum
            # açık lig yalnızca kendi verisi değiştiyse yeniden kurulur (başka ligde biten maç ekranı yenilemez)
            if G.S and G.S.yil == SON_SEZON and not G.depo.guncel_mi(G.S):
                self.secim['hedef'] = (G.S.lig, G.S.yil)
                await self.yukle(G.S.lig, G.S.yil)
                ui.notify('Süren sezonun verisi güncellendi.', type='positive')
        damga = (g.canli or {}).get('guncellendi')
        if damga != izlenen['canli']:
            izlenen['canli'] = damga
            G.yay('canli')

    def bildirimleri_goster(self):
        for sira, _, baslik, metin in list(bildirim.kuyruk):
            if sira > self.gorulen['sira']:
                self.gorulen['sira'] = sira
                ui.notify(f'{baslik} · {metin}', type='info', position='top-right', timeout=15000, close_button='Kapat')


def sayfa(depo):
    _Sayfa(depo)
