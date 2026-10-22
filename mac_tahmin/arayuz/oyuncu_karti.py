"""Oyuncu kartı penceresi: özet, mevkidaşlara göre yüzdelikler, ayrıntılar, benzer oyuncular ve sezon geçmişi."""
import logging

from nicegui import run, ui

from .. import lig_maclari, oyuncu_tahmin, takim
from ..bicim import para as _para
from ..sezon import LIGLER, SON_SEZON, benzer_esik, benzer_oyuncular, kariyer, mevki_adi, sezon_etiketi
from . import takip
from .oyuncu_karti_html import (ayrinti_html, benzer_notu, benzer_suz_uygula, deger_grafik_secenekleri, deger_isaretleri, deger_notu,
                                fiziksel_html, fiziksel_notu, gelisim_grafik_secenekleri, gelisim_notu, istikrar_html, kulvar_html,
                                KULVAR_NOTU, kutular_html, meta_metni, ozel_html, rozet_html, son_grafik_secenekleri,
                                son_maclar_html, son_maclar_notu, sut_haritasi, sut_notu, yuzdelik_bilgi)
from .ortak import e, fmt, hata_metni, lig_bilgi, sayi, takim_tiklama

logger = logging.getLogger(__name__)

FIZIKSEL_LIGLER = {'EPL'}  # FotMob'un fiziksel veri (koşu, sprint, hız) verdiği ligler
BENZER_SUZGEC = {'': 'Hepsi', 'genc': 'Daha genç', 'ucuz': 'Daha ucuz'}  # "daha ucuz" yalnızca süren sezonda
GELISIM_SEZON = 10  # gelişim grafiğinde en çok bu kadar son sezon


