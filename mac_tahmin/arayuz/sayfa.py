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
from .ortak import CSS, KAYNAK, PALETLER, TEMALAR, UYGULAMA, hata_metni, lig_bilgi, lig_secenekleri, sezon_secenekleri

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

    def dinle(self, olay, fn):
        self._dinleyiciler.setdefault(olay, []).append(fn)

    def yay(self, olay):
        for fn in self._dinleyiciler.get(olay, []):
            sonuc = fn()
            if inspect.isawaitable(sonuc):
                self.arka_plan(sonuc)

    def arka_plan(self, coro):
        background_tasks.create(coro)


def sayfa(depo):
    ui.add_css(CSS)
    ui.colors(primary='#1c5b3e', secondary='#2f7a57', accent='#c9960f', positive='#2f7a57', negative='#b0413e')
    # görünüm (başlıktaki palet düğmesi): tema bilgisayara göre / açık / koyu, renk paleti (ortak.PALETLER)
    gorunum = dict(app.storage.general.get('gorunum') or {})
    karanlik = ui.dark_mode({'acik': False, 'koyu': True}.get(gorunum.get('tema')))
    palet0 = gorunum.get('palet') if gorunum.get('palet') in PALETLER else 'saha'
    ui.query('body').classes(add=f'palet-{palet0}')
    G = Gorunum(depo)
    hafiza = app.storage.general.get('son', {})
    lig0 = hafiza.get('lig', VARSAYILAN[0])
    if lig0 not in lig_secenekleri():
        lig0 = VARSAYILAN[0]
    yil0 = hafiza.get('yil', VARSAYILAN[1])
    if yil0 not in sezon_secenekleri(lig0):
        yil0 = SON_SEZON
    ilk_sekme = hafiza.get('sekme') if hafiza.get('sekme') in [m.ID for m in SEKMELER] else SEKMELER[0].ID

    def hatirla(**kv):
        app.storage.general['son'] = {**app.storage.general.get('son', {}), **kv}

    # ---------------------------------------------------------------- başlık
    with ui.row().classes('app-ust items-end'):
        with ui.column().classes('gap-0'):
            ui.html(f'<h1>{UYGULAMA}</h1>', sanitize=False)
            alt_baslik = ui.label().classes('alt')
        ui.space()
        # genel arama: takım ya da oyuncu adı (süren sezondaki bütün ligler ve Avrupa kupaları)
        with ui.input(placeholder='Takım ya da oyuncu ara').props('outlined dense clearable debounce=250').style(
                'min-width:230px') as ara_kutu:
            with ara_kutu.add_slot('prepend'):
                ui.icon('search')
            with ui.menu().props('no-focus no-refocus fit') as ara_menu:
                ara_liste = ui.column().classes('gap-0').style('min-width:300px')
        lig_sec = ui.select(lig_secenekleri(), value=lig0, label='Lig').props('outlined dense options-dense').style('min-width:270px')
        sezon_sec = ui.select(sezon_secenekleri(lig0), value=yil0, label='Sezon').props('outlined dense options-dense').style('min-width:150px')
        with ui.button(icon='palette').props('flat round dense').tooltip('Görünüm: tema ve renkler'):
            with ui.menu().props('auto-close=false'):
                with ui.column().classes('gap-2').style('padding:12px 14px;min-width:260px'):
                    ui.label('Tema').classes('cap').style('font-weight:600')
                    ui.toggle(TEMALAR, value=gorunum.get('tema') if gorunum.get('tema') in TEMALAR else 'oto',
                              on_change=lambda ev: tema_degisti(ev.value)).props('dense no-caps unelevated toggle-color=primary')
                    ui.label('Renkler').classes('cap').style('font-weight:600;margin-top:4px')
                    palet_liste = ui.list().props('dense').classes('w-full')
        durum = ui.label().classes('cap')

    def palet_ciz():
        palet_liste.clear()
        with palet_liste:
            for k, (ad, renk) in PALETLER.items():
                with ui.item(on_click=lambda _, k=k: palet_degisti(k)).props('clickable dense'):
                    with ui.item_section().props('avatar').style('min-width:30px'):
                        ui.icon('circle').style(f'color:{renk}')
                    with ui.item_section():
                        ui.item_label(ad)
                    with ui.item_section().props('side'):
                        if k == gorunum.get('palet', 'saha'):
                            ui.icon('check', color='primary')

    def tema_degisti(tema):
        karanlik.set_value({'acik': False, 'koyu': True}.get(tema))
        gorunum['tema'] = tema
        app.storage.general['gorunum'] = dict(gorunum)

    def palet_degisti(palet):
        ui.query('body').classes(remove=' '.join(f'palet-{k}' for k in PALETLER), add=f'palet-{palet}')
        gorunum['palet'] = palet
        app.storage.general['gorunum'] = dict(gorunum)
        palet_ciz()
    gorunum['palet'] = palet0
    palet_ciz()

    # ---------------------------------------------------------------- sekmeler
    with ui.tabs(value=ilk_sekme).classes('sekmeler').props(
            'align=left no-caps active-color=primary indicator-color=primary dense') as sekmeler:
        for m in SEKMELER:
            with ui.tab(m.ID, m.AD):
                if hasattr(m, 'sekme_ek'):
                    G.ek[m.ID] = m.sekme_ek()

    G.sekme_ac = sekmeler.set_value
    yenileyiciler = {}  # sekme ID -> yenile işlevi
    with ui.tab_panels(sekmeler, value=ilk_sekme).props('animated=false keep-alive').classes('w-full').style('background:transparent'):
        for m in SEKMELER:
            with ui.tab_panel(m.ID).classes('icerik'):
                yenileyiciler[m.ID] = m.kur(G)

    with ui.row().classes('alt-bilgi items-center gap-2'):
        kaynak = ui.label()
        ui.space()
        veri_durum = ui.label()
        guncelle_dugme = ui.button('Şimdi güncelle', icon='refresh', on_click=lambda: simdi()).props('flat dense no-caps size=sm')
        bicim_uyari = ui.label().classes('w-full').style('color:#e0a030')  # FotMob/Understat veri biçimi değiştiyse (sema.py)
        bicim_uyari.set_visibility(False)

    kart_ac = oyuncu_karti.kur(G)
    G.oyuncu_ac = lambda idx: G.arka_plan(kart_ac(idx=idx))
    mac_ac = mac_karti.kur(G)
    G.mac_ac = lambda m: G.arka_plan(mac_ac(m))
    takim_karti.kur(G)  # G.takim_ac(FotMob takım id'si ya da açık ligdeki takım adı)
    G.ayrintili_tahmin = mac_tahmini.kur(G)  # kupa ve milli maçların ayrıntılı tahmin penceresi

    # Tembel sekmeler (TEMBEL = True, ör. modeller: saniyeler süren eğitim) yalnızca açıkken yenilenir;
    # sezon değiştiğinde kapalıysa 'bayat' işaretlenir ve açıldığında yenilenir.
    bayat = set()

    async def sekme_yenile(m):
        sonuc = yenileyiciler[m.ID]()
        if inspect.isawaitable(sonuc):
            await sonuc

    async def hepsini_yenile():
        for m in SEKMELER:
            if getattr(m, 'TEMBEL', False) and sekmeler.value != m.ID:
                bayat.add(m.ID)
            else:
                bayat.discard(m.ID)
                G.arka_plan(sekme_yenile(m))
        G.yay('sezon')

    # ---------------------------------------------------------------- sezon yükleme
    secim = {'sessiz': False, 'hedef': None}

    async def yukle(lig, yil, oyuncu_id=None):
        durum.text = 'Yükleniyor…'
        try:
            S = await run.io_bound(G.depo.sezon, lig, yil)
        except Exception as ex:
            secim['hedef'] = None
            durum.text = 'Bu lig ve sezonun verisi yüklenemedi.'
            ui.notify(f'Veri yüklenemedi: {hata_metni(ex, "lig verisi")}', type='negative')
            return
        if secim['hedef'] != (lig, yil):  # bu sırada başka bir sezon seçildi
            return
        if not S.M:
            secim['hedef'] = None
            durum.text = 'Bu sezonda henüz oynanmış maç yok; önceki sezonu seç.'
            return
        G.S = S
        durum.text = ''
        hatirla(lig=lig, yil=yil)
        l = lig_bilgi(lig)
        alt_baslik.text = f'{l[1]} ({l[2]}) · {sezon_etiketi(yil, lig)}' + (' · sezon sürüyor' if S.U else '')
        kaynak.text = f'Veri kaynağı: {KAYNAK[S.src][1]}. Tahminler istatistiksel modeldir; kesin sonuç değildir.'
        await hepsini_yenile()
        if oyuncu_id is not None:
            await kart_ac(oyuncu_id=oyuncu_id)

    def istek(lig, yil, oyuncu_id=None):
        if secim['hedef'] == (lig, yil) and oyuncu_id is None:
            return
        secim['hedef'] = (lig, yil)
        G.arka_plan(yukle(lig, yil, oyuncu_id))

    def lig_degisti(ev):
        if secim['sessiz']:
            return
        sec = sezon_secenekleri(ev.value)
        y = sezon_sec.value if sezon_sec.value in sec else SON_SEZON
        secim['sessiz'] = True
        sezon_sec.set_options(sec, value=y)
        secim['sessiz'] = False
        istek(ev.value, y)

    def sezon_degisti(ev):
        if not secim['sessiz'] and ev.value is not None:
            istek(lig_sec.value, ev.value)

    lig_sec.on_value_change(lig_degisti)
    sezon_sec.on_value_change(sezon_degisti)

    def lige_gec(lig, yil, oyuncu_id=None):
        """Uygulamayı o lig ve sezona geçirir; oyuncu verildiyse kartı orada açılır."""
        secim['sessiz'] = True
        lig_sec.set_value(lig)
        sezon_sec.set_options(sezon_secenekleri(lig), value=yil)
        secim['sessiz'] = False
        istek(lig, yil, oyuncu_id)

    async def oyuncu_goster(lig, yil, oyuncu_id):
        """Oyuncunun kartı, açık lig ve sezon değişmeden (başka lig-sezonunsa o sezon arka planda kurulur): scout'ta, maç
        kartında, kariyer tablosunda başka ligden bir oyuncuya tıklayınca bulunulan sayfa kaybolmasın."""
        if G.S and (G.S.lig, G.S.yil) == (lig, yil):
            await kart_ac(oyuncu_id=oyuncu_id)
            return
        try:
            S = await run.io_bound(G.depo.sezon, lig, yil)
        except Exception as ex:
            ui.notify(f'Veri yüklenemedi: {hata_metni(ex, "lig verisi")}', type='negative')
            return
        if S is not None:
            await kart_ac(oyuncu_id=oyuncu_id, S=S)

    def git(lig, yil, oyuncu_id=None):
        """Oyuncu verildiyse kartını açık lig değişmeden açar (kartta "bu sezona geç" düğmesi var); verilmediyse o lig ve
        sezona geçer."""
        if oyuncu_id is not None:
            G.arka_plan(oyuncu_goster(lig, yil, oyuncu_id))
        else:
            lige_gec(lig, yil)
    G.git = git
    G.lige_gec = lige_gec

    async def sekme_degisti(ev):
        hatirla(sekme=ev.value)
        if ev.value in bayat and G.S:
            bayat.discard(ev.value)
            await sekme_yenile(next(m for m in SEKMELER if m.ID == ev.value))
    sekmeler.on_value_change(sekme_degisti)

    # ---------------------------------------------------------------- genel arama
    async def ara(ev):
        sorgu = ev.value or ''
        sonuc = await run.io_bound(G.depo.ara, sorgu) if len(sorgu.strip()) >= 2 else []
        if (ara_kutu.value or '') != sorgu:  # bu sırada yazılmaya devam edildi
            return
        ara_liste.clear()
        if not sonuc:
            ara_menu.close()
            return
        with ara_liste:
            for x in sonuc:
                with ui.item(on_click=lambda _, x=x: secildi(x)).props('dense clickable'):
                    with ui.item_section().props('avatar'):
                        if x['tur'] == 'takim':
                            ui.html(logo_html(takim_logo_url(x['tid']), bos='<span class="logo"></span>'), sanitize=False)
                        else:
                            ui.icon('person', size='sm').classes('text-grey-7')
                    with ui.item_section():
                        ui.item_label(x['ad'])
                        ui.item_label(('Takım · ' if x['tur'] == 'takim' else '') + x['ek']).props('caption')
        ara_menu.open()

    def secildi(x):
        ara_menu.close()
        ara_kutu.set_value('')
        if x['tur'] == 'takim':
            G.takim_ac(x['tid'])
        else:
            G.git(x['lig'], x['yil'], x['id'])

    ara_kutu.on_value_change(ara)

    # ---------------------------------------------------------------- kendini güncelleme
    def simdi():
        if not G.depo.g.simdi_guncelle():  # arka arkaya basılırsa kaynak sitelere yük binmesin
            ui.notify(f'Veriler az önce güncellendi. Yeni bir güncelleme için {G.depo.g.simdi_kalan_sn()} saniye sonra '
                      'tekrar dene.')
            return
        ui.notify('Süren sezonların, milli turnuvaların ve Avrupa kupalarının verisi indiriliyor; bitince açık sayfalar '
                  'kendiliğinden yenilenir.')

    izlenen = {'surum': G.depo.g.veri_surum, 'canli': None}

    async def takip():
        g = G.depo.g
        if g.veri_yenileniyor:
            veri_durum.text = 'Süren sezonların verisi yenileniyor…'
        elif g.son_veri:
            veri_durum.text = f'Süren sezon verisi: {g.son_veri:%d.%m %H:%M} · {g.veri_saat:g} saatte bir kendini yeniler'
        guncelle_dugme.set_enabled(not g.veri_yenileniyor)
        bicim_uyari.text = g.bicim_uyarisi()
        bicim_uyari.set_visibility(bool(bicim_uyari.text))
        if g.veri_surum != izlenen['surum']:  # süren sezonun verisi yenilendi
            izlenen['surum'] = g.veri_surum
            # açık lig yalnızca kendi verisi değiştiyse yeniden kurulur (başka ligde biten maç ekranı yenilemez)
            if G.S and G.S.yil == SON_SEZON and not G.depo.guncel_mi(G.S):
                secim['hedef'] = (G.S.lig, G.S.yil)
                await yukle(G.S.lig, G.S.yil)
                ui.notify('Süren sezonun verisi güncellendi.', type='positive')
        damga = (g.canli or {}).get('guncellendi')
        if damga != izlenen['canli']:
            izlenen['canli'] = damga
            G.yay('canli')

    ui.timer(15, takip)

    # favori takım bildirimleri: bildirim.kuyruk'taki yeniler bu pencerede de gösterilir
    gorulen = {'sira': bildirim.kuyruk[-1][0] if bildirim.kuyruk else 0}

    def bildirimleri_goster():
        for sira, _, baslik, metin in list(bildirim.kuyruk):
            if sira > gorulen['sira']:
                gorulen['sira'] = sira
                ui.notify(f'{baslik} · {metin}', type='info', position='top-right', timeout=15000, close_button='Kapat')

    ui.timer(5, bildirimleri_goster)
    istek(lig0, yil0)