class _Kart:
    """Oyuncu kartı penceresi: öğeler özniteliklerde, yüklemeler (FotMob verisi, benzerler, kariyer) arka planda
    çalışan yöntemler. d['istek']: eski bir oyuncunun geç gelen verisi yenisinin üstüne yazılmasın."""

    def __init__(self, G):
        self.G = G
        self.d = {'p': None, 'kapsam': 'lig', 'istek': 0, 'benzer_suz': ''}
        with ui.dialog().props('transition-show=fade transition-hide=fade') as self.dlg, \
                ui.card().classes('w-full gap-3').style('max-width:860px;background:var(--panel);color:var(--ink)'):
            self._iskelet_ust()
            self._iskelet_son_maclar()
            self._iskelet_benzer_gecmis()

    # ---------------------------------------------------------------- arayüz iskeleti
    def _iskelet_ust(self):
        with ui.row().classes('w-full items-start no-wrap'):
            with ui.column().classes('gap-0 grow'):
                self.ad = ui.label().classes('disp').style('font-size:2rem;font-weight:700;line-height:1.1')
                self.meta = ui.label().classes('cap')
                self.ozel = ui.html('', sanitize=False)
            self.rozet = ui.html('', sanitize=False).style('text-align:center')
            self.takip_dugme = ui.button('Takip et', icon='visibility', on_click=lambda: self.takip_et()).props(
                'flat dense no-caps color=accent').tooltip('Takip listene ekle: gol / asist, değer ve sözleşme bildirimleri; '
                                                          'liste Takımlarım sekmesinde')
            ui.button('Kıyasla', icon='compare_arrows', on_click=lambda: self.kiyasla()).props(
                'flat dense no-caps color=primary').tooltip('Bu oyuncuyu Kıyasla sekmesine ekle')
            ui.button(icon='close', on_click=self.dlg.close).props('flat round dense')
        # başka lig-sezonun oyuncusu açık lig değişmeden gösterilir; istenirse uygulama o sezona geçer
        self.gec_dugme = ui.button('', icon='open_in_new', on_click=lambda: self.sezona_gec()).props(
            'flat dense no-caps color=primary size=sm').tooltip('Uygulamayı bu oyuncunun lig ve sezonuna geçir')
        self.gec_dugme.set_visibility(False)
        self.kutular = ui.html('', sanitize=False).classes('w-full')
        with ui.row().classes('w-full gap-6 items-start'):
            with ui.column().classes('gap-1').style('flex:1 1 360px'):
                ui.label('Mevkidaşlarına göre').classes('disp text-lg font-bold')
                self.yuzdelik = ui.html('', sanitize=False).classes('w-full')
                self.yuzdelik_not = ui.label().classes('cap')
            with ui.column().classes('gap-1').style('flex:1 1 260px'):
                ui.label('Ayrıntılar').classes('disp text-lg font-bold')
                self.ayrinti = ui.html('', sanitize=False).classes('w-full')
        with ui.column().classes('w-full gap-1') as self.fiz_bolum:
            ui.label('Fiziksel (bu sezon)').classes('disp text-lg font-bold')
            self.fiz_kutu = ui.html('', sanitize=False).classes('w-full')
            self.fiz_not = ui.label().classes('cap')

    def _iskelet_son_maclar(self):
        ui.label('Son maçları').classes('disp text-lg font-bold')
        self.son_not = ui.label().classes('cap')
        self.istikrar_not = ui.html('', sanitize=False).classes('w-full')
        self.son_grafik = ui.echart(son_grafik_secenekleri()).classes('w-full').style('height:240px')
        self.son_tablo = ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:260px;overflow-y:auto')
        with ui.row().classes('w-full gap-6 items-start') as self.deger_sut:
            with ui.column().classes('gap-1').style('flex:1 1 300px;max-width:360px'):
                ui.label('Şut haritası (güncel sezon)').classes('disp text-lg font-bold')
                self.sut_kutu = ui.html('', sanitize=False).classes('w-full')
                self.sut_not = ui.label().classes('cap')
            with ui.column().classes('gap-1').style('flex:2 1 360px'):
                ui.label('Piyasa değeri geçmişi').classes('disp text-lg font-bold')
                self.deger_grafik = ui.echart(deger_grafik_secenekleri()).classes('w-full').style('height:240px')
                self.deger_not = ui.label().classes('cap')
        self.deger_sut.set_visibility(False)

    def _iskelet_benzer_gecmis(self):
        with ui.row().classes('w-full items-center gap-2'):
            ui.label('Benzer oyuncular').classes('disp text-lg font-bold')
            ui.space()
            self.benzer_suz = ui.toggle(BENZER_SUZGEC, value='', on_change=lambda ev: self.suzgec_degisti(ev.value)).props(
                'dense no-caps unelevated toggle-color=primary')
            self.kapsam = ui.toggle({'lig': 'Bu lig', 'tum': 'Tüm ligler'}, value='lig',
                                    on_change=lambda ev: self.kapsam_degisti(ev.value)).props(
                'dense no-caps unelevated toggle-color=primary')
        self.benzer = ui.column().classes('liste')
        self.benzer_not = ui.label().classes('cap')
        with ui.column().classes('w-full gap-1') as self.gelisim_bolum:
            ui.label('Gelişim (sezon sezon, uygulamadaki ligler)').classes('disp text-lg font-bold')
            self.gelisim_grafik = ui.echart(gelisim_grafik_secenekleri()).classes('w-full').style('height:250px')
            self.gelisim_not = ui.label().classes('cap')
        self.gelisim_bolum.set_visibility(False)
        with ui.row().classes('w-full items-center'):
            ui.label('Sezon geçmişi').classes('disp text-lg font-bold')
            ui.space()
            self.gecmis_gorunum = ui.toggle({'tum': 'Bütün kulvarlar', 'lig': 'Lig ayrıntısı (dakika, xG)'}, value='tum',
                                            on_change=lambda _: self.gorunum_degisti()).props(
                'dense no-caps unelevated toggle-color=primary')
        self.tum_kutu = takim_tiklama(ui.html('', sanitize=False).classes('w-full kaydir').style('max-height:480px;overflow-y:auto'),
                                      self.G)
        self.tum_not = ui.label().classes('cap')
        with ui.column().classes('w-full gap-0') as self.lig_bolum:
            self.kariyer_kutu = ui.column().classes('w-full gap-0 kaydir')
            self.kariyer_not = ui.label().classes('cap')

    # ---------------------------------------------------------------- düğmeler
    def gorunum_degisti(self):
        tum = self.gecmis_gorunum.value == 'tum'
        self.tum_kutu.set_visibility(tum)
        self.tum_not.set_visibility(tum)
        self.lig_bolum.set_visibility(not tum)

    def kiyasla(self):
        d = self.d
        if d['p'] is not None:
            self.dlg.close()
            self.G.kiyasa_ekle(d['S'].lig, d['S'].yil, d['p'])

    def sezona_gec(self):
        d = self.d
        if d['p'] is not None:
            self.G.lige_gec(d['S'].lig, d['S'].yil, d['p']['id'])

    def takip_ciz(self):
        p = self.d['p']
        self.takip_dugme.set_visibility(bool(p and p.get('fm_id')))
        var = bool(p and p.get('fm_id') and takip.takipte_mi(p['fm_id']))
        self.takip_dugme.text = 'Takipte' if var else 'Takip et'
        self.takip_dugme.props(f'icon={"visibility_off" if var else "visibility"}')

    def takip_et(self):
        d = self.d
        p = d['p']
        if p is None or not p.get('fm_id'):
            return
        eklendi = takip.degistir(p, d['S'].lig, d['S'].yil)
        self.takip_ciz()
        ui.notify(f'{p["n"]} takip listene eklendi: gol / asist, değer ve sözleşme değişikliklerinde bildirim alırsın '
                  '(liste Takımlarım sekmesinde).' if eklendi else f'{p["n"]} takip listenden çıkarıldı.')
        self.G.yay('takip')

    def kapsam_degisti(self, k):
        self.d['kapsam'] = k
        if self.d['p'] is not None:
            self.G.arka_plan(self.benzer_yukle(self.d['p'], self.d['istek']))

    def suzgec_degisti(self, k):
        self.d['benzer_suz'] = k or ''
        if self.d['p'] is not None:
            self.G.arka_plan(self.benzer_yukle(self.d['p'], self.d['istek']))

    # ---------------------------------------------------------------- kartı aç
    def _ozet_doldur(self, S, p):
        """Başlık, rozet, kutular, mevkidaşlara göre yüzdelikler ve ayrıntılar (hepsi hemen hesaplanır)."""
        k = S.oyuncu_karti(p)
        self.ad.text = p['n']
        self.meta.text = meta_metni(p, S)
        self.ozel.content = ozel_html(p)
        self.rozet.content = rozet_html(p, k)
        self.kutular.content = kutular_html(p)
        self.yuzdelik.content, self.yuzdelik_not.text = yuzdelik_bilgi(k, p, S)
        self.ayrinti.content = ayrinti_html(k, p)

    def _bos_yukleniyor(self, S, p):
        """Arka planda yüklenecek bölümleri "yükleniyor" durumuna al."""
        self.gelisim_bolum.set_visibility(False)
        self.benzer.clear()
        self.benzer_not.text = 'Benzer oyuncular aranıyor…'
        self.kariyer_kutu.clear()
        self.kariyer_not.text = 'Diğer sezonlar yükleniyor…'
        self.tum_kutu.content = ''
        self.tum_not.text = 'Bütün kulvarlardaki sezonlar alınıyor…' if p.get('fm_id') else 'Bu oyuncunun FotMob kaydı bulunamadı.'
        if not p.get('fm_id'):
            self.gecmis_gorunum.set_value('lig')
        self.gorunum_degisti()
        self.son_not.text = 'Son maçlar alınıyor…' if p.get('fm_id') else 'Bu oyuncunun FotMob kaydı bulunamadı.'
        self.son_tablo.content = ''
        self.son_grafik.options['xAxis']['data'] = []
        for s in self.son_grafik.options['series']:
            s['data'] = []
        self.son_grafik.update()
        self.fiz_kutu.content = ''
        self.fiz_bolum.set_visibility(S.lig in FIZIKSEL_LIGLER and S.yil == SON_SEZON and bool(p.get('fm_id')))

    async def ac(self, idx=None, oyuncu_id=None, S=None):
        """Oyuncunun kartı. S: oyuncunun sezonu (verilmezse açık sezon); başka lig-sezonun oyuncusu açık lig değişmeden
        gösterilir, başlıkta "bu sezona geç" düğmesi çıkar."""
        G, d = self.G, self.d
        S = S or G.S
        if oyuncu_id is not None:
            p = next((q for q in S.PLY if q['id'] == oyuncu_id), None)
        else:
            p = S.PLY[idx] if 0 <= idx < len(S.PLY) else None
        if p is None:
            return
        d['p'], d['S'] = p, S
        baska = G.S is None or (G.S.lig, G.S.yil) != (S.lig, S.yil)
        self.gec_dugme.set_visibility(baska)
        if baska:
            self.gec_dugme.text = f'{lig_bilgi(S.lig)[1]} {sezon_etiketi(S.yil, S.lig)} sayfasına geç'
        d['istek'] += 1
        istek = d['istek']
        self.takip_ciz()
        self._ozet_doldur(S, p)
        self.kapsam.set_value(d['kapsam'])
        # "daha ucuz": piyasa değerleri bugünkü, yalnızca süren sezonda anlamlı
        secenek = BENZER_SUZGEC if S.yil == SON_SEZON else {k: v for k, v in BENZER_SUZGEC.items() if k != 'ucuz'}
        if d['benzer_suz'] not in secenek:
            d['benzer_suz'] = ''
        self.benzer_suz.set_options(secenek, value=d['benzer_suz'])
        self._bos_yukleniyor(S, p)
        self.dlg.open()
        if S.lig in FIZIKSEL_LIGLER and S.yil == SON_SEZON and p.get('fm_id'):
            self.fiz_not.text = 'Fiziksel veriler hazırlanıyor…'
            G.arka_plan(self.fiziksel_yukle(S, p, istek))
        G.arka_plan(self.benzer_yukle(p, istek))
        G.arka_plan(self.kariyer_yukle(p, istek))
        self.deger_sut.set_visibility(False)
        self.istikrar_not.content = ''
        if p.get('fm_id'):
            G.arka_plan(self.son_maclar_yukle(p, istek))
            G.arka_plan(self.deger_sut_yukle(p, istek))
            G.arka_plan(self.tum_kulvarlar_yukle(p, istek))
            if S.yil == SON_SEZON:
                G.arka_plan(self.istikrar_yukle(S, p, istek))

    # ---------------------------------------------------------------- arka plan yüklemeleri
    async def istikrar_yukle(self, S, p, istek):
        """Maçtan maça istikrar (lig_maclari.istikrar): bu sezon ligdeki maç puanlarının dalgalanması, ligdeki
        oyuncularla kıyas. Yalnızca önceden indirilmiş maçlar (ağ isteği yok)."""
        try:
            satirlar = await run.io_bound(lig_maclari.oyuncu_satirlari, S.lig, self.G.depo.g.ham, None, False)
        except Exception:
            logger.debug('istikrar için maç verisi okunamadı: %s', S.lig, exc_info=True)
            return
        if istek != self.d['istek'] or not str(p['fm_id']).isdigit():
            return
        v = lig_maclari.istikrar(satirlar).get(int(p['fm_id']))
        self.istikrar_not.content = istikrar_html(v)

    async def deger_sut_yukle(self, p, istek):
        """Piyasa değeri geçmişi ve güncel sezonun şut haritası (FotMob oyuncu sayfası; son maçlarla aynı sayfa)."""
        try:
            degerler, sutlar = await run.io_bound(takim.deger_ve_sutlar, p['fm_id'], self.G.depo.g.ham)
        except Exception:
            logger.debug('değer geçmişi ve şutlar alınamadı: %s', p['fm_id'], exc_info=True)
            return
        if istek != self.d['istek'] or (not degerler and not sutlar):
            return
        self.deger_sut.set_visibility(True)
        self.sut_kutu.content = sut_haritasi(sutlar) if sutlar else '<p class="cap">Bu sezon şut kaydı yok.</p>'
        if sutlar:
            self.sut_not.text = sut_notu(sutlar)
        if degerler:
            self.deger_grafik.options['series'][0]['data'] = [[t, round(v / 1e6, 2)] for t, v, _ in degerler]
            self.deger_grafik.options['series'][0]['markPoint']['data'] = deger_isaretleri(degerler)
            self.deger_grafik.update()
            self.deger_not.text = deger_notu(degerler)
        else:
            self.deger_not.text = 'Değer geçmişi yok.'

    async def fiziksel_yukle(self, S, p, istek):
        """Sezonluk fiziksel veriler (maç maç FotMob verisinden; lig_maclari.fiziksel_ozet) ve ligdeki yüzdelik sırası."""
        def ilerleme(k, n):
            if istek == self.d['istek']:
                self.fiz_not.text = f'Ligin maç verisi hazırlanıyor… {k}/{n} (ilk açılışta bir kez indirilir)'
        try:
            satirlar = await run.io_bound(lig_maclari.oyuncu_satirlari, S.lig, self.G.depo.g.ham, ilerleme)
        except Exception:
            logger.warning('ligin maç verisi alınamadı: %s', S.lig, exc_info=True)
            satirlar = []
        if istek != self.d['istek']:
            return
        oz = lig_maclari.fiziksel_ozet(satirlar)
        o = oz.get(int(p['fm_id'])) if str(p['fm_id']).isdigit() else None
        if not o:
            self.fiz_kutu.content = ''
            self.fiz_not.text = 'Bu oyuncu için fiziksel veri yok (bu sezon ligde oynadığı maçlarda kaydedilmemiş).'
            return
        havuz = [x for x in oz.values() if x['dk'] >= lig_maclari.FIZIKSEL_MIN_DK]
        self.fiz_kutu.content = fiziksel_html(o, havuz)
        self.fiz_not.text = fiziksel_notu(o, havuz)

    async def tum_kulvarlar_yukle(self, p, istek):
        """FotMob kariyer bilgisi: sezon sezon, takım takım toplam ve altında kulvar kulvar (lig, kupa, Avrupa…)."""
        try:
            sezonlar = await run.io_bound(takim.oyuncu_kariyeri, p['fm_id'], self.G.depo.g.ham)
        except Exception as ex:
            if istek == self.d['istek']:
                self.tum_not.text = f'Kariyer bilgisi alınamadı: {hata_metni(ex, "kariyer bilgisi")}'
            return
        if istek != self.d['istek']:
            return
        if not sezonlar:
            self.tum_not.text = 'FotMob\'da kariyer bilgisi yok.'
            return
        self.tum_kutu.content = kulvar_html(sezonlar)
        self.tum_not.text = KULVAR_NOTU

    async def son_maclar_yukle(self, p, istek):
        """FotMob'dan son maçlar: maç maç gol, asist ve puan grafiği ve tablo (bütün kulvarlar ve milli takım)."""
        try:
            maclar = await run.io_bound(takim.oyuncu_son_maclar, p['fm_id'], self.G.depo.g.ham)
        except Exception as ex:
            if istek == self.d['istek']:
                self.son_not.text = f'Son maçlar alınamadı: {hata_metni(ex, "son maçlar")}'
            return
        if istek != self.d['istek']:
            return
        maclar = maclar[-25:]
        if not maclar:
            self.son_not.text = 'FotMob\'da son maç kaydı yok.'
            return
        self.son_not.text = son_maclar_notu(maclar)
        secenek = self.son_grafik.options
        secenek['xAxis']['data'] = [f'{m["zaman"][8:10]}.{m["zaman"][5:7]} {m["rakip"][:10]}' for m in maclar]
        secenek['series'][0]['data'] = [m['gol'] for m in maclar]
        secenek['series'][1]['data'] = [m['asist'] for m in maclar]
        secenek['series'][2]['data'] = [m['puan'] for m in maclar]
        self.son_grafik.update()
        self.son_tablo.content = son_maclar_html(maclar)

    def _benzer_ciz(self, S, liste):
        G = self.G
        with self.benzer:
            for q, lig_anahtar, b, yas, dg in liste:
                pc = max(0, round(b * 100))
                l = lig_bilgi(lig_anahtar)
                with ui.element('div').classes('satir'):
                    with ui.element('div'):
                        if lig_anahtar == S.lig:
                            ui.button(q['n'], on_click=lambda _, i=q['idx']: G.arka_plan(self.ac(idx=i, S=S))).props(
                                'flat dense no-caps').classes('link')
                        else:
                            ui.button(q['n'], on_click=lambda _, k=lig_anahtar, i=q['id']: G.git(k, S.yil, i)).props(
                                'flat dense no-caps').classes('link')
                        ui.html(f'<small>{e(q["t"])} · {e(mevki_adi(q))}'
                                + (f' · {yas} yaş' if yas is not None else '') + (f' · {_para(dg)}' if dg else '')
                                + (f' · {e(l[1])} ({e(l[2])})' if lig_anahtar != S.lig else '')
                                + f' · {q["g"]} gol, {q["a"]} asist</small>', sanitize=False)
                    ui.html(f'<div class="track"><i style="width:{pc}%"></i></div>', sanitize=False)
                    ui.label(f'{pc}%').classes('pv')

    async def benzer_yukle(self, p, istek):
        G, d = self.G, self.d
        S = d['S']
        r = await run.io_bound(benzer_oyuncular, S, p, G.depo.veri_klasoru, d['kapsam'] == 'tum', None)
        if istek != d['istek'] or d['S'] is not S or r is None:
            return
        self.benzer.clear()
        if r.get('kaleci'):
            self.benzer_not.text = 'Bu ligin veri kaynağı kaleciler için ayrıntılı istatistik vermediği için karşılaştırma yapılamıyor.'
            return
        esik = benzer_esik(S)
        if r.get('yok'):
            self.benzer_not.text = (f'Benzer oyuncu araması için en az {esik} dakika gerekiyor.' if p['min'] < esik
                                    else 'Bu oyuncu için karşılaştırma yapılacak yeterli veri yok.')
            return
        fm = p.get('fm_id')
        d['deger'] = (G.depo.degerler_onbellek(S.lig).get(int(fm)) if S.yil == SON_SEZON and str(fm).isdigit() else None)
        if d['benzer_suz'] == 'ucuz' and not d['deger']:
            self.benzer_not.text = 'Bu oyuncunun piyasa değeri bilinmediği için "daha ucuz" süzgeci uygulanamıyor.'
            return
        liste = benzer_suz_uygula(G.depo, d, S, p, r['sonuc'])
        if not liste:
            self.benzer_not.text = 'Bu süzgeçle benzer oyuncu bulunamadı; "Tüm ligler"i dene.'
            return
        self._benzer_ciz(S, liste)
        self.benzer_not.text = benzer_notu(d, p, r, esik)

    async def gelisim_yukle(self, satirlar, istek):
        """Sezon sezon performans endeksi (o sezonki mevkidaşlarına göre; oyuncu_tahmin.performans_endeksi) ve 90 dakikada
        gol + asist. satirlar: kariyer() satırları (her lig-sezonda oyuncunun kendi id'si)."""
        G, d = self.G, self.d
        noktalar = []
        for r in sorted(satirlar, key=lambda r: (r['yil'], r['lig']))[-GELISIM_SEZON:]:
            try:
                S2 = await run.io_bound(G.depo.sezon, r['anahtar'], r['yil'])
                endeks = await run.io_bound(oyuncu_tahmin.performans_endeksi, S2)
            except Exception:
                logger.debug('gelişim noktası hesaplanamadı: %s %s', r['anahtar'], r['yil'], exc_info=True)
                continue
            if istek != d['istek']:
                return
            q = next((x for x in S2.PLY if x['id'] == r['id'] and x['t'] == r['takim']), None) \
                or next((x for x in S2.PLY if x['id'] == r['id']), None)
            if q is None or not q['min']:
                continue
            e_ = endeks.get(q['idx']) if endeks else None
            noktalar.append((f'{sezon_etiketi(r["yil"], r["anahtar"])}\n{r["takim"][:12]}',
                             round(e_, 1) if e_ is not None else None, round((q['g'] + q['a']) / q['min'] * 90, 2), q['min']))
        if istek != d['istek'] or len(noktalar) < 2:
            return
        self.gelisim_grafik.options['xAxis']['data'] = [n[0] for n in noktalar]
        self.gelisim_grafik.options['series'][0]['data'] = [n[1] for n in noktalar]
        self.gelisim_grafik.options['series'][1]['data'] = [n[2] for n in noktalar]
        self.gelisim_grafik.update()
        self.gelisim_bolum.set_visibility(True)
        self.gelisim_not.text = gelisim_notu(noktalar)

    def _kariyer_ciz(self, S, satirlar):
        G = self.G
        with self.kariyer_kutu:
            with ui.element('div').classes('w-full').style(
                    'display:grid;grid-template-columns:90px minmax(0,1.2fr) minmax(0,1.4fr) repeat(6,56px);gap:2px 8px;font-size:.88rem'):
                for b in ('Sezon', 'Lig', 'Takım', 'Maç', 'Dk', 'Gol', 'xG', 'Asist', 'xA'):
                    ui.label(b).classes('cap').style('font-weight:600')
                for r in satirlar:
                    bu = r['anahtar'] == S.lig and r['yil'] == S.yil
                    etiket = sezon_etiketi(r['yil'], r['anahtar'])
                    if bu:
                        ui.label(etiket).style('font-weight:700')
                    else:
                        # o lig-sezondaki kendi id'siyle (kaynaklar arasında id değişir)
                        ui.button(etiket, on_click=lambda _, k=r['anahtar'], y=r['yil'], i=r['id']: G.git(k, y, i)).props(
                            'flat dense no-caps').classes('link')
                    for v in (r['lig'], r['takim'], r['mp'], sayi(r['min']), r['g'], fmt(r['xg'], 1), r['a'], fmt(r['xa'], 1)):
                        ui.label(str(v)).style('font-weight:700' if bu else '')

    async def kariyer_yukle(self, p, istek):
        G, d = self.G, self.d
        S = d['S']
        self.kariyer_kutu.clear()
        if p['id'] is None:
            self.kariyer_not.text = 'Bu oyuncu için sezon geçmişi yok.'
            return
        satirlar = await run.io_bound(kariyer, G.depo.veri_klasoru, S.src, p['id'], p.get('fm_id'))
        if istek != d['istek'] or d['S'] is not S or satirlar is None:
            return
        self._kariyer_ciz(S, satirlar)
        G.arka_plan(self.gelisim_yukle(satirlar, istek))
        self.kariyer_not.text = (f'Uygulamadaki {len(LIGLER)} ligde bulunan sezonlar (veri kaynakları arasında FotMob kimliğiyle '
                                 'eşleştirilir). Uygulamada olmayan liglerdeki ve kupalardaki sezonlar burada görünmez. Başka bir '
                                 'sezona geçmek için sezona tıkla.')


def kur(G):
    kart = _Kart(G)
    G.kart_kapatanlar.append(kart.dlg.close)  # bir sekmeye (ör. lig maçının tahmini) geçilirken kapanır
    return kart.ac
